from __future__ import annotations

import time
from typing import Callable

import httpx

from . import cognito
from .credentials import LOGIN_HINT, Credentials
from .errors import ApiError, CognitoError, ReLoginRequiredError

# Refresh a little before the ID token really expires so a request never races the expiry.
REFRESH_MARGIN_SECONDS = 60


class GrindGainsClient:
    def __init__(
        self,
        credentials: Credentials,
        http: httpx.Client | None = None,
        clock: Callable[[], float] = time.time,
    ):
        self._credentials = credentials
        self._http = http or httpx.Client(timeout=15)
        self._clock = clock
        self._id_token: str | None = None
        self._expires_at = 0.0

    def list_movements(self) -> list[dict]:
        return self._get_list(None)

    def get_movement_history(self, movement_id: str) -> list[dict]:
        return self._get_list({"movement_id": movement_id})

    def _get_list(self, params: dict | None) -> list[dict]:
        data = self._get(params)
        if not isinstance(data, list):
            raise ApiError("The API returned an unexpected response shape")
        return data

    def _get(self, params: dict | None):
        resp = None
        for attempt in (0, 1):
            token = self._token(force_refresh=attempt == 1)
            try:
                resp = self._http.get(
                    self._credentials.api_url.rstrip("/") + "/",
                    params=params,
                    headers={"Authorization": f"Bearer {token}"},
                )
            except httpx.HTTPError as err:
                raise ApiError(f"Could not reach the GrindGains API ({type(err).__name__})") from None
            if resp.status_code != 401:
                break

        if resp.status_code == 401:
            raise ApiError(f"The API rejected the saved login even after refreshing. Run: {LOGIN_HINT}")
        if resp.status_code >= 400:
            raise ApiError(f"The API returned an error (HTTP {resp.status_code}): {self._error_message(resp)}")
        try:
            return resp.json()
        except ValueError:
            raise ApiError("The API returned a response that is not JSON") from None

    @staticmethod
    def _error_message(resp: httpx.Response) -> str:
        try:
            message = resp.json().get("error")
        except (ValueError, AttributeError):
            message = None
        return message if isinstance(message, str) else "no details"

    def _token(self, force_refresh: bool = False) -> str:
        if not force_refresh and self._id_token and self._clock() < self._expires_at - REFRESH_MARGIN_SECONDS:
            return self._id_token
        try:
            result = cognito.refresh_id_token(
                self._http,
                self._credentials.region,
                self._credentials.client_id,
                self._credentials.refresh_token,
            )
        except CognitoError as err:
            if err.error_type == "NotAuthorizedException":
                raise ReLoginRequiredError(
                    f"The saved login expired or was revoked. Run: {LOGIN_HINT}"
                ) from None
            raise ApiError(f"Could not refresh the login: {err}") from None
        self._id_token = result.id_token
        self._expires_at = self._clock() + result.expires_in
        return self._id_token
