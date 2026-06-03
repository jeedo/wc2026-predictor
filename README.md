# FIFA World Cup 2026 Prediction System

An AI-powered prediction system for the FIFA World Cup 2026 group stage, built on Azure serverless architecture. Generates Claude-powered predictions for group winners, runners-up, and match outcomes.

## Quick Start

### View Predictions

**Groups & Predictions:**
```bash
curl https://func-wc2026-zwn7h5hfxftt2.azurewebsites.net/api/groups
```

**Latest Predictions:**
```bash
curl https://func-wc2026-zwn7h5hfxftt2.azurewebsites.net/api/predictions
```

**Fixtures by Matchday:**
```bash
curl https://func-wc2026-zwn7h5hfxftt2.azurewebsites.net/api/fixtures/1
```

**Accuracy Tracking:**
```bash
curl https://func-wc2026-zwn7h5hfxftt2.azurewebsites.net/api/accuracy
```

---

## Manual Prediction Triggering

### Option 1: Restart Function App (Immediate)

Restarting the Function App kicks off fn_ingest immediately, which fetches fresh data and generates predictions.

**Via Azure CLI:**
```bash
az functionapp restart \
  --name func-wc2026-zwn7h5hfxftt2 \
  --resource-group rg-wc2026
```

**Via Azure Portal:**
1. Go to Azure Portal → Function App: `func-wc2026-zwn7h5hfxftt2`
2. Click **Restart** button (top menu bar)
3. Confirm restart
4. Wait 30 seconds for fn_ingest to run and fn_predict to process

---

### Option 2: Trigger Timer Manually (Azure Portal)

Manually invoke the timer trigger for fn_ingest:

1. Go to Azure Portal → Function Apps → `func-wc2026-zwn7h5hfxftt2`
2. Click **Functions** in the left menu
3. Select **fn_ingest**
4. Click **Code + Test** tab
5. Click **Test/Run** button
6. Click **Run** (uses the default timer trigger)
7. Check the output — should see "Seeded X teams" or fixture updates
8. Wait 30 seconds for fn_predict to process the queue messages

---

### Option 3: Monitor Progress in Application Insights

Track the prediction generation in real-time:

```bash
# View latest function executions
az monitor app-insights query \
  --app appinsights-wc2026 \
  --resource-group rg-wc2026 \
  --analytics-query "requests | order by timestamp desc | limit 10"

# View traces (logs)
az monitor app-insights query \
  --app appinsights-wc2026 \
  --resource-group rg-wc2026 \
  --analytics-query "traces | order by timestamp desc | limit 20"

# View exceptions
az monitor app-insights query \
  --app appinsights-wc2026 \
  --resource-group rg-wc2026 \
  --analytics-query "exceptions | order by timestamp desc | limit 10"
```

---

## How It Works

### Automatic Workflow (Every 6 Hours)

1. **fn_ingest (Timer)** — Runs on schedule: `0 0 */6 * * *`
   - Fetches latest fixtures and standings from API-Football
   - Detects when matches finish (transition to FT status)
   - Enqueues prediction requests to `predict-trigger` queue

2. **fn_predict (Queue)** — Triggered by queue messages
   - Reads fixture and team data from Cosmos DB
   - Calls Claude API with team/fixture context
   - Stores predictions in Cosmos DB

3. **fn_api (HTTP)** — On-demand queries
   - Serves groups, predictions, fixtures, accuracy stats
   - Joins prediction data with fixture information

### Manual Trigger Workflow

1. Manually restart Function App or invoke timer
2. fn_ingest runs immediately (same 6-hour cycle logic)
3. Queue messages enqueued for fn_predict
4. Predictions generated within 30-60 seconds
5. Available via `/api/predictions` and `/api/fixtures/{matchday}`

---

## API Endpoints

All endpoints return JSON and support CORS (access from frontend):

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/groups` | GET | All 12 groups with teams |
| `/api/predictions` | GET | Latest Claude predictions (all groups) |
| `/api/fixtures/{matchday}` | GET | Fixtures for matchday (1-3) with predictions |
| `/api/accuracy` | GET | Prediction accuracy after each matchday |
| `/api/usage` | GET | API call usage by provider (monitoring) |

---

## Architecture

- **Frontend**: Azure Static Web Apps (React + Vite)
- **API**: Azure Functions (HTTP trigger)
- **Ingestion**: Azure Functions (Timer trigger, 6-hour cycle)
- **Prediction**: Azure Functions (Queue trigger)
- **Database**: Azure Cosmos DB (NoSQL)
- **Queue**: Azure Queue Storage
- **Secrets**: Azure Key Vault
- **AI**: Claude API (claude-haiku)
- **Data Source**: API-Football v3

See `docs/architecture.md` for full technical details.

---

## Troubleshooting

### Predictions are stale (older than 6 hours)

1. **Restart fn_ingest immediately:**
   ```bash
   az functionapp restart --name func-wc2026-zwn7h5hfxftt2 --resource-group rg-wc2026
   ```

2. **Check queue messages:**
   ```bash
   az storage queue list --account-name $(az storage account list -g rg-wc2026 --query [0].name -o tsv)
   ```

3. **View fn_predict logs:**
   ```bash
   az monitor app-insights query --app appinsights-wc2026 -g rg-wc2026 \
     --analytics-query "exceptions | order by timestamp desc | limit 5"
   ```

### API returns 404 or error

1. Check if Function App is running:
   ```bash
   az functionapp show --name func-wc2026-zwn7h5hfxftt2 --resource-group rg-wc2026 \
     --query state
   ```

2. Restart if needed:
   ```bash
   az functionapp restart --name func-wc2026-zwn7h5hfxftt2 --resource-group rg-wc2026
   ```

3. Wait 30 seconds for cold start

---

## Development

### Local Setup

```bash
# Install dependencies
cd functions && uv sync

# Run tests
uv run pytest -q

# Run function locally
func start
```

### Add to Plan

To add tasks to the implementation plan:

```bash
python scripts/complete_task.py <task_number>
```

View the plan:
```bash
cat docs/plan.md
```

---

## Cost

- **Azure Functions**: Free tier (1M executions/month)
- **Cosmos DB**: Free tier (1,000 RU/s, 25GB)
- **Static Web Apps**: Free tier
- **Claude API**: ~$0.14 per prediction (36 predictions for tournament)
- **Total estimate**: ~$0.20 for entire tournament

---

## Links

- **Architecture**: `docs/architecture.md`
- **Implementation Plan**: `docs/plan.md`
- **Live Frontend**: https://lively-ocean-05da39a0f.7.azurestaticapps.net
- **API Base**: https://func-wc2026-zwn7h5hfxftt2.azurewebsites.net

---

## Support

For issues or questions:
1. Check Application Insights logs (traces/exceptions)
2. Review `docs/architecture.md` for system design
3. Check recent function execution in Azure Portal

Last updated: June 2026
