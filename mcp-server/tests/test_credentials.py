from pathlib import Path

import pytest

from grindgains_mcp.credentials import Credentials, default_credentials_path, load, save
from grindgains_mcp.errors import NotLoggedInError

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_default_path_is_under_the_home_directory_and_outside_the_repo(monkeypatch):
    monkeypatch.delenv("GRINDGAINS_MCP_CREDENTIALS", raising=False)

    path = default_credentials_path()

    assert Path.home() in path.parents
    assert REPO_ROOT not in path.parents


def test_save_then_load_round_trips(tmp_path):
    path = tmp_path / "cfg" / "credentials.json"
    creds = Credentials("https://api.example.test", "ca-central-1", "client", "refresh")

    save(creds, path)

    assert load(path) == creds


def test_load_without_a_saved_login_says_how_to_log_in(tmp_path):
    with pytest.raises(NotLoggedInError, match="grindgains_mcp.login"):
        load(tmp_path / "missing.json")


def test_load_rejects_a_corrupted_file(tmp_path):
    path = tmp_path / "credentials.json"
    path.write_text("{not json")

    with pytest.raises(NotLoggedInError):
        load(path)
