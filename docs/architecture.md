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
| API Layer    | Azure Functions — HTTP Trigger (Python)  | Serverless; 1M free executions/month; familiar from DLAB pipelines              |
| Ingestion    | Azure Functions — Timer Trigger (Python) | Cron-scheduled every 6h during tournament window; zero cost at this scale       |
| Prediction   | Azure Functions — Queue Trigger (Python) | Triggered by fn-ingest via Storage Queue when matches finish; event-driven      |
| Event Bus    | Azure Queue Storage                      | Free (bundled with Functions storage account); decouples ingest from prediction |
| Database     | Azure Cosmos DB — NoSQL API              | Permanent free tier: 1,000 RU/s + 25GB; schema-free JSON fits team/fixture data |
| AI / LLM     | Anthropic Claude API (claude-haiku-4-5)  | ~$0.14 for full group stage; sufficient for structured JSON prediction tasks    |
| Data Source  | football-data.org REST API               | Free plan covers WC fixtures, live scores, group standings                      |
| CI/CD        | Azure DevOps Pipelines                   | Existing DLAB YAML templates reused; Bicep infra + function deploy stages       |
| IaC          | Azure Bicep                              | Declarative provisioning of Cosmos DB, Function App, Static Web App             |
| Package Mgmt | uv (Python)                              | Consistent with DLAB toolchain; fast lockfile-based installs in pipeline        |

-----

## System Components

### 3.1 Data Flow Overview

The pipeline runs in three layers: ingestion (football-data.org → Cosmos DB), prediction (Cosmos DB → Claude API → Cosmos DB), and presentation (Cosmos DB → Azure Functions HTTP → React frontend).

```
football-data.org  →  fn-ingest (Timer, 6h)  →  Cosmos DB
                                              →  Storage Queue (on match finish)
Storage Queue      →  fn-predict (Queue)      →  Claude API  →  Cosmos DB
Cosmos DB          →  fn-api (HTTP)           →  React Static Web App
```

### 3.2 Azure Functions

#### fn-ingest — Timer Trigger (every 6 hours)

- Calls football-data.org free API to fetch current WC fixtures and match results
- On first run: seeds the `teams` container with all 48 teams, group assignments, FIFA rankings
- Upserts latest fixture and result data into the `fixtures` Cosmos DB container
- After each upsert, compares incoming `status` against the previously stored value; if any fixture transitions to `FINISHED`, enqueues a message to the `predict-trigger` Storage Queue
- Runs only during the tournament window (June 12 – July 2) to conserve executions

#### fn-predict — Queue Trigger (`predict-trigger` queue)

- Fires when fn-ingest enqueues a message indicating one or more matches have finished
- Reads current `fixtures` and `teams` data from Cosmos DB
- Constructs a structured prompt with group standings, team form, and FIFA rankings
- Calls Claude API (`claude-haiku-4-5`) requesting JSON output: group winner, runner-up, reasoning per group
- Writes prediction documents to the `predictions` container, versioned by matchday
- Idempotent: if multiple messages arrive for the same matchday (e.g. two matches finish in the same 6h window), the latest run overwrites the previous prediction document

#### fn-api — HTTP Trigger

- Exposes a lightweight REST API consumed by the React frontend
- `GET /groups` — returns all 12 groups with current standings
- `GET /predictions` — returns latest Claude predictions with reasoning
- `GET /fixtures/{matchday}` — returns scheduled and completed matches for a given matchday
- `GET /accuracy` — returns prediction accuracy stats after each matchday

### 3.3 Cosmos DB Schema

Four containers, all using NoSQL JSON documents. Partition keys designed for point reads.

| Container     | Partition Key | Sample Document Fields                                                                         |
|---------------|---------------|------------------------------------------------------------------------------------------------|
| `teams`       | `/group`      | `teamId`, `name`, `group`, `fifaRanking`, `recentForm[5]`, `squadDepth`                        |
| `fixtures`    | `/matchday`   | `fixtureId`, `matchday`, `homeTeam`, `awayTeam`, `kickoff`, `homeScore`, `awayScore`, `status` |
| `predictions` | `/matchday`   | `predictionId`, `matchday`, `generatedAt`, `groups[{group, winner, runnerUp, reasoning}]`      |
| `scores`      | `/matchday`   | `scoreId`, `matchday`, `evaluatedAt`, `correctWinners`, `correctRunnersUp`, `totalGroups`      |

### 3.4 React Frontend

- **Groups View**: all 12 groups (A–L) with predicted winner, runner-up, and Claude's reasoning blurb
- **Fixtures View**: upcoming and completed matches with live scores per group
- **Accuracy View**: after each matchday, shows correct vs incorrect predictions
- Deployed via the `frontend` stage in Azure DevOps Pipelines using the `AzureStaticWebApp@0` task
- Calls `fn-api` HTTP trigger directly; no separate backend server required

### 3.5 Azure DevOps Pipeline

Three-stage pipeline reusing existing DLAB YAML template patterns:

| Stage       | Trigger               | Actions                                                                                  |
|-------------|-----------------------|------------------------------------------------------------------------------------------|
| `infra`     | Push to main / manual | `az deployment` run on `main.bicep` — provisions Cosmos DB, Function App, Static Web App |
| `functions` | Push to main          | `uv build` → zip artifact → `az functionapp deploy` to Function App                      |
| `frontend`  | Push to main          | `npm build` → artifact → `AzureStaticWebApp@0` deploy task                               |

### 3.6 Repository Structure

```
wc2026-predictor/
├── infra/
│   └── main.bicep
├── functions/
│   ├── fn_ingest/   __init__.py, function.json
│   ├── fn_predict/  __init__.py, function.json
│   ├── fn_api/      __init__.py, function.json
│   ├── pyproject.toml
│   └── host.json
├── frontend/
│   ├── src/
│   └── package.json
└── pipelines/
    └── azure-pipelines.yml
```

-----

## Data Model / API

### football-data.org API

| Endpoint                            | Usage                                 | Free Tier Limit |
|-------------------------------------|---------------------------------------|-----------------|
| `GET /v4/competitions/WC/matches`   | Fetch all WC fixtures and live scores | 10 calls/minute |
| `GET /v4/competitions/WC/standings` | Fetch group standings per matchday    | 10 calls/minute |
| `GET /v4/competitions/WC/teams`     | Seed team metadata on first run       | 10 calls/minute |

### Claude API Request Shape

`fn-predict` sends a single request per daily run containing all 12 groups. Claude responds with a JSON array:

```json
{
  "predictions": [
    {
      "group": "A",
      "winner": "Germany",
      "runnerUp": "Mexico",
      "reasoning": "Germany leads on FIFA ranking and form..."
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
    { "group": "A", "winner": "Germany", "runnerUp": "Mexico", "reasoning": "..." }
  ]
}
```

-----

## Cost Summary

| Service                | Free Limit                      | Estimated Usage       | Est. Cost |
|------------------------|---------------------------------|-----------------------|-----------|
| Azure Cosmos DB        | 1,000 RU/s + 25GB (permanent)   | <1GB, <200 RU/s       | $0.00     |
| Azure Functions        | 1M executions/month (permanent) | ~700 executions total | $0.00     |
| Azure Static Web Apps  | Free hobby tier (permanent)     | Personal project      | $0.00     |
| Claude API (Haiku 4.5) | Pay-per-use                     | ~36 prediction calls  | ~$0.14    |
| football-data.org      | Free plan                       | ~300 API calls        | $0.00     |
| **Total**              |                                 |                       | **~$0.14** |

-----

## Scheduling

| Function     | Schedule                             | Purpose                                                         |
|--------------|--------------------------------------|-----------------------------------------------------------------|
| `fn-ingest`  | Every 6 hours, June 12 – July 2      | Fetch latest match results and standings from football-data.org |
| `fn-predict` | On match finish (Queue trigger)       | Regenerate predictions whenever fn-ingest detects a FINISHED match |
| `fn-api`     | On-demand HTTP                       | Serve frontend requests; no schedule                            |

-----

## Setup Prerequisites

- Register at [football-data.org](https://www.football-data.org) for a free API key (instant approval)
- Add $10 credit to Anthropic Console at [console.anthropic.com](https://console.anthropic.com)
- Create a personal Azure subscription (separate from SHB/DLAB to avoid consuming the one-per-subscription Cosmos DB free tier)
- Create Cosmos DB account with free tier opt-in enabled — this must be selected at account creation time and cannot be added retroactively
- Disable or configure aggressive sampling on Application Insights to avoid unexpected Log Analytics charges

-----

## Research & References

| Resource                   | URL                                                                     | Purpose                             |
|----------------------------|-------------------------------------------------------------------------|-------------------------------------|
| football-data.org          | <https://www.football-data.org>                                         | Live WC fixture and standings data  |
| Anthropic Console          | <https://console.anthropic.com>                                         | Claude API access and billing       |
| Azure Cosmos DB Free Tier  | <https://learn.microsoft.com/en-us/azure/cosmos-db/free-tier>           | Free tier eligibility and limits    |
| Azure Functions Pricing    | <https://azure.microsoft.com/en-us/pricing/details/functions/>          | Consumption plan free grant details |
| Azure Static Web Apps      | <https://azure.microsoft.com/en-us/pricing/details/app-service/static/> | Free hobby tier details             |
| FIFA World Cup 2026 Groups | <https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026> | Official group draw and schedule    |
