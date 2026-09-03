"""
Cognito ID token verification for the Function URL.

There's no API Gateway, so there's no built-in COGNITO_USER_POOLS
authorizer — the Lambda has to verify the JWT itself: fetch the User Pool's
public signing keys (JWKS), check the signature/issuer/audience/expiry, and
pull the caller's stable user id out of the `sub` claim. `sub` (not email)
is what backs the DynamoDB partition key, since it never changes even if the
user later changes their email.
"""

import os

import jwt
from jwt import PyJWKClient

AWS_REGION = os.environ["AWS_REGION"]
USER_POOL_ID = os.environ["USER_POOL_ID"]
CLIENT_ID = os.environ["USER_POOL_CLIENT_ID"]

ISSUER = f"https://cognito-idp.{AWS_REGION}.amazonaws.com/{USER_POOL_ID}"
JWKS_URL = f"{ISSUER}/.well-known/jwks.json"

# Reused across warm invocations; PyJWKClient caches fetched keys internally.
_jwk_client = PyJWKClient(JWKS_URL)


def get_authenticated_user_id(event):
    """Return the caller's Cognito `sub`, or None if unauthenticated/invalid."""
    headers = event.get("headers") or {}
    auth_header = headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[len("Bearer "):]

    try:
        signing_key = _jwk_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=CLIENT_ID,
            issuer=ISSUER,
        )
    except jwt.PyJWTError:
        return None

    # Cognito issues both ID and access tokens; only ID tokens carry `aud`
    # and identity claims, so reject anything else even if signed correctly.
    if claims.get("token_use") != "id":
        return None

    return claims.get("sub")
