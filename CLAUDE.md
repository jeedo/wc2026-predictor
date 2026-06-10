# Claude Instructions

## Session Start

Always read at the beginning of every session:
- [`docs/architecture.md`](docs/architecture.md) — system design and decisions
- [`docs/plan.md`](docs/plan.md) — phased task list with completion status

Then run `python scripts/check_docs.py` and surface any failures to the user before proceeding.

---

## Starting a New Project

When the user defines a project goal:

1. **Architecture first** — collaborate to fill in `docs/architecture.md` section by section. Do not write any code until the user approves it.
2. **Plan second** — only after architecture approval, generate `docs/plan.md` with numbered, phased tasks derived from the architecture.
3. **No implementation** until both documents are approved by the user.

### Required sections in `docs/architecture.md`
- Overview & Goals
- Tech Stack
- System Components
- Data Model / API
- Link to `docs/research.md` if additional research was performed

### Default phases in `docs/plan.md`
- Phase 1: Setup & Scaffolding
- Phase 2: Core Domain
- Phase 3: API / Interface
- Phase 4: Testing & QA
- Phase 5: CI/CD & Deployment

---

## Implementing a Feature

When the user asks to implement a task from `docs/plan.md`:

1. Identify the task number
2. Create a branch: `git checkout -b feature/<task-number>-<short-slug>`
3. **Write tests first** — run them and confirm they **fail** (red phase)
4. Implement the feature until all tests pass (green phase)
5. Mark the task complete: `python scripts/complete_task.py <task-number>`
6. Before committing, run `uv run pytest` and `uv run mypy fn_predict fn_api fn_ingest shared --ignore-missing-imports` — both must pass clean
7. Commit using a conventional commit message (includes the updated `docs/plan.md`)
7. Push and open a PR: `gh pr create`

---

## Branching

- Always branch from `main` — never commit directly to `main`
- Name format: `feature/<task-number>-<short-slug>` (e.g. `feature/7-add-jwt-auth`)

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

## Task Management Scripts

Run from the project root:

| Script | Usage | Description |
|--------|-------|-------------|
| `check_docs.py` | `python scripts/check_docs.py` | Validate architecture.md and plan.md (required sections, numbering, TBD markers) |
| `renumber_tasks.py` | `python scripts/renumber_tasks.py` | Restore sequential numbering after adding/removing tasks |
| `complete_task.py` | `python scripts/complete_task.py <N>` | Mark task N as complete |
| `get_phase_tasks.py` | `python scripts/get_phase_tasks.py <phase>` | List tasks for a phase (by name or number) |

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
