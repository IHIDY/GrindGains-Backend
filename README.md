# TrainingGPT — MVP Backend

Multi-user backend for a personal training tracker (sets/reps + isometric
time-under-tension), built as a single Lambda behind a Function URL. No API
Gateway — that means no built-in Cognito authorizer either, so the Lambda
verifies the caller's Cognito ID token itself.

## Stack

- **IaC:** AWS SAM (`template.yaml`)
- **Compute:** 1 Lambda function (Python 3.11, arm64), routed by HTTP method
- **Storage:** 1 DynamoDB table (`TrainingLogs`), on-demand billing
- **Auth:** Amazon Cognito User Pool (free tier: 50,000 MAU) — the frontend
  signs users in and sends their ID token; the Lambda verifies it on every
  request (see `src/auth.py`)
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

Each user only ever sees their own `USER#<sub>` partition — there's no way
for one signed-in user to read or write another's logs.

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

## Frontend integration

The frontend needs to authenticate users against the Cognito User Pool
(`UserPoolId` / `UserPoolClientId` from the outputs above) and get an **ID
token** back — e.g. via [AWS Amplify Auth](https://docs.amplify.aws/) or
[`amazon-cognito-identity-js`](https://github.com/aws-amplify/amplify-js/tree/main/packages/amazon-cognito-identity-js).
Users sign up (email + password), confirm their email, sign in, and the
library hands back `idToken`. Send that on every API call:

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

Create a test user and get a token via the AWS CLI:

```bash
aws cognito-idp sign-up \
  --client-id "$USER_POOL_CLIENT_ID" \
  --username you@example.com --password 'SomeStr0ngPassw0rd'

aws cognito-idp admin-confirm-sign-up \
  --user-pool-id "$USER_POOL_ID" --username you@example.com

aws cognito-idp initiate-auth \
  --client-id "$USER_POOL_CLIENT_ID" \
  --auth-flow USER_PASSWORD_AUTH \
  --auth-parameters USERNAME=you@example.com,PASSWORD='SomeStr0ngPassw0rd'
# -> copy AuthenticationResult.IdToken from the response
```

Then:

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

curl "$FUNCTION_URL?movement_id=pushup" -H "authorization: Bearer $ID_TOKEN"
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

The Lambda execution role is scoped to exactly two actions
(`dynamodb:PutItem`, `dynamodb:Query`) on the `TrainingLogs` table ARN only —
see the inline `Policies` statement in `template.yaml`.

## Notes / follow-ups for later hardening

- No pagination on `GET` — fine at MVP scale; add `LastEvaluatedKey`
  handling if a movement's log history grows large.
- No sign-up/forgot-password UI is included here — that's on the frontend,
  using Amplify Auth or the Cognito Hosted UI.
