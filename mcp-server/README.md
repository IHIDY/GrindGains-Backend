# GrindGains MCP server

A local [MCP](https://modelcontextprotocol.io/) server that lets Claude Desktop read your own GrindGains
training data. It runs on your machine (stdio) and calls the same Lambda Function URL as the web app,
signed in as you.

This directory currently contains the **login command and the authenticated API client**. The MCP tools
and the server entry point come in the next step (GrindGains-Backend#14).

It is not part of the Lambda package: `template.yaml` builds only `src/`.

## How authentication works

- You sign in **once** with your email and password. Only a Cognito **refresh token** is saved, together
  with the non-secret connection settings (API URL, region, app client id). The password and the ID token
  are never written to disk.
- The client exchanges the refresh token for a short-lived ID token (1 hour) and sends it as
  `Authorization: Bearer ...`, exactly like the web app. If the API answers 401 it refreshes once and retries.
- The refresh token is stored at `~/.config/grindgains-mcp/credentials.json` (file mode 600, directory
  mode 700), outside any repository. Set `GRINDGAINS_MCP_CREDENTIALS` to use another path.
- The refresh token expires after the Cognito default of about 30 days (this project does not set a
  custom value), after which the client tells you to run the login command again.
- Treat the credentials file like a password: anyone who can read it can read your training data until you
  sign out of that session or it expires.

## Setup

Requires Python 3.10 or newer (the macOS system `python3` is too old; use a newer one).

```bash
cd mcp-server
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Sign in once, using the values from the backend stack outputs (`FunctionUrl`, region, `UserPoolClientId`):

```bash
.venv/bin/python -m grindgains_mcp.login \
  --api-url https://<your-function-url> \
  --region <aws-region> \
  --client-id <UserPoolClientId> \
  --email <you@example.com>
```

You are asked for the password without it being echoed.

## Tests

From the repository root, with the test dependencies installed (`pip install -r requirements-dev.txt`):

```bash
python3 -m pytest tests/ mcp-server/tests/
```

The tests use a fake HTTP transport, so they need no network, AWS credentials or real account.
