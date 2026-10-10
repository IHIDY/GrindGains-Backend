import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from grindgains_mcp.credentials import Credentials  # noqa: E402

REGION = "ca-central-1"
CLIENT_ID = "test-client-id"
API_URL = "https://api.example.test"
REFRESH_TOKEN = "refresh-token-secret"


@pytest.fixture
def credentials():
    return Credentials(api_url=API_URL, region=REGION, client_id=CLIENT_ID, refresh_token=REFRESH_TOKEN)


def cognito_ok(id_token="id-1", expires_in=3600, refresh_token=None):
    result = {"IdToken": id_token, "ExpiresIn": expires_in, "TokenType": "Bearer"}
    if refresh_token:
        result["RefreshToken"] = refresh_token
    return httpx.Response(200, json={"AuthenticationResult": result})


def cognito_error(error_type, message, status=400):
    return httpx.Response(
        status,
        json={"__type": error_type, "message": message},
        headers={"x-amzn-errortype": error_type},
    )


def make_http(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now
