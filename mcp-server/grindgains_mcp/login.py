from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path
from typing import Callable

import httpx

from . import cognito
from .credentials import Credentials, default_credentials_path, save
from .errors import LoginError


def main(
    argv: list[str] | None = None,
    *,
    http: httpx.Client | None = None,
    read_password: Callable[[str], str] = getpass.getpass,
    path: Path | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m grindgains_mcp.login",
        description="Sign in once and save a refresh token for the GrindGains MCP server.",
    )
    parser.add_argument("--api-url", required=True, help="Lambda Function URL (FunctionUrl stack output)")
    parser.add_argument("--region", required=True, help="AWS region of the Cognito user pool")
    parser.add_argument("--client-id", required=True, help="Cognito app client id (UserPoolClientId stack output)")
    parser.add_argument("--email", required=True)
    args = parser.parse_args(argv)

    password = read_password("Password: ")
    client = http or httpx.Client(timeout=15)
    try:
        result = cognito.password_login(client, args.region, args.client_id, args.email, password)
    except LoginError as err:
        print(str(err), file=sys.stderr)
        return 1

    target = path or default_credentials_path()
    save(Credentials(args.api_url, args.region, args.client_id, result.refresh_token), target)
    print(f"Saved the login to {target} (refresh token only; your password is not stored).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
