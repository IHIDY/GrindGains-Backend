from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from .errors import NotLoggedInError

LOGIN_HINT = (
    "python -m grindgains_mcp.login --api-url <FunctionUrl> --region <region> "
    "--client-id <UserPoolClientId> --email <you@example.com>"
)


@dataclass(frozen=True)
class Credentials:
    api_url: str
    region: str
    client_id: str
    refresh_token: str


def default_credentials_path() -> Path:
    override = os.environ.get("GRINDGAINS_MCP_CREDENTIALS")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "grindgains-mcp" / "credentials.json"


def save(credentials: Credentials, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(asdict(credentials), f)
    os.chmod(path, 0o600)


def load(path: Path) -> Credentials:
    try:
        data = json.loads(path.read_text())
        return Credentials(
            api_url=data["api_url"],
            region=data["region"],
            client_id=data["client_id"],
            refresh_token=data["refresh_token"],
        )
    except (OSError, ValueError, KeyError, TypeError):
        raise NotLoggedInError(f"No saved login found. Run: {LOGIN_HINT}") from None
