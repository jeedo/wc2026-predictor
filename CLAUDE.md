# Claude Instructions

## Session Start

Always read at the beginning of every session:
- [`docs/architecture.md`](docs/architecture.md) — system design and decisions

Then run `uv run python scripts/check_docs.py` and surface any failures to the user before proceeding.

---

## Working on a GitHub Issue

When the user asks to work on a GitHub issue:

1. **Read the issue**: `gh issue view <N>` — understand scope, acceptance criteria, and any constraints
2. **Plan phase** — if the issue body does not include a clear implementation plan:
   - If research is needed (unfamiliar API, new library, ambiguous approach), do it first
   - Write a concise plan: files to touch, data model changes, new tests needed, edge cases
   - Present the plan to the user and wait for approval before writing any code
3. **Branch**: `git checkout -b feature/<issue-number>-<short-slug>` — always from `main`
4. **Write tests first** — run them and confirm they **fail** (red phase)
5. **Implement** until all tests pass (green phase)
6. **Quality gate** — both must pass clean before committing:
   - `uv run pytest`
   - `uv run mypy fn_predict fn_api fn_ingest shared --ignore-missing-imports`
7. **Update `docs/architecture.md`** — reflect any changes made during implementation: new endpoints, schema changes, new containers, updated data flow, changed dependencies
8. **Commit** using a conventional commit message
9. **PR**: `gh pr create` — reference the issue number in the body

### When research is required

- Fetch API docs or relevant pages with `WebFetch`
- Call live APIs if real response shapes are needed to inform the implementation
- Search the codebase with `grep` or the Explore agent for existing patterns
- Check existing tests for conventions already in use
- **Write findings to `docs/research.md`** — include the question being answered, what was tried, actual API responses or relevant excerpts, and the conclusion; append under a dated heading if the file already exists
- Summarise the key conclusion in the plan before proposing implementation

---

## Branching

- Always branch from `main` — never commit directly to `main`
- Name format: `feature/<issue-number>-<short-slug>` (e.g. `feature/7-add-jwt-auth`)

---

## Commit Messages (Conventional Commits)

Format: `<type>(<scope>): <description>`

Types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`

Examples:
```
feat(auth): add JWT token validation
fix(api): handle empty upstream response
docs(arch): update data model section
test(auth): add edge cases for expired tokens
```

---

## Local UI Development

The frontend uses **MSW (Mock Service Worker)** so the full UI can be developed and tested without a live backend.

**Run with mock data (no Azure backend needed):**
```bash
cd frontend
npm run dev
```
MSW is automatically activated in dev mode (`import.meta.env.DEV`). All API routes (`/api/groups`, `/api/predictions`, `/api/fixtures/:matchday`, `/api/news/:team`, etc.) are intercepted and return realistic seed data from `src/mocks/data.js`.

**Adding or updating mock handlers:**
- Seed data lives in `frontend/src/mocks/data.js` — edit constants here to change what the UI shows
- Route handlers live in `frontend/src/mocks/handlers.js` — add new `http.get(...)` entries for new endpoints
- Handlers use relative paths (`/api/...`) so they match any origin (both Vite dev server and jsdom tests)

**Tests share the same handlers:**
- `src/test-setup.js` starts the MSW Node server before each test suite
- Tests use `server.use(http.get('/api/...', () => HttpResponse.json(...)))` for per-test overrides
- `server.resetHandlers()` in `afterEach` clears overrides automatically — no manual cleanup needed
- Do NOT use `vi.stubGlobal('fetch', ...)` — use `server.use()` instead

---

## Python Projects

- Always use `uv` — never pip, never poetry
- Add runtime dependency: `uv add <package>`
- Add dev dependency: `uv add --dev <package>`
- **Run Python locally: always use `uv run <command>`** — ensures the correct Python version (from `requires-python` in pyproject.toml) is used
  - Example: `uv run python scripts/check_docs.py` (not bare `python scripts/check_docs.py`)
  - Example: `uv run pytest` (not bare `pytest`)
  - For one-off scripts needing additional packages, use multiple `--with` flags
  - **Always add `--with python-dotenv` to load .env files:** `uv run --with anthropic --with python-dotenv python script.py`
- Never manually edit dependency lists in `pyproject.toml`

---

## GitHub

Use the `gh` CLI for all GitHub operations:

```bash
gh pr create --title "feat: ..." --body "..."
gh pr status
gh run list        # check CI status
gh issue list
gh issue view <N>  # read an issue before starting work
```

---

## Deployment & CI/CD

**Azure DevOps Pipeline Auto-Deploy:**
- `git push` to main triggers the Azure DevOps pipeline automatically
- **DO NOT run manual `func azure functionapp publish` after pushing to git** — the pipeline will handle it
- Manual deploys should only be used during local debugging/testing
- Check pipeline status via Azure DevOps portal or by waiting for logs to appear in App Insights (~2-3 min)

**Application Insights Logging:**
- `APPINSIGHTS_INSTRUMENTATIONKEY` and `APPLICATIONINSIGHTS_CONNECTION_STRING` are automatically configured by Bicep
- All function executions, exceptions, and traces are logged to App Insights (workspace-based)
- Data is in workspace-native tables — use `az monitor log-analytics query` not `az monitor app-insights query`
- Check logs with: `az monitor log-analytics query --workspace 73c43f55-5a43-4843-a85a-87baec2305d9 --analytics-query "AppTraces | order by TimeGenerated desc | limit 20"`
- Query examples:
  - Recent errors: `AppExceptions | where TimeGenerated > ago(30m) | order by TimeGenerated desc`
  - Failed requests: `AppRequests | where Success == false | order by TimeGenerated desc`
  - Function execution logs: `AppTraces | where OperationName contains 'fn_api' | order by TimeGenerated desc`

---

## Key Vault Secret Rotation

App Service / Function Apps cache KV secret values for up to **24 hours**. A function app restart alone does not flush the cache.

**Runbook for rotating a secret:**

1. Update the secret in Key Vault:
   ```bash
   az keyvault secret set --vault-name kv-wc2026-zwn7h5hfxftt2 --name <secret-name> --value "<new-value>"
   ```
2. Force the function app to re-fetch all KV references immediately (no restart needed):
   ```bash
   RESOURCE_ID=$(az functionapp show --name func-wc2026-zwn7h5hfxftt2 --resource-group rg-wc2026 --query id -o tsv)
   az rest --method POST \
     --url "https://management.azure.com${RESOURCE_ID}/config/configreferences/appsettings/refresh?api-version=2022-03-01"
   ```
   The response lists every KV-backed setting with `"status": "Resolved"` or an error detail.

3. Verify the target secret resolved:
   ```bash
   az rest --method POST \
     --url "https://management.azure.com${RESOURCE_ID}/config/configreferences/appsettings/refresh?api-version=2022-03-01" \
     --query "value[?name=='<SETTING_NAME>'].properties"
   ```

**Do not** set the app setting to a plain string as a workaround — always keep it as a KV reference and use the refresh API instead.

**Important — the pipeline overwrites KV secrets on every deploy:** `azure-pipelines.yml` runs Bicep on every push and passes secret values from the Azure DevOps variable group `wc2026-secrets`. If a secret is rotated, the pipeline will overwrite the KV secret back to the old value on the next run unless the pipeline variable is also updated.

**Runbook for rotating a secret end-to-end:**

1. Update the Azure DevOps pipeline variable (source of truth):
   ```bash
   az pipelines variable-group variable update \
     --org https://dev.azure.com/gede \
     --project Wc2026 \
     --group-id 1 \
     --name <VARIABLE_NAME> \
     --value "<new-value>" \
     --secret true
   ```
2. Update the KV secret directly so the running function picks it up immediately (without waiting for the next pipeline run):
   ```bash
   az keyvault secret set --vault-name kv-wc2026-zwn7h5hfxftt2 --name <secret-name> --value "<new-value>"
   ```
3. Force the function app to re-fetch the new KV value:
   ```bash
   RESOURCE_ID=$(az functionapp show --name func-wc2026-zwn7h5hfxftt2 --resource-group rg-wc2026 --query id -o tsv)
   az rest --method POST \
     --url "https://management.azure.com${RESOURCE_ID}/config/configreferences/appsettings/refresh?api-version=2022-03-01"
   ```

The variable group ID is **1** (`wc2026-secrets`). Variables: `SERPA_API_KEY`, `ANTHROPIC_API_KEY`, `FOOTBALL_DATA_API_KEY`, `APISPORTS_API_KEY`, `CosmosDbConnectionString`.

---

## Debugging & Monitoring

**Query Application Insights Logs:**

Use `debug/get_logs.py` to query logs from each function app:

```bash
# Get all data for fn_api in the last hour
uv run debug/get_logs.py fn_api

# Get all functions (default)
uv run debug/get_logs.py

# Look back 3 hours
uv run debug/get_logs.py fn_api --hours 3

# Get only requests (skip traces and exceptions)
uv run debug/get_logs.py fn_api --requests-only

# Get only exceptions
uv run debug/get_logs.py fn_api --exceptions-only

# Query with limit
uv run debug/get_logs.py fn_predict --limit 50
```

**Available functions:** `fn_api`, `fn_predict`, `fn_ingest`, or `all`

The script shows:
- 📊 Recent HTTP requests with status codes and response times
- 📝 Application trace logs at different severity levels
- ❌ Exceptions and errors
- ✅ Function app health status and uptime
