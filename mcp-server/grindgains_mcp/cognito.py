from __future__ import annotations

from dataclasses import dataclass

import httpx

from .errors import CognitoError, LoginError


@dataclass(frozen=True)
class AuthResult:
    id_token: str
    expires_in: int
    refresh_token: str | None = None


def _call(http: httpx.Client, region: str, target: str, payload: dict) -> dict:
    try:
        resp = http.post(
            f"https://cognito-idp.{region}.amazonaws.com/",
            json=payload,
            headers={
                "Content-Type": "application/x-amz-json-1.1",
                "X-Amz-Target": f"AWSCognitoIdentityProviderService.{target}",
            },
        )
    except httpx.HTTPError as err:
        raise CognitoError("NetworkError", f"Could not reach Cognito ({type(err).__name__})") from None
    try:
        data = resp.json()
    except ValueError:
        raise CognitoError("BadResponse", f"Cognito returned an unexpected response (HTTP {resp.status_code})") from None
    if resp.status_code >= 400:
        error_type = str(data.get("__type", "")).split("#")[-1]
        raise CognitoError(error_type, data.get("message") or f"Cognito error (HTTP {resp.status_code})")
    return data


def password_login(http: httpx.Client, region: str, client_id: str, email: str, password: str) -> AuthResult:
    try:
        data = _call(
            http,
            region,
            "InitiateAuth",
            {
                "AuthFlow": "USER_PASSWORD_AUTH",
                "ClientId": client_id,
                "AuthParameters": {"USERNAME": email, "PASSWORD": password},
            },
        )
    except CognitoError as err:
        raise LoginError(f"Login failed: {err}") from None
    if "ChallengeName" in data:
        raise LoginError(
            f"Login needs an extra step ({data['ChallengeName']}). Finish it in the web app, then try again."
        )
    result = data["AuthenticationResult"]
    return AuthResult(
        id_token=result["IdToken"],
        expires_in=int(result["ExpiresIn"]),
        refresh_token=result["RefreshToken"],
    )


def refresh_id_token(http: httpx.Client, region: str, client_id: str, refresh_token: str) -> AuthResult:
    data = _call(
        http,
        region,
        "InitiateAuth",
        {
            "AuthFlow": "REFRESH_TOKEN_AUTH",
            "ClientId": client_id,
            "AuthParameters": {"REFRESH_TOKEN": refresh_token},
        },
    )
    result = data["AuthenticationResult"]
    return AuthResult(id_token=result["IdToken"], expires_in=int(result["ExpiresIn"]))
