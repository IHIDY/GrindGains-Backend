import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from conftest import REFRESH_TOKEN, Clock, cognito_error, cognito_ok, make_http
from grindgains_mcp.api import GrindGainsClient
from grindgains_mcp.errors import ApiError, ReLoginRequiredError

ENTRY = {
    "movement_id": "pushup",
    "timestamp": "2026-09-07T18:41:00.067781Z",
    "mode": "isotonic",
    "weight": 0,
    "reps_or_time": 20,
    "sets": 3,
    "rpe": 8,
}


class FakeBackend:
    """Routes requests to a fake Cognito or a fake API and records them."""

    def __init__(self, api_responses, cognito_responses=None):
        self.api_responses = list(api_responses)
        self.cognito_responses = list(cognito_responses or [cognito_ok("id-1")])
        self.cognito_calls = []
        self.api_calls = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.host.startswith("cognito-idp"):
            self.cognito_calls.append(json.loads(request.content))
            return self.cognito_responses.pop(0) if len(self.cognito_responses) > 1 else self.cognito_responses[0]
        self.api_calls.append(request)
        response = self.api_responses.pop(0) if len(self.api_responses) > 1 else self.api_responses[0]
        if isinstance(response, Exception):
            raise response
        return response


def make_client(credentials, backend, clock=None):
    return GrindGainsClient(credentials, http=make_http(backend), clock=clock or Clock())


def test_exchanges_the_refresh_token_and_sends_the_id_token_as_bearer(credentials):
    backend = FakeBackend([httpx.Response(200, json=[ENTRY])])

    make_client(credentials, backend).list_movements()

    assert backend.cognito_calls == [
        {
            "AuthFlow": "REFRESH_TOKEN_AUTH",
            "ClientId": credentials.client_id,
            "AuthParameters": {"REFRESH_TOKEN": REFRESH_TOKEN},
        }
    ]
    assert backend.api_calls[0].headers["authorization"] == "Bearer id-1"


def test_reuses_the_cached_id_token_until_shortly_before_it_expires(credentials):
    clock = Clock(1000.0)
    backend = FakeBackend(
        [httpx.Response(200, json=[])],
        [cognito_ok("id-1", expires_in=3600), cognito_ok("id-2", expires_in=3600)],
    )
    client = make_client(credentials, backend, clock)

    client.list_movements()
    clock.now += 3000  # still inside the token's lifetime
    client.list_movements()
    assert len(backend.cognito_calls) == 1

    clock.now += 600  # now within the 60s safety margin of expiry
    client.list_movements()
    assert len(backend.cognito_calls) == 2
    assert backend.api_calls[-1].headers["authorization"] == "Bearer id-2"


def test_a_401_triggers_one_refresh_and_a_retry(credentials):
    backend = FakeBackend(
        [httpx.Response(401, json={"error": "Unauthorized"}), httpx.Response(200, json=[ENTRY])],
        [cognito_ok("id-1"), cognito_ok("id-2")],
    )

    result = make_client(credentials, backend).list_movements()

    assert result == [ENTRY]
    assert [c.headers["authorization"] for c in backend.api_calls] == ["Bearer id-1", "Bearer id-2"]


def test_a_second_401_raises_a_clear_error(credentials):
    backend = FakeBackend(
        [httpx.Response(401, json={"error": "Unauthorized"})],
        [cognito_ok("id-1"), cognito_ok("id-2")],
    )

    with pytest.raises(ApiError, match="grindgains_mcp.login"):
        make_client(credentials, backend).list_movements()

    assert len(backend.api_calls) == 2


def test_an_expired_refresh_token_tells_the_user_to_log_in_again(credentials):
    backend = FakeBackend(
        [httpx.Response(200, json=[])],
        [cognito_error("NotAuthorizedException", "Refresh Token has expired")],
    )

    with pytest.raises(ReLoginRequiredError, match="grindgains_mcp.login"):
        make_client(credentials, backend).list_movements()

    assert backend.api_calls == []


def test_fetches_every_movement(credentials):
    backend = FakeBackend([httpx.Response(200, json=[ENTRY])])

    result = make_client(credentials, backend).list_movements()

    assert result == [ENTRY]
    request = backend.api_calls[0]
    assert request.method == "GET"
    assert urlparse(str(request.url)).query == ""


def test_fetches_one_movements_history_with_the_id_encoded(credentials):
    backend = FakeBackend([httpx.Response(200, json=[ENTRY])])

    result = make_client(credentials, backend).get_movement_history("bench press")

    assert result == [ENTRY]
    query = parse_qs(urlparse(str(backend.api_calls[0].url)).query)
    assert query == {"movement_id": ["bench press"]}
    assert "bench%20press" in str(backend.api_calls[0].url) or "bench+press" in str(backend.api_calls[0].url)


@pytest.mark.parametrize(
    "response",
    [
        httpx.ConnectError("boom"),
        httpx.Response(500, json={"error": "Internal error"}),
        httpx.Response(200, content=b"<html>not json</html>"),
        httpx.Response(200, json={"not": "a list"}),
    ],
)
def test_failures_become_a_clear_error_without_leaking_tokens(credentials, response):
    backend = FakeBackend([response])

    with pytest.raises(ApiError) as excinfo:
        make_client(credentials, backend).list_movements()

    message = str(excinfo.value)
    assert message
    assert "id-1" not in message
    assert REFRESH_TOKEN not in message


def test_a_server_error_message_includes_the_status(credentials):
    backend = FakeBackend([httpx.Response(500, json={"error": "Internal error"})])

    with pytest.raises(ApiError, match="500.*Internal error"):
        make_client(credentials, backend).list_movements()
