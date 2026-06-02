# Implementation Plan

> Generated from [Architecture](architecture.md)
> **Last Updated**: 2026-06-02

## Phase 1: Setup & Scaffolding

- [x] 1. Initialise directory structure: create `infra/`, `functions/`, `frontend/`, `pipelines/` folders
- [x] 2. Initialise Python project in `functions/` with `uv init`; add runtime deps (`azure-functions`, `azure-cosmos`, `azure-storage-queue`, `anthropic`, `httpx`) and dev deps (`pytest`, `pytest-asyncio`, `ruff`, `mypy`)
- [x] 3. Create `functions/host.json` and `functions/local.settings.json.template` with Azurite connection strings as placeholders; add `local.settings.json` to `.gitignore`
- [ ] 4. Scaffold React app in `frontend/` using Vite (`npm create vite@latest`)
- [x] 5. Add top-level `.gitignore` entries: `.venv`, `__pycache__`, `dist/`, `node_modules/`, `local.settings.json`

## Phase 2: Core Domain

- [ ] 6. Write `infra/main.bicep`: provision Storage Account, Key Vault, Cosmos DB account with free tier and 4 containers (`teams`, `fixtures`, `predictions`, `scores`), Function App (Consumption plan), and Static Web App
- [ ] 7. Implement `functions/shared/cosmos.py`: upsert and point-read helpers for all four containers
- [ ] 8. Implement `functions/shared/api_football.py`: HTTP client wrapping API-Football v3 `GET /teams`, `GET /fixtures`, `GET /standings`; normalise `"Group Stage - N"` round strings to integers `1`/`2`/`3`
- [ ] 9. Implement `fn_ingest` Timer Trigger: on first run seed `teams` container from `GET /teams`; on every run fetch fixtures via `GET /fixtures` and upsert to `fixtures` container
- [ ] 10. Extend `fn_ingest`: after each upsert compare incoming fixture `status` against stored value; enqueue a message to the `predict-trigger` Storage Queue for every fixture that transitions to `FINISHED`
- [ ] 11. Implement `fn_predict` Queue Trigger: read `fixtures` and `teams` from Cosmos DB; build a structured prompt with group standings, team form, and FIFA rankings for all 12 groups
- [ ] 12. Extend `fn_predict`: call Claude API (`claude-haiku-4-5`) with the prompt; parse JSON response; write idempotent prediction document to `predictions` container keyed by matchday
- [ ] 13. Implement accuracy scoring in `fn_predict`: after writing predictions, compare against completed fixtures; award one point per group where **both** winner and runner-up match; write result to `scores` container
- [ ] 14. Implement `fn_api` HTTP Trigger — `GET /groups`: query `fixtures` for latest standings grouped by group letter; return all 12 groups
- [ ] 15. Implement `fn_api` remaining endpoints: `GET /predictions` (latest prediction doc), `GET /fixtures/{matchday}` (fixtures by matchday integer), `GET /accuracy` (latest scores doc with per-group breakdown)

## Phase 3: API / Interface

- [ ] 16. Build React **Groups View**: fetch `GET /predictions`; render all 12 groups (A–L) each showing predicted winner, runner-up, and Claude reasoning blurb
- [ ] 17. Build React **Fixtures View**: fetch `GET /fixtures/{matchday}`; render upcoming and completed matches with scores, kickoff times, and status per group; include matchday tab selector
- [ ] 18. Build React **Accuracy View**: fetch `GET /accuracy`; render overall score (e.g. 8/12) and a per-group row showing predicted vs actual with correct/incorrect indicator
- [ ] 19. Wire frontend to `fn-api` using an environment variable (`VITE_API_BASE_URL`) so the base URL is injected at build time by the Azure DevOps pipeline
- [ ] 20. Apply responsive layout and basic styling (CSS modules or Tailwind); ensure all three views are usable on mobile

## Phase 4: Testing & QA

- [ ] 21. Unit tests for `shared/api_football.py`: mock HTTP responses; assert correct parsing of fixtures, standings, and team data; assert round-string-to-integer normalisation
- [ ] 22. Unit tests for `fn_ingest`: assert teams seeded on first run only; assert fixture upsert; assert correct detection of `FINISHED` transitions and queue message content
- [ ] 23. Unit tests for `fn_predict`: assert prompt construction includes all 12 groups; assert idempotent write (second call with same matchday overwrites, not duplicates); assert malformed Claude response is handled gracefully
- [ ] 24. Unit tests for accuracy scoring: assert strict scoring (both winner and runner-up must match); assert partial match scores zero; assert max score of 12
- [ ] 25. Unit tests for `fn_api`: assert response shapes match architecture spec for all four endpoints; assert 404 for unknown matchday
- [ ] 26. Local integration test: start Azurite and Functions Core Tools; run `fn_ingest` with fixture stub data; verify queue message triggers `fn_predict`; verify `fn_api` returns expected data end-to-end

## Phase 5: CI/CD & Deployment

- [ ] 27. Write `pipelines/azure-pipelines.yml` with three stages: `infra` (`az deployment group create` on `main.bicep`), `functions` (`uv sync` → zip → `az functionapp deploy`), `frontend` (`npm ci && npm run build` → `AzureStaticWebApp@0`)
- [ ] 28. Add Key Vault secret provisioning to the `infra` stage: write `apisports-api-key`, `anthropic-api-key`, and `cosmos-connection-string` from Azure DevOps variable group; grant Function App managed identity `Key Vault Secrets User` role via Bicep output
- [ ] 29. Deploy to Azure via pipeline; run smoke tests: call each `fn_api` endpoint and assert HTTP 200; verify `fn_ingest` executes on schedule and writes to Cosmos DB
- [ ] 30. Cost check: after first live tournament day confirm Azure portal shows $0.00 usage across all services and Claude spend is within budget
