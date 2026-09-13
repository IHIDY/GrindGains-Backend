# TrainingGPT — MVP Backend

Invite-only, multi-user backend for a personal training tracker (sets/reps +
isometric time-under-tension), built on a Lambda behind a Function URL. No
API Gateway — that means no built-in Cognito authorizer either, so the
Lambda verifies the caller's Cognito ID token itself.

## Stack

- **IaC:** AWS SAM (`template.yaml`)
- **Compute:** 2 Lambda functions (Python 3.11, arm64):
  - `TrainingLogsFunction` — the API, routed by HTTP method behind the
    Function URL (`src/app.py`)
  - `InviteCodeValidatorFunction` — a Cognito Pre Sign-up trigger that gates
    registration behind a one-time invite code (`src/invite_trigger.py`).
    Kept as a separate function on purpose: it can't share the API
    function's env vars without CloudFormation rejecting the template as a
    circular dependency (User Pool → trigger function → User Pool)
- **Storage:** 1 DynamoDB table (`TrainingLogs`), on-demand billing — also
  holds invite code items (`PK=INVITECODE#<code>`) and claimed-username
  items (`PK=USERNAME#<lowercased name>`)
- **Auth:** Amazon Cognito User Pool (free tier: 50,000 MAU), registration
  gated by invite code and (if supplied) a unique `preferred_username` —
  the frontend signs users in and sends their ID token; the Lambda verifies
  it on every request (see `src/auth.py`)
- **API:** Lambda Function URL with CORS enabled (`AuthType: NONE` — auth is
  enforced in application code instead of via AWS SigV4)

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

## Deploy

`PyJWT[crypto]` (used to verify Cognito tokens) has a compiled C extension
(`cryptography`), so it must be built for Amazon Linux, not your host OS.
**Build with `--use-container`** (requires Docker Desktop running) so SAM
builds it correctly regardless of what machine you're on:

```bash
sam build --use-container
sam deploy --guided
```

Grab `FunctionUrl`, `UserPoolId`, and `UserPoolClientId` from the stack
outputs — the frontend needs all three.

## Invite codes

Registration is closed by default — `SignUp` fails unless the caller passes
a valid, unused invite code. Generate some:

```bash
python3 scripts/create_invite_codes.py --count 5 --region ca-central-1
```

This prints N random 8-character codes and writes each as an unused item in
`TrainingLogs` (`PK=INVITECODE#<code>`, `SK=STATUS`). Hand codes out to
whoever you want to let in; each one works for exactly one sign-up
(`src/invite_trigger.py` consumes it atomically, so two people racing on the
same code can't both get in). Re-run the script any time you need more.

## Username uniqueness

Cognito is configured with `UsernameAttributes: [email]`, so email
uniqueness is already enforced natively — no work needed there. But Cognito
can't also natively dedupe a separate `preferred_username` attribute in
this configuration (`UsernameAttributes` and `AliasAttributes` are mutually
exclusive, and switching to the latter would mean recreating the pool), so
`invite_trigger.py` enforces it manually: **if** the sign-up includes a
`preferred_username`, it atomically claims `PK=USERNAME#<name.lower()>` in
the same table (case-insensitive — `CoolGymRat` and `coolgymrat` collide on
purpose). If that name's already claimed, sign-up is rejected with `That
username is already taken.`. If no `preferred_username` is sent, this check
is skipped entirely (it's optional, not required).

This runs in the **same DynamoDB transaction** as the invite-code check
(`TransactWriteItems`), not as two separate writes — otherwise a sign-up
could claim the username and then fail the invite-code check (or vice
versa), permanently locking a username to a signup that never completed.
Either both succeed or neither does.

## Frontend integration

The frontend needs to authenticate users against the Cognito User Pool
(`UserPoolId` / `UserPoolClientId` from the outputs above) and get an **ID
token** back — e.g. via [AWS Amplify Auth](https://docs.amplify.aws/) or
[`amazon-cognito-identity-js`](https://github.com/aws-amplify/amplify-js/tree/main/packages/amazon-cognito-identity-js).
Users sign up (email + password + **invite code**), confirm their email,
sign in, and the library hands back `idToken`.

Sign-up must pass the invite code as `ClientMetadata` (not a regular user
attribute) so `invite_trigger.py` can read it from
`event.request.clientMetadata`. If you want a unique display name, pass it
as the real `preferred_username` **user attribute** (not clientMetadata) —
that's a standard Cognito attribute, no schema changes needed on our end:

```js
// amazon-cognito-identity-js
const attributeList = [
  new CognitoUserAttribute({ Name: "preferred_username", Value: username }), // optional
];
userPool.signUp(
  email,
  password,
  attributeList,
  [], // validationData
  callback,
  { invite_code: inviteCode } // clientMetadata
);
```

If the username's taken, `SignUp` fails with `That username is already
taken.` — same error-surfacing mechanism as an invalid invite code, so
handle both the same way on the frontend (show the message from the
caught error).

Then send the ID token on every API call:

```js
fetch(FUNCTION_URL, {
  method: "POST",
  headers: {
    "content-type": "application/json",
    "authorization": `Bearer ${idToken}`,
  },
  body: JSON.stringify({ ... }),
});
```

ID tokens expire after 1 hour (see `AccessTokenValidity`/`IdTokenValidity`
in `template.yaml`); use the pool's refresh token to get a new one rather
than re-prompting login each time.

### Testing without a frontend

Create an invite code, then a test user, then get a token via the AWS CLI:

```bash
python3 scripts/create_invite_codes.py --count 1 --region ca-central-1
# -> copy the printed code into INVITE_CODE below

aws cognito-idp sign-up \
  --client-id "$USER_POOL_CLIENT_ID" \
  --username you@example.com --password 'SomeStr0ngPassw0rd' \
  --client-metadata invite_code="$INVITE_CODE"

aws cognito-idp admin-confirm-sign-up \
  --user-pool-id "$USER_POOL_ID" --username you@example.com

aws cognito-idp initiate-auth \
  --client-id "$USER_POOL_CLIENT_ID" \
  --auth-flow USER_PASSWORD_AUTH \
  --auth-parameters USERNAME=you@example.com,PASSWORD='SomeStr0ngPassw0rd'
# -> copy AuthenticationResult.IdToken from the response
```

Then (see **API reference** above for the full request/response shapes):

```bash
curl -X POST "$FUNCTION_URL" \
  -H 'content-type: application/json' \
  -H "authorization: Bearer $ID_TOKEN" \
  -d '{
        "movement_id": "pushup",
        "mode": "isotonic",
        "weight": 0,
        "reps_or_time": 20,
        "sets": 3
      }'

curl "$FUNCTION_URL?movement_id=pushup" -H "authorization: Bearer $ID_TOKEN"  # one movement's history
curl "$FUNCTION_URL" -H "authorization: Bearer $ID_TOKEN"                    # every movement, latest entry each
```

## Auth details

`src/auth.py` fetches the User Pool's public JWKS, verifies the token's
signature/issuer/audience/expiry, checks `token_use == "id"` (rejects
access tokens, which lack the identity claims this app relies on), and
returns the `sub` claim. `src/app.py` returns `401` if that check fails for
any reason (missing header, expired token, wrong pool, tampered signature,
etc.) before touching DynamoDB.

Nothing secret is stored in this repo — Cognito manages credentials, and
there's no shared static key anywhere in `template.yaml` or the source, so
it's safe to push this repo publicly.

## IAM

Each function has its own least-privilege role, scoped to the `TrainingLogs`
table ARN only:

- `TrainingLogsFunction`: `dynamodb:PutItem`, `dynamodb:Query` (training log
  items only — it never touches invite codes or claimed usernames)
- `InviteCodeValidatorFunction`: `dynamodb:UpdateItem`, `dynamodb:PutItem`
  (invite code / username items only — it never touches training log
  items). Both actions are needed because the two checks run together in
  one `TransactWriteItems` call; IAM authorizes each item in a transaction
  by its underlying action, same as if you'd called `UpdateItem`/`PutItem`
  individually — there's no separate "transaction" permission.

## Error handling & input validation

`app.py` never returns raw exception text to the caller — unexpected errors
log full detail to CloudWatch (`logger.exception`) but the HTTP response is
just a generic `{"error": "Internal error"}`, so internal boto3/DynamoDB
error strings can't leak to callers. `movement_id`, `weight`,
`reps_or_time`, `sets`, and `rpe` are all validated (type and, for
`movement_id`, character set/length; for `rpe`, the 1-10 range) before
anything touches DynamoDB, so malformed input gets a clean `400` instead of
falling through to a generic `500`.

## Notes / follow-ups for later hardening

- Deploying with **root AWS credentials** works but isn't great practice —
  switch to a scoped-down IAM user/role for deploys when convenient.
- No rate limiting on the Function URL (unlike API Gateway, it has no
  built-in throttling) — fine at personal scale, but there's no backstop
  against a scripted flood.
- No pagination on either `GET` mode — fine at MVP scale; add
  `LastEvaluatedKey` handling if a movement's log history (or a user's
  total movement count) grows large. The no-`movement_id` mode in
  particular queries every log item a user has ever written (to dedupe
  down to one-per-movement), so it's the one to watch first.
- No sign-up/forgot-password UI is included here — that's on the frontend,
  using Amplify Auth or the Cognito Hosted UI.
