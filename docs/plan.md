# Implementation Plan

> Generated from [Architecture](architecture.md)
> **Last Updated**: 2026-06-02

## Phase 1: Setup & Scaffolding

- [x] 1. Initialise directory structure: create `infra/`, `functions/`, `frontend/`, `pipelines/` folders
- [x] 2. Initialise Python project in `functions/` with `uv init`; add runtime deps (`azure-functions`, `azure-cosmos`, `azure-storage-queue`, `anthropic`, `httpx`) and dev deps (`pytest`, `pytest-asyncio`, `ruff`, `mypy`)
- [x] 3. Create `functions/host.json` and `functions/local.settings.json.template` with Azurite connection strings as placeholders; add `local.settings.json` to `.gitignore`
- [x] 4. Scaffold React app in `frontend/` using Vite (`npm create vite@latest`)
- [x] 5. Add top-level `.gitignore` entries: `.venv`, `__pycache__`, `dist/`, `node_modules/`, `local.settings.json`

## Phase 2: Core Domain

- [x] 6. Write `infra/main.bicep`: provision Storage Account, Key Vault, Cosmos DB account with free tier and 4 containers (`teams`, `fixtures`, `predictions`, `scores`), Function App (Consumption plan), and Static Web App
- [x] 7. Implement `functions/shared/cosmos.py`: upsert and point-read helpers for all four containers
- [x] 8. Implement `functions/shared/api_football.py`: HTTP client wrapping API-Football v3 `GET /teams`, `GET /fixtures`, `GET /standings`; normalise `"Group Stage - N"` round strings to integers `1`/`2`/`3`
- [x] 9. Implement `fn_ingest` Timer Trigger: on first run seed `teams` container from `GET /teams`; on every run fetch fixtures via `GET /fixtures` and upsert to `fixtures` container
- [x] 10. Extend `fn_ingest`: after each upsert compare incoming fixture `status` against stored value; enqueue a message to the `predict-trigger` Storage Queue for every fixture that transitions to `FINISHED`
- [x] 11. Implement `fn_predict` Queue Trigger: read `fixtures` and `teams` from Cosmos DB; build a structured prompt with group standings, team form, and FIFA rankings for all 12 groups
- [x] 12. Extend `fn_predict`: call Claude API (`claude-haiku-4-5`) with the prompt; parse JSON response; write idempotent prediction document to `predictions` container keyed by matchday
- [x] 13. Implement accuracy scoring in `fn_predict`: after writing predictions, compare against completed fixtures; award one point per group where **both** winner and runner-up match; write result to `scores` container
- [x] 14. Implement `fn_api` HTTP Trigger — `GET /groups`: query `fixtures` for latest standings grouped by group letter; return all 12 groups
- [x] 15. Implement `fn_api` remaining endpoints: `GET /predictions` (latest prediction doc), `GET /fixtures/{matchday}` (fixtures by matchday integer), `GET /accuracy` (latest scores doc with per-group breakdown)

## Phase 3: API / Interface

- [x] 16. Build React **Groups View**: fetch `GET /predictions`; render all 12 groups (A–L) each showing predicted winner, runner-up, and Claude reasoning blurb
- [x] 17. Build React **Fixtures View**: fetch `GET /fixtures/{matchday}`; render upcoming and completed matches with scores, kickoff times, and status per group; include matchday tab selector
- [x] 18. Build React **Accuracy View**: fetch `GET /accuracy`; render overall score (e.g. 8/12) and a per-group row showing predicted vs actual with correct/incorrect indicator
- [x] 19. Wire frontend to `fn-api` using an environment variable (`VITE_API_BASE_URL`) so the base URL is injected at build time by the Azure DevOps pipeline
- [x] 20. Apply responsive layout and basic styling (CSS modules or Tailwind); ensure all three views are usable on mobile

## Phase 4: Testing & QA

- [x] 21. Unit tests for `shared/api_football.py`: mock HTTP responses; assert correct parsing of fixtures, standings, and team data; assert round-string-to-integer normalisation
- [x] 22. Unit tests for `fn_ingest`: assert teams seeded on first run only; assert fixture upsert; assert correct detection of `FINISHED` transitions and queue message content
- [x] 23. Unit tests for `fn_predict`: assert prompt construction includes all 12 groups; assert idempotent write (second call with same matchday overwrites, not duplicates); assert malformed Claude response is handled gracefully
- [x] 24. Unit tests for accuracy scoring: assert strict scoring (both winner and runner-up must match); assert partial match scores zero; assert max score of 12
- [x] 25. Unit tests for `fn_api`: assert response shapes match architecture spec for all four endpoints; assert 404 for unknown matchday
- [x] 26. Local integration test: start Azurite and Functions Core Tools; run `fn_ingest` with fixture stub data; verify queue message triggers `fn_predict`; verify `fn_api` returns expected data end-to-end

## Phase 5: CI/CD & Deployment

- [x] 27. Write `pipelines/azure-pipelines.yml` with three stages: `infra` (`az deployment group create` on `main.bicep`), `functions` (`uv sync` → zip → `az functionapp deploy`), `frontend` (`npm ci && npm run build` → `AzureStaticWebApp@0`)
- [x] 28. Add Key Vault secret provisioning to the `infra` stage: write `apisports-api-key`, `anthropic-api-key`, and `cosmos-connection-string` from Azure DevOps variable group; grant Function App managed identity `Key Vault Secrets User` role via Bicep output
- [x] 29. Deploy to Azure via pipeline; run smoke tests: call each `fn_api` endpoint and assert HTTP 200; verify `fn_ingest` executes on schedule and writes to Cosmos DB
- [x] 30. Cost check: after first live tournament day confirm Azure portal shows $0.00 usage across all services and Claude spend is within budget

## Phase 6: Deployment Setup & Go-Live

- [ ] 31. Create external service accounts: register at api-sports.io for a free API key (100 req/day, instant approval); add $10 credit at Anthropic Console and copy the API key; keep both keys ready for the ADO variable group
- [x] 32. Create a dedicated Azure subscription (Cosmos DB free tier is one per subscription — do not share with an existing sub); log in with `az login`; create the resource group: `az group create --name rg-wc2026 --location eastus`
- [ ] 33. In Azure DevOps create an organisation and project; create a service connection named exactly `wc2026-service-connection` (Azure Resource Manager, scoped to the `rg-wc2026` resource group) and grant it access to all pipelines
- [ ] 34. Create variable group `wc2026-secrets` in ADO Library; add `APISPORTS_API_KEY` and `ANTHROPIC_API_KEY` as locked secret variables; link the group to the pipeline
- [ ] 35. Register the pipeline against `pipelines/azure-pipelines.yml` and trigger a first run — the `infra` stage provisions all Azure resources (Storage, Cosmos DB, Key Vault, Function App, Static Web App) and writes the three Key Vault secrets
- [ ] 36. After the `infra` stage completes, retrieve the Static Web App deployment token: `az staticwebapp secrets list --name <swa-name> --resource-group rg-wc2026 --query "properties.apiKey" --output tsv`; add it as `AZURE_STATIC_WEB_APPS_API_TOKEN` in the variable group; re-run the `frontend` and `smoke` pipeline stages
- [ ] 37. Verify portal state: Cosmos DB free tier discount shows "Applied"; four containers present (`teams`, `fixtures`, `predictions`, `scores`); Key Vault holds three secrets; Function App system-assigned managed identity is On; `KEY_VAULT_URI` appears in Function App application settings; three functions listed (`fn_ingest`, `fn_predict`, `fn_api`)
- [ ] 38. Run smoke tests against the live Function App: `python scripts/smoke_test.py https://<func-app>.azurewebsites.net/api`; assert all four endpoints return expected HTTP status codes and response shapes
- [ ] 39. Trigger `fn_ingest` manually and confirm 48 team documents appear in the Cosmos DB `teams` container; navigate to the Static Web App URL and verify all three views (Groups, Fixtures, Accuracy) load with no browser console errors and no CORS or 401 responses from fn-api
