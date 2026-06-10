# Queue System Documentation

## Overview

The prediction system uses an Azure Storage Queue to asynchronously trigger prediction generation when match fixtures reach completion status.

## How the Queue is Used

### 1. Queue Enqueue Points

#### fn_ingest (Timer Trigger)
- **When**: Runs on a timer schedule to fetch fixtures from Football Data API
- **Enqueue Condition**: When a fixture status transitions from non-FT to FT (Finished)
- **Message Payload**: 
  ```json
  {
    "matchday": <int>,
    "fixtureId": <int>
  }
  ```
- **Queue Name**: `predict-trigger` (configurable via `PREDICT_QUEUE_NAME` env var)

#### fn_api (`/api/predictions/trigger` endpoint)
- **When**: Called manually via HTTP POST to trigger predictions
- **Payload**:
  ```json
  {
    "matchday": <int>,
    "fixtureId": null
  }
  ```
- **Purpose**: Allow on-demand prediction generation without waiting for fixtures to finish

### 2. Queue Processing

#### fn_predict (Queue Trigger)
- **Triggered By**: Queue message arrival
- **Processing**:
  1. Receives queue message with matchday and fixtureId
  2. Queries teams and fixtures from Cosmos DB
  3. Fetches group assignments from Football Data API standings
  4. Builds prediction prompt with actual team data and group assignments
  5. Calls Claude API to generate predictions using structured outputs
  6. Stores predictions in Cosmos DB (`predictions` container)
  7. If fixtures are finished, calculates accuracy scores

## Expected Behavior

### Happy Path
1. **Fixture Completion** → fn_ingest detects status change to "FT"
2. **Queue Message** → Enqueues `{matchday, fixtureId}` to predict-trigger queue
3. **Queue Processing** → fn_predict receives and processes message
4. **Prediction Generation** → Claude generates predictions for all 12 groups
5. **Storage** → Predictions stored in Cosmos DB with structure:
   ```
   {
     "id": "prediction-md<matchday>",
     "matchday": <int>,
     "generatedAt": <ISO timestamp>,
     "groups": [
       {
         "group": "A",
         "winner": "<team_name>",
         "runnerUp": "<team_name>",
         "confidence": "high|medium|low",
         "reasoning": "<text>",
         "matches": [...]
       },
       ...
     ]
   }
   ```

### API Integration
- **GET /api/predictions** → Returns latest predictions-all document
- **GET /api/fixtures/<matchday>** → Returns fixtures with attached predicted scores (if predictions exist)

## Potential Error Scenarios

### Error 1: Queue Message Not Dequeued
- **Symptom**: Message stays in queue, fn_predict doesn't trigger
- **Causes**:
  - fn_predict function app offline or not listening to queue
  - Queue authorization issues (missing connection string)
  - Malformed message structure
- **Recovery**: Manual `/api/predictions/trigger` endpoint or restart function app

### Error 2: Fixture Status Not Transitioning
- **Symptom**: Queue never receives messages even though matches finish
- **Cause**: `_should_enqueue()` condition not met
  - Status change from non-FT to FT required
  - If fixture already FT in database, no message sent
- **Expected Behavior**: Only first FT transition triggers queue
- **Impact**: Predictions not generated unless manually triggered

### Error 3: Claude API Call Failure
- **Symptom**: Predictions not stored, queue message consumed but no result
- **Causes**:
  - API key invalid or expired
  - Rate limit exceeded
  - Malformed prompt
- **Evidence**: Exception logged in fn_predict, message removed from queue (no retry)
- **Recovery**: Manual trigger via `/api/predictions/trigger` endpoint

### Error 4: Team Data Mismatch
- **Symptom**: Claude generates predictions but fixture-prediction matching fails (0/24 matched)
- **Root Cause**: Team name mismatch between:
  - Fixtures database (e.g., "Mexico")
  - Predictions generated (e.g., "Mexico")
  - Different naming conventions cause no matches
- **Resolution**: Use authoritative team names from standings API (now fixed)

### Error 5: Group Assignment Missing (DEAD LETTER QUEUE ISSUE)
- **Symptom**: Messages end up in dead letter queue, fn_predict crashes
- **Root Cause**: Prompt using hardcoded group assignments (USA, Spain, Germany, Brazil, etc.) but database had different teams (Mexico, South Korea, Czechia, etc.)
- **How It Happened**:
  1. fn_ingest enqueued message with matchday
  2. fn_predict received message and queried teams/fixtures from database
  3. _build_prompt() used hardcoded groups instead of actual database groups
  4. Prompt had mismatch: teams in database didn't match prompt's hardcoded groups
  5. Claude might have generated invalid JSON or predictions with wrong structure
  6. _parse_claude_response() failed or returned empty predictions
  7. Exception raised at line 273: `raise` rethrows error
  8. Azure Functions framework dead-letters the message (max retries exceeded)
- **Message Flow to Dead Letter**:
  ```
  Queue Message → fn_predict receives → Error occurs (prompt mismatch) 
  → Exception raised → fn_predict crashes → Message fails 
  → Retry attempt fails (same error) → Max retries exceeded 
  → Message moved to dead letter queue
  ```
- **Fixes Applied**:
  1. ✅ Made prompt use actual team data from database (line 100-104 in fn_predict)
  2. ✅ Extracted group derivation to shared module used by both fn_ingest and fn_api
  3. ✅ Now fetch groups from standings API (authoritative source) instead of deriving
  4. ✅ All 12 groups (A-L) now properly assigned and used in prompts

## Current Status

✅ **Queue System Operational**
- Messages enqueue successfully
- fn_predict processes messages correctly
- Predictions generate for all 12 groups
- Fixture-prediction matching: 100% (24/24 for matchday 1)

## Dead Letter Queue (DLQ) Handling

### When Messages Go to DLQ
Azure Functions automatically moves messages to the dead letter queue after:
- 5 dequeue attempts (default, configurable)
- Each with exponential backoff retry

### Monitor Dead Letter Queue
```bash
# Check dead letter queue size
az storage queue show --name predict-trigger-deadletter --account-name <storage_account>

# Peek at dead letter messages
az storage message peek --queue-name predict-trigger-deadletter --account-name <storage_account> --num-messages 10
```

### Recover From Dead Letter Queue
1. **Identify Root Cause**: Check fn_predict logs for the exception
2. **Fix Issue**: Update code (e.g., group assignments, prompt format)
3. **Redeploy**: Push fixes and wait for deployment
4. **Manual Retry**: Move messages back to main queue or manually trigger:
   ```bash
   curl -X POST "https://<function-app>/api/predictions/trigger" \
     -H "Content-Type: application/json" \
     -d '{"matchday": 1}'
   ```

## Monitoring

### Check Queue Depth
```bash
az storage queue show --name predict-trigger --account-name <storage_account>
```

### View Messages in Queue
```bash
az storage message peek --queue-name predict-trigger --account-name <storage_account>
```

### Check Function Logs
```bash
uv run debug/get_logs.py fn_predict --hours 1
```

### Early Warning Signs
Watch for:
- Queue depth increasing (messages not being processed)
- fn_predict exceptions in logs
- Messages appearing in dead letter queue
- fn_predict invocations but no predictions stored in Cosmos DB

## Related Documentation
- [Architecture](architecture.md) - System design
- [fn_ingest](../functions/fn_ingest/__init__.py) - Fixture ingestion and queue enqueue
- [fn_predict](../functions/fn_predict/__init__.py) - Queue processing and prediction generation
- [fn_api](../functions/fn_api/__init__.py) - HTTP endpoints including manual trigger
