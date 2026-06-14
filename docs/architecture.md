# Architecture: WC2026 Group Stage Predictor

> **Status**: Draft   **Last Updated**: June 2026   **Owner**: Gede

-----

## Overview & Goals

**Problem Statement**:

The FIFA World Cup 2026 group stage features 48 teams across 12 groups (A–L), playing 3 matchdays between June 12 and July 2, 2026. Manually tracking team form, FIFA rankings, and squad data across 12 groups to make informed predictions is time-consuming. This project automates data collection, AI-powered prediction generation, and accuracy tracking in a fully serverless Azure pipeline.

## Success Criteria

- All 12 group stage winners and runners-up predicted before Matchday 1 (June 12, 2026)
- Predictions automatically revised after each matchday based on actual results
- Prediction accuracy tracked and displayed (e.g. 8/12 groups correct after Matchday 2)
- Total infrastructure cost does not exceed $1 for the full tournament
- All Azure services remain within always-free tier limits

-----

## Tech Stack

| Layer        | Technology                               | Rationale                                                                       |
|--------------|------------------------------------------|---------------------------------------------------------------------------------|
| Frontend     | Azure Static Web Apps (React)            | Free hobby tier; deploys from Azure DevOps; no server management                |
| API Layer    | Azure Functions — HTTP Trigger (Python)  | Serverless; 1M free executions/month; no server management                      |
| Scheduling   | Azure Logic Apps (Consumption)           | 6-hour recurrence trigger; independent of Function App host; ~240 actions/month |
| Ingestion    | Azure Functions — Queue Trigger (Python) | Triggered by Logic App → POST /api/ingest → Storage Queue; decoupled            |
| Prediction   | Azure Functions — Queue Trigger (Python) | Triggered by fn-ingest via Storage Queue when matches finish; event-driven      |
| Event Bus    | Azure Queue Storage                      | Free (bundled with Functions storage account); decouples ingest from prediction |
| Database     | Azure Cosmos DB — NoSQL API              | Permanent free tier: 1,000 RU/s + 25GB; schema-free JSON fits team/fixture data |
| AI / LLM     | Anthropic Claude API (claude-haiku-4-5)  | ~$0.14 for full group stage; sufficient for structured JSON prediction tasks    |
| Data Source  | football-data.org v4                     | Free tier: 10 req/min; covers WC 2026 fixtures, live scores, group standings    |
| News Search  | Serper.dev (Google Search API)           | Free tier: 2,500 searches/month; provides up-to-date team news for Claude prompt |
| Secrets      | Azure Key Vault                          | Managed identity access; no credentials in app settings or source control       |
| CI/CD        | Azure DevOps Pipelines                   | YAML pipelines; Bicep infra + function deploy stages                            |
| IaC          | Azure Bicep                              | Declarative provisioning of Cosmos DB, Function App, Static Web App, Key Vault  |
| Package Mgmt | uv (Python)                              | Fast lockfile-based installs; consistent across local and pipeline              |
| Local Dev    | Azure Functions Core Tools + Azurite     | Run functions and emulate Cosmos DB locally without Azure connectivity           |

-----

## System Components

### 3.1 Data Flow Overview

The pipeline runs in three layers: ingestion (football-data.org → Cosmos DB), prediction (Cosmos DB → Claude API → Cosmos DB), and presentation (Cosmos DB → Azure Functions HTTP → React frontend).

```
Key Vault          →  (managed identity)      →  fn-ingest, fn-predict, fn-api
Logic App (6h)     →  POST /api/ingest        →  ingest-trigger Queue
ingest-trigger     →  fn-ingest (Queue)        →  football-data.org  →  Cosmos DB
                                               →  predict-trigger Queue (on match finish)
predict-trigger    →  fn-predict (Queue)       →  Claude API  →  Cosmos DB
Cosmos DB          →  fn-api (HTTP)            →  React Static Web App
```

### 3.2 Azure Functions

#### fn-ingest — Queue Trigger (`ingest-trigger` queue)

- Triggered by `POST /api/ingest` (fn-api enqueues to `ingest-trigger`, returns 202 immediately)
- Retrieves `FOOTBALL_DATA_API_KEY` and Cosmos DB connection string from Key Vault via managed identity
- Calls football-data.org v4 (`/v4/competitions/2000/...`) to fetch current WC fixtures and group standings
- On first run: seeds the `teams` container with all 48 teams and group assignments derived from standings
- Fetches **group stage** fixtures for matchdays 1–3 and **knockout stage** fixtures for all rounds (`LAST_32`, `LAST_16`, `QUARTER_FINALS`, `SEMI_FINALS`, `THIRD_PLACE`, `FINAL`)
- Upserts all fixture and result data into the `fixtures` Cosmos DB container; knockout fixtures use the stage string (e.g. `"LAST_32"`) as the `matchday` field since the API returns `null` for knockout matchdays
- HTTP calls to football-data.org use automatic retry with exponential backoff (2 s, 4 s) on transient connection errors (`RemoteProtocolError`, `ConnectError`, `ReadTimeout`); HTTP 4xx/5xx errors are not retried
- After each upsert, compares incoming `status` against the previously stored value; if any fixture transitions to `FT`, enqueues a **Base64-encoded** JSON message `{"matchday": N, "fixtureId": M, "correlationId": "..."}` to the `predict-trigger` Storage Queue
- Propagates a `correlationId` (UUID) through the queue message for end-to-end observability
- Logs group assignment counts, fixture upsert counts, and enqueue events for observability

#### fn-predict — Queue Trigger (`predict-trigger` queue)

- Retrieves `ANTHROPIC_API_KEY` and Cosmos DB connection string from Key Vault via managed identity
- Fires in two scenarios:
  1. When fn-ingest enqueues a message indicating one or more matches have finished (auto-regenerate predictions)
  2. When the `POST /api/predictions/trigger` HTTP endpoint is called (on-demand, before tournament starts)
- Reads current `fixtures` and `teams` data from Cosmos DB
- Constructs a structured prompt with group standings, team form, and FIFA rankings; for knockout fixtures where both teams are known (not TBD), the prompt also includes a `KNOCKOUT FIXTURES` section
- If `SERPA_API_KEY` is set, fetches recent news for all teams **in parallel** via `asyncio.gather()` using **Serper** (`POST https://google.serper.dev/news`), enriching the Claude prompt with up-to-date injury/form/squad information; results are cached in the `news` Cosmos container for 12 hours (configurable via `SERPA_MAX_RESULTS`, default 3) to avoid redundant API calls within the same matchday
- Calls the **Claude API using structured outputs** (Pydantic `PredictionsResponse` model with `extra="forbid"`) to guarantee valid JSON; generates group-stage predictions (winner, runner-up, confidence, reasoning, per-match scores) **and** knockout match predictions (predicted winner per fixture)
- Computes accuracy scores immediately after prediction if any finished fixtures are present, writing results to the `scores` container
- Writes prediction documents to the `predictions` container under the fixed id `predictions-all`
- Idempotent: if multiple messages arrive for the same matchday (e.g. two matches finish in the same 6h window), the latest run overwrites the previous prediction document

#### fn-api — HTTP Trigger

- Exposes a lightweight REST API consumed by the React frontend and operators
- `GET /groups` — returns all 12 groups with current standings
- `GET /predictions` — returns latest Claude predictions with per-group reasoning and confidence levels
- `GET /fixtures/{matchday}` — returns scheduled and completed group-stage matches for a given matchday, with predicted scores merged in where available
- `GET /fixtures/stage/{stage}` — returns fixtures for a knockout stage (e.g. `LAST_32`, `FINAL`); the stage string matches the value stored in the `stage` field of each fixture document
- `GET /news/{team}` — returns the most recent cached news doc for a team (`{ teamName, snippets[], date }`); returns `{ snippets: [] }` if nothing is cached yet; team name is URL-decoded so spaces work
- `GET /accuracy` — returns prediction accuracy stats after each matchday; a group counts as correct only if **both** predicted winner and runner-up match the actual final standings (strict scoring, max 12 points)
- `GET /usage` — returns API call counts and token usage for the current window per provider (Anthropic, football-data.org), compared against configured rate-limit thresholds
- `GET /status` — pipeline health snapshot: latest prediction metadata, Storage Queue depths (including poison queue), team count, and finished/total fixture counts; each component degrades independently (returns `null` for that field on error)
- `POST /api/predictions/trigger` — enqueue a prediction generation job (optional JSON body: `{"matchday": 1}`); allows pre-tournament predictions before any matches finish
- `POST /api/ingest` — enqueue an ingest job immediately; returns 202 with a `correlationId` for tracing

### 3.3 Cosmos DB Schema

Five containers, all using NoSQL JSON documents. Partition keys designed for point reads.

| Container     | Partition Key | Sample Document Fields                                                                         |
|---------------|---------------|------------------------------------------------------------------------------------------------|
| `teams`       | `/group`      | `teamId`, `name`, `group`, `fifaRanking`, `recentForm[5]`, `squadDepth`                        |
| `fixtures`    | `/matchday`   | `fixtureId`, `matchday`, `stage`, `homeTeam`, `awayTeam`, `kickoff`, `homeScore`, `awayScore`, `status` — for group-stage fixtures `matchday` is an integer (1–3); for knockout fixtures it is the stage string (e.g. `"LAST_32"`) because the API returns `null` |
| `predictions` | `/matchday`   | `id` (`predictions-all`), `matchday`, `generatedAt`, `groups[{group, winner, runnerUp, confidence, reasoning, matches[]}]`, `knockout[{stage, matches[{fixtureId, predictedWinner, ...}]}]` |
| `scores`      | `/matchday`   | `scoreId`, `matchday`, `evaluatedAt`, `score`, `totalGroups`, `groups[{group, correct, predictedWinner, actualWinner, predictedRunnerUp, actualRunnerUp}]`, `knockoutScore`, `knockoutTotal` |
| `news`        | `/teamName`   | `id` (`news-{team}-{date}`), `teamName`, `date`, `snippets[]`, `ttl` (43200s / 12h)            |
| `usage`       | `/provider`   | `id` (`usage-{provider}-{date}`), `provider`, `date`, `callCount`, `inputTokens`, `outputTokens` |

### 3.4 React Frontend

- **Groups View**: all 12 groups (A–L) with predicted winner, runner-up, and Claude's reasoning blurb; each team name shows a 📰 news icon that opens the `TeamNewsModal` overlay
- **TeamNewsModal**: fetches `GET /news/{team}` on open; shows loading state, snippets list, empty state, and error state; closes on backdrop click, close button, or Escape key; rendered via `createPortal` to `document.body` to avoid z-index/overflow clipping
- **Fixtures View**: upcoming and completed matches with live scores per group
- **Accuracy View**: after each matchday, shows correct vs incorrect predictions
- **Usage View**: shows current-window API call counts and rate-limit percentage per provider
- Deployed via the `frontend` stage in Azure DevOps Pipelines using the `AzureStaticWebApp@0` task
- Calls `fn-api` HTTP trigger directly; no separate backend server required

#### Mock Layer (MSW)

`frontend/src/mocks/` provides a shared API mock layer using [MSW (Mock Service Worker)](https://mswjs.io/):

| File | Purpose |
|---|---|
| `data.js` | Seed data constants (groups, predictions, fixtures, news, etc.) shared across handlers and tests |
| `handlers.js` | MSW request handlers for all API routes, using relative paths (`/api/...`) to match any origin |
| `browser.js` | `setupWorker` for the Vite dev server — intercepts fetch at the service worker level |
| `server.js` | `setupServer` for vitest — intercepts fetch in Node.js |

In dev mode (`npm run dev`), `main.jsx` starts the MSW browser worker so the full UI loads with realistic mock data and no backend connection required. In tests, `test-setup.js` starts the Node server before each suite and resets handlers after each test, so all tests share one consistent mock baseline and use `server.use()` for per-test overrides.

### 3.5 Azure DevOps Pipeline

Three-stage pipeline:

| Stage       | Trigger               | Actions                                                                                              |
|-------------|-----------------------|------------------------------------------------------------------------------------------------------|
| `infra`     | Push to main / manual | `az deployment` run on `main.bicep` — provisions Cosmos DB, Function App, Static Web App, Key Vault  |
| `functions` | Push to main          | `uv build` → zip artifact → `az functionapp deploy` to Function App                                  |
| `frontend`  | Push to main          | `npm build` → artifact → `AzureStaticWebApp@0` deploy task                                           |

### 3.6 Repository Structure

```
wc2026-predictor/
├── infra/
│   └── main.bicep
├── functions/
│   ├── fn_ingest/   __init__.py, function.json
│   ├── fn_predict/  __init__.py, function.json
│   ├── fn_api/      __init__.py, function.json
│   ├── local.settings.json.template
│   ├── pyproject.toml
│   └── host.json
├── frontend/
│   ├── src/
│   │   └── mocks/   data.js, handlers.js, browser.js, server.js
│   └── package.json
└── pipelines/
    └── azure-pipelines.yml
```

### 3.7 Secret Management

All runtime secrets are stored in Azure Key Vault and accessed via the Function App's system-assigned managed identity — no credentials are stored in App Settings or source control.

| Secret name              | Value                                   |
|--------------------------|-----------------------------------------|
| `apisports-api-key`      | API-Football (api-sports.io) API key    |
| `anthropic-api-key`      | Anthropic Claude API key                |
| `cosmos-connection-string` | Cosmos DB primary connection string   |
| `serpa-api-key`          | Serper.dev API key for team news search |

The `infra` Bicep stage provisions the Key Vault, creates secrets, grants the Function App's managed identity `Key Vault Secrets User` role, and outputs the vault URI into a pipeline variable consumed by the `functions` stage.

### 3.8 Local Development

| Tool                       | Purpose                                              |
|----------------------------|------------------------------------------------------|
| Azure Functions Core Tools | Run functions locally with `func start`              |
| Azurite                    | Emulate Cosmos DB and Queue Storage without Azure    |

`functions/local.settings.json.template` is committed to source control with placeholder values. Developers copy it to `local.settings.json` (git-ignored) and fill in real keys. The `AzureWebJobsStorage` and `CosmosDbConnectionString` values point to Azurite during local runs.

-----

## Data Model / API

### football-data.org v4

Base URL: `https://api.football-data.org/v4`  
Auth header: `X-Auth-Token: {FOOTBALL_DATA_API_KEY}`  
WC 2026 identifiers: competition `2000` (code `WC`)  
Free tier: **10 requests/minute** — `fn-ingest` runs at most ~10 calls per ingest cycle (well within limit)

| Endpoint                                                        | Parameters            | Usage                                             |
|-----------------------------------------------------------------|-----------------------|---------------------------------------------------|
| `GET /competitions/2000/teams`                                  | —                     | Seed all 48 WC2026 teams on first run             |
| `GET /competitions/2000/standings`                              | —                     | Fetch all 12 group tables (used for group assignments) |
| `GET /competitions/2000/matches`                                | `matchday=N`          | Fetch group-stage fixtures for matchday 1, 2, or 3 |
| `GET /competitions/2000/matches`                                | `stage=LAST_32` etc.  | Fetch knockout fixtures per stage                 |

Knockout stage values: `LAST_32`, `LAST_16`, `QUARTER_FINALS`, `SEMI_FINALS`, `THIRD_PLACE`, `FINAL`.  
The API returns `matchday: null` for all knockout fixtures — `fn-ingest` substitutes the stage string as the `matchday` value in Cosmos DB.

All calls are wrapped in `_get_with_retry()` which retries up to 3 times with exponential backoff on `RemoteProtocolError`, `ConnectError`, and `ReadTimeout`; `HTTPStatusError` (4xx/5xx) is raised immediately without retry.

### Claude API Request Shape

`fn-predict` sends a single request per prediction job (on-demand or post-match) containing all 12 groups and any known knockout fixtures. Claude responds with a validated JSON structure (enforced via Pydantic structured outputs) including confidence ratings, per-match predictions, and knockout winner predictions:

```json
{
  "predictions": [
    {
      "group": "A",
      "winner": "Germany",
      "runnerUp": "Mexico",
      "confidence": "high",
      "reasoning": "Germany leads on FIFA ranking and form...",
      "matches": [
        {
          "homeTeam": "Germany",
          "awayTeam": "Mexico",
          "matchday": 1,
          "predictedHomeScore": 2,
          "predictedAwayScore": 0,
          "confidence": "high"
        }
      ]
    }
  ],
  "knockout": [
    {
      "stage": "LAST_32",
      "matches": [
        {
          "fixtureId": 537417,
          "stage": "LAST_32",
          "homeTeam": "Germany",
          "awayTeam": "Mexico",
          "predictedWinner": "Germany",
          "predictedHomeScore": 2,
          "predictedAwayScore": 1,
          "confidence": "high"
        }
      ]
    }
  ]
}
```

### fn-api Response Shape (`GET /accuracy`)

A group is scored as correct only when **both** predicted winner and runner-up match actual final standings. Maximum score is 12 (one point per group).

```json
{
  "matchday": 2,
  "evaluatedAt": "2026-06-22T10:00:00Z",
  "score": 8,
  "totalGroups": 12,
  "groups": [
    {
      "group": "A",
      "correct": true,
      "predictedWinner": "Germany",
      "actualWinner": "Germany",
      "predictedRunnerUp": "Mexico",
      "actualRunnerUp": "Mexico"
    }
  ]
}
```

### fn-api Response Shape (`GET /predictions`)

```json
{
  "matchday": 2,
  "generatedAt": "2026-06-20T08:00:00Z",
  "groups": [
    {
      "group": "A",
      "winner": "Germany",
      "runnerUp": "Mexico",
      "confidence": "high",
      "reasoning": "...",
      "matches": [
        {
          "homeTeam": "Germany",
          "awayTeam": "Mexico",
          "matchday": 1,
          "predictedHomeScore": 2,
          "predictedAwayScore": 0,
          "confidence": "high"
        }
      ]
    }
  ]
}
```

-----

## Cost Summary

| Service                | Free Limit                      | Estimated Usage       | Est. Cost |
|------------------------|---------------------------------|-----------------------|-----------|
| Azure Key Vault        | 10,000 operations/month free    | ~100 secret reads     | $0.00     |
| Azure Cosmos DB        | 1,000 RU/s + 25GB (permanent)   | <1GB, <200 RU/s       | $0.00     |
| Azure Functions        | 1M executions/month (permanent) | ~700 executions total | $0.00     |
| Azure Static Web Apps  | Free hobby tier (permanent)     | Personal project      | $0.00     |
| Azure Logic Apps       | 4,000 actions/month free        | ~240 actions/month    | $0.00     |
| Claude API (Haiku 4.5) | Pay-per-use                     | ~36 prediction calls  | ~$0.14    |
| football-data.org      | 10 req/min free                 | ~10 calls per ingest cycle | $0.00 |
| **Total**              |                                 |                       | **~$0.14** |

-----

## Scheduling

| Trigger      | Schedule                             | Purpose                                                         |
|--------------|--------------------------------------|-----------------------------------------------------------------|
| Logic App    | Every 6 hours (independent of host)  | POSTs to `POST /api/ingest`; wakes fn-ingest reliably regardless of Function App cold-start state |
| `fn-ingest`  | Queue Trigger (`ingest-trigger`)     | Fetch latest match results and standings; enqueue predict-trigger on FINISHED matches |
| `fn-predict` | On match finish OR on-demand HTTP    | Regenerate predictions when fn-ingest detects a FINISHED match, or when `POST /api/predictions/trigger` is called (pre-tournament) |
| `fn-api`     | On-demand HTTP                       | Serve frontend requests; no schedule                            |

**Why Logic Apps instead of Function Timer Trigger:** On the Azure Functions Consumption Plan, a low-traffic app stays cold between HTTP requests and can miss scheduled timer fires (the scale controller wakes the host, but if it shuts down before the cron slot, the fire is missed). Logic Apps Consumption tier runs its recurrence trigger independently of the Function App host — it simply makes an HTTP call when the timer fires. At 4 runs/day × 2 actions/run = ~240 actions/month (well within the 4,000/month free tier).

-----

## Pre-Tournament Prediction Workflow

To satisfy the success criterion of predictions ready before Matchday 1 (June 12):

1. **Before June 11**: Call `POST /api/predictions/trigger` with `{"matchday": 1}` to enqueue a prediction generation job. This does NOT require any matches to be finished.
2. **Within 30s**: fn-predict processes the queue message, reads current teams and fixtures from Cosmos DB, calls Claude API with instructions to predict group winners and match scores, and writes the results to the predictions container.
3. **Immediately available**: Frontend displays predictions on the Groups and Fixtures views with confidence badges and reasoning.
4. **After each matchday**: fn-ingest detects finished matches and automatically re-enqueues fn-predict to regenerate predictions with actual results incorporated.

The `POST /api/predictions/trigger` endpoint allows predictions to be generated on-demand at any point in the tournament without waiting for matches to finish. Calling it multiple times for the same matchday overwrites the previous prediction (idempotent).

-----

## Setup Prerequisites

- Register at [api-sports.io](https://www.api-sports.io) for a free API key (100 req/day; instant approval)
- Add $10 credit to Anthropic Console at [console.anthropic.com](https://console.anthropic.com)
- Create a dedicated Azure subscription to avoid consuming the one-per-subscription Cosmos DB free tier
- Create Cosmos DB account with free tier opt-in enabled — this must be selected at account creation time and cannot be added retroactively
- Disable or configure aggressive sampling on Application Insights to avoid unexpected Log Analytics charges
- Create Azure Key Vault in the same resource group as the Function App; enable system-assigned managed identity on the Function App and grant it the `Key Vault Secrets User` role
- Copy `functions/local.settings.json.template` to `functions/local.settings.json` for local development (never commit `local.settings.json`)

-----

## Research & References

| Resource                   | URL                                                                     | Purpose                             |
|----------------------------|-------------------------------------------------------------------------|-------------------------------------|
| football-data.org          | <https://www.football-data.org>                                         | Live WC fixture and standings data  |
| football-data.org Docs     | <https://docs.football-data.org/general/v4>                             | v4 endpoint reference               |
| Anthropic Console          | <https://console.anthropic.com>                                         | Claude API access and billing       |
| Azure Cosmos DB Free Tier  | <https://learn.microsoft.com/en-us/azure/cosmos-db/free-tier>           | Free tier eligibility and limits    |
| Azure Functions Pricing    | <https://azure.microsoft.com/en-us/pricing/details/functions/>          | Consumption plan free grant details |
| Azure Static Web Apps      | <https://azure.microsoft.com/en-us/pricing/details/app-service/static/> | Free hobby tier details             |
| FIFA World Cup 2026 Groups | <https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026> | Official group draw and schedule    |
