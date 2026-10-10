import json
import stat

import httpx

from conftest import API_URL, CLIENT_ID, REGION, cognito_error, cognito_ok, make_http
from grindgains_mcp.login import main

ARGS = ["--api-url", API_URL, "--region", REGION, "--client-id", CLIENT_ID, "--email", "me@example.test"]
PASSWORD = "correct horse battery staple"


def run_login(handler, path):
    return main(ARGS, http=make_http(handler), read_password=lambda _prompt: PASSWORD, path=path)


def test_login_saves_only_the_refresh_token_and_connection_settings(tmp_path):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["target"] = request.headers["x-amz-target"]
        seen["body"] = json.loads(request.content)
        return cognito_ok(id_token="the-id-token", refresh_token="the-refresh-token")

    path = tmp_path / "grindgains-mcp" / "credentials.json"

    assert run_login(handler, path) == 0

    assert seen["url"] == f"https://cognito-idp.{REGION}.amazonaws.com/"
    assert seen["target"].endswith(".InitiateAuth")
    assert seen["body"]["AuthFlow"] == "USER_PASSWORD_AUTH"
    assert seen["body"]["ClientId"] == CLIENT_ID

    text = path.read_text()
    assert json.loads(text) == {
        "api_url": API_URL,
        "region": REGION,
        "client_id": CLIENT_ID,
        "refresh_token": "the-refresh-token",
    }
    assert PASSWORD not in text
    assert "the-id-token" not in text


def test_login_file_is_private(tmp_path):
    path = tmp_path / "grindgains-mcp" / "credentials.json"

    run_login(lambda request: cognito_ok(refresh_token="r"), path)

    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_failed_login_prints_the_reason_and_writes_no_file(tmp_path, capsys):
    path = tmp_path / "grindgains-mcp" / "credentials.json"

    code = run_login(lambda request: cognito_error("NotAuthorizedException", "Incorrect username or password."), path)

    assert code == 1
    assert "Incorrect username or password." in capsys.readouterr().err
    assert not path.exists()


def test_login_challenge_writes_no_file(tmp_path, capsys):
    path = tmp_path / "grindgains-mcp" / "credentials.json"

    def handler(request):
        return httpx.Response(200, json={"ChallengeName": "NEW_PASSWORD_REQUIRED", "Session": "s"})

    code = run_login(handler, path)

    assert code == 1
    assert "NEW_PASSWORD_REQUIRED" in capsys.readouterr().err
    assert not path.exists()
