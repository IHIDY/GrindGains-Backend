# Deploying and running your own

The stack, how to deploy it, how to mint invite codes, and the permissions each function has.

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

## Known gaps and hardening ideas

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
