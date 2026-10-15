# API and data model

Request and response shapes, the data model and error handling for the GrindGains API. This is the canonical copy of the API contract.

## Data model (single-table design)

| Field | Value |
|---|---|
| PK | `USER#<user_id>` (`user_id` = the caller's Cognito `sub`, taken from their verified ID token) |
| SK | `MOVEMENT#<movement_id>#LOG#<timestamp_iso8601>` |
| `mode` | `"isotonic"` \| `"mobeta"` |
| `weight` | Number |
| `reps_or_time` | Number (reps for isotonic, seconds for mobeta) |
| `sets` | Number (defaults to 1) |
| `rpe` | Number, 1-10 (optional, omitted when not provided) |

Each user only ever sees their own `USER#<sub>` partition — there's no way
for one signed-in user to read or write another's logs.

`PK`/`SK` are internal storage details and never appear in API
responses — see **API reference** below for the actual response shape.

## API reference

No API Gateway means no path-based routing — every request hits the same
`FunctionUrl`, differentiated by HTTP method (and, for `GET`, a query
param). Every request needs `Authorization: Bearer <ID token>`; anything
without a valid one gets `401`.

### `POST` — log a set/hold

```
POST {FunctionUrl}
Headers: content-type: application/json, authorization: Bearer <ID token>
Body:
{
  "movement_id": "pushup",   // required, 1-128 chars: letters/digits/_/-
  "mode": "isotonic",        // required, "isotonic" | "mobeta"
  "weight": 0,                // required, number
  "reps_or_time": 20,         // required, number (reps for isotonic, seconds for mobeta)
  "sets": 3,                  // optional, number, defaults to 1
  "rpe": 8                    // optional, number, 1-10
}
```

`201` on success, body is the created entry:
```json
{"movement_id": "pushup", "timestamp": "2026-09-07T18:41:00.067781Z", "mode": "isotonic", "weight": 0, "reps_or_time": 20, "sets": 3, "rpe": 8}
```
`rpe` is `null` in the response when it wasn't provided on the request.

### `PUT` — edit an existing set/hold

Identifies the entry to overwrite by `movement_id` + `timestamp` (the exact
`timestamp` string a prior `POST`/`GET` returned for it — that's the SK
under the hood). All fields are re-sent in full; there's no partial patch.

```
PUT {FunctionUrl}
Headers: content-type: application/json, authorization: Bearer <ID token>
Body:
{
  "movement_id": "pushup",                        // required, must match the existing entry
  "timestamp": "2026-09-07T18:41:00.067781Z",     // required, identifies which entry to edit
  "mode": "isotonic",                             // required
  "weight": 185,                                  // required, number
  "reps_or_time": 8,                              // required, number
  "sets": 1,                                      // optional, number, defaults to 1
  "rpe": 8.5                                      // optional, number, 1-10
}
```

`200` on success, body is the updated entry (same shape as `POST`'s
response). `404` if no entry exists for that `movement_id` + `timestamp`
under the caller's own user — it never creates a new entry.

### `GET ?movement_id=<id>` — history for one movement

`200`, body is an array of entries (same shape as the `POST` response),
oldest first:
```json
[
  {"movement_id": "pushup", "timestamp": "2026-09-07T18:41:00.067781Z", "mode": "isotonic", "weight": 0, "reps_or_time": 20, "sets": 3, "rpe": 8},
  {"movement_id": "pushup", "timestamp": "2026-09-07T18:41:00.555374Z", "mode": "isotonic", "weight": 0, "reps_or_time": 25, "sets": 4, "rpe": null}
]
```
Reverse client-side if you want most-recent-first.

### `GET` (no `movement_id`) — list every movement this user has logged

For a dashboard/list page that needs to know "what movements does this user
have" before it can query any of them individually. `200`, body is an array
with **one entry per movement_id — the most recent one**:
```json
[
  {"movement_id": "plank", "timestamp": "2026-09-07T18:41:00.399294Z", "mode": "mobeta", "weight": 0, "reps_or_time": 45, "sets": 1, "rpe": null},
  {"movement_id": "pushup", "timestamp": "2026-09-07T18:41:00.555374Z", "mode": "isotonic", "weight": 0, "reps_or_time": 25, "sets": 4, "rpe": 8}
]
```

### Errors

| Scenario | Status | Body |
|---|---|---|
| Missing/expired/invalid token | 401 | `{"error": "Unauthorized"}` |
| Missing field, bad type, invalid `mode`/`movement_id`/`rpe` out of range | 400 | `{"error": "<what's wrong>"}` |
| `PUT` targeting a `movement_id`/`timestamp` with no matching entry | 404 | `{"error": "<what's wrong>"}` |
| Anything unexpected | 500 | `{"error": "Internal error"}` (no internal detail leaked; full trace goes to CloudWatch) |

## Error handling & input validation

`app.py` never returns raw exception text to the caller — unexpected errors
log full detail to CloudWatch (`logger.exception`) but the HTTP response is
just a generic `{"error": "Internal error"}`, so internal boto3/DynamoDB
error strings can't leak to callers. `movement_id`, `weight`,
`reps_or_time`, `sets`, and `rpe` are all validated (type and, for
`movement_id`, character set/length; for `rpe`, the 1-10 range) before
anything touches DynamoDB, so malformed input gets a clean `400` instead of
falling through to a generic `500`.
