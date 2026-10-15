# Authentication and sign-up

How sign-in works, how invite codes and usernames are enforced, and how a client talks to the API.

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

# pick a password for the test user that meets the pool's password policy
export TEST_PASSWORD='<your-test-password>'

aws cognito-idp sign-up \
  --client-id "$USER_POOL_CLIENT_ID" \
  --username you@example.com --password "$TEST_PASSWORD" \
  --client-metadata invite_code="$INVITE_CODE"

aws cognito-idp admin-confirm-sign-up \
  --user-pool-id "$USER_POOL_ID" --username you@example.com

aws cognito-idp initiate-auth \
  --client-id "$USER_POOL_CLIENT_ID" \
  --auth-flow USER_PASSWORD_AUTH \
  --auth-parameters USERNAME=you@example.com,PASSWORD="$TEST_PASSWORD"
# -> copy AuthenticationResult.IdToken from the response
```

Then (see the [API reference](api.md) for the full request/response shapes):

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
