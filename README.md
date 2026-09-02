# TrainingGPT — MVP Backend

Single-Lambda, single-DynamoDB-table backend for a personal training tracker
(sets/reps + isometric time-under-tension). No API Gateway — the API is
exposed directly via a Lambda Function URL to avoid any per-route cost.

## Stack

- **IaC:** AWS SAM (`template.yaml`)
- **Compute:** 1 Lambda function (Python 3.11, arm64), routed by HTTP method
- **Storage:** 1 DynamoDB table (`TrainingLogs`), on-demand billing
- **API:** Lambda Function URL with CORS enabled, no auth (`AuthType: NONE`)

## Data model (single-table design)

| Field | Value |
|---|---|
| PK | `USER#ME` (hardcoded single user for the MVP) |
| SK | `MOVEMENT#<movement_id>#LOG#<timestamp_iso8601>` |
| `mode` | `"isotonic"` \| `"mobeta"` |
| `weight` | Number |
| `reps_or_time` | Number (reps for isotonic, seconds for mobeta) |
| `sets` | Number (defaults to 1) |

## Deploy

```bash
sam build
sam deploy --guided   # first time; creates samconfig.toml
```

Grab the Function URL from the stack outputs (`FunctionUrl`).

## Usage

Log a set:

```bash
curl -X POST "$FUNCTION_URL" \
  -H 'content-type: application/json' \
  -d '{
        "movement_id": "pushup",
        "mode": "isotonic",
        "weight": 0,
        "reps_or_time": 20,
        "sets": 3
      }'
```

Log an isometric hold:

```bash
curl -X POST "$FUNCTION_URL" \
  -H 'content-type: application/json' \
  -d '{
        "movement_id": "plank",
        "mode": "mobeta",
        "weight": 0,
        "reps_or_time": 60
      }'
```

Fetch logs for a movement:

```bash
curl "$FUNCTION_URL?movement_id=pushup"
```

## IAM

The Lambda execution role is scoped to exactly two actions
(`dynamodb:PutItem`, `dynamodb:Query`) on the `TrainingLogs` table ARN only —
see the inline `Policies` statement in `template.yaml`.

## Notes / follow-ups for later hardening

- `AuthType: NONE` means the Function URL is publicly invocable by anyone
  with the URL. Fine for a personal MVP; revisit (e.g. `AWS_IAM` auth, a
  shared secret header checked in the handler, or Cognito) before this
  holds anything sensitive or gets a real frontend.
- No pagination on `GET` — fine at MVP scale; add `LastEvaluatedKey`
  handling if a movement's log history grows large.
