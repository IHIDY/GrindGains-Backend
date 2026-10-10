# GrindGains MCP server

A local [MCP](https://modelcontextprotocol.io/) server that lets Claude Desktop read your own GrindGains
training data. It runs on your machine (stdio), calls the same Lambda Function URL as the web app, and
signs in as you. It is **read-only**: there is no tool that can change or delete anything.

It is not part of the Lambda package: `template.yaml` builds only `src/`.

## Tools

| Tool | What it returns |
|---|---|
| `list_movements` | Every movement you have logged, most recently trained first: `movement_id`, `display_name`, `mode` (`isotonic` = sets x reps with a load, `mobeta` = timed isometric hold), `entry_count`, `last_logged_date_local` |
| `get_movement_history(movement_id)` | Every entry for one movement, oldest first: `timestamp` (ISO-8601 with local UTC offset), `date_local`, `weight_lb`, `reps` (isotonic) or `hold_seconds` (mobeta), `sets`, `rpe` (null when not recorded) |

- Dates and times use the `America/Halifax` timezone by default. Set `GRINDGAINS_TZ` to another IANA name
  (for example `America/Vancouver`) to change it. A late-evening workout therefore lands on the day you
  actually trained, not on the next UTC day.
- Weights are pounds, hold times are seconds. The tools return recorded facts only, never advice.
- The API has no count endpoint, so `list_movements` makes one extra request per movement to count entries,
  and neither tool paginates. That is fine at personal scale.

## How authentication works

- You sign in **once** with your email and password. Only a Cognito **refresh token** is saved, together
  with the non-secret connection settings (API URL, region, app client id). The password and the ID token
  are never written to disk.
- The server exchanges the refresh token for a short-lived ID token (1 hour) and sends it as
  `Authorization: Bearer ...`, exactly like the web app. If the API answers 401 it refreshes once and retries.
- The refresh token is stored at `~/.config/grindgains-mcp/credentials.json` (file mode 600, directory
  mode 700), outside any repository. Set `GRINDGAINS_MCP_CREDENTIALS` to use another path.
- The refresh token lasts about 30 days (the Cognito default; this project does not set a custom value),
  after which the tools tell you to run the login command again.
- Treat the credentials file like a password: anyone who can read it can read your training data until it
  expires.

## Setup

Requires **Python 3.10 or newer** (the macOS system `python3` 3.9 is too old).

```bash
cd mcp-server
python3.13 -m venv .venv        # or any Python >= 3.10
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

## Try it with MCP Inspector

```bash
npx @modelcontextprotocol/inspector \
  /ABSOLUTE/PATH/TO/GrindGains-Backend/mcp-server/.venv/bin/python \
  /ABSOLUTE/PATH/TO/GrindGains-Backend/mcp-server/run_server.py
```

In the Inspector, list the tools and call `list_movements`; you should see your real data.

## Add it to Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (or Claude Desktop → Settings →
Developer → Edit Config) and add the server. **Use absolute paths**: Claude Desktop starts servers with an
undefined working directory, and `~` is not expanded.

```json
{
  "mcpServers": {
    "grindgains": {
      "command": "/ABSOLUTE/PATH/TO/GrindGains-Backend/mcp-server/.venv/bin/python",
      "args": ["/ABSOLUTE/PATH/TO/GrindGains-Backend/mcp-server/run_server.py"]
    }
  }
}
```

Quit Claude Desktop completely and reopen it, then ask for example "What did I train last week?".

## Security notes

- Everything a tool returns becomes part of your conversation with Claude, so only connect it on an
  account where you are comfortable sharing your training log.
- The tools are annotated read-only, but annotations are only hints to the client; the real guarantee is
  that the server contains no write code.
- Nothing secret is stored in this repository. If you ever commit a file by mistake, treat the refresh token
  as leaked and sign in again after it expires or is revoked.
- The server writes logs to stderr only, because stdout carries the MCP protocol.

## Tests

From the repository root, with the test dependencies installed (`pip install -r requirements-dev.txt`):

```bash
python3 -m pytest tests/ mcp-server/tests/
```

The tests use a fake HTTP transport and a fake API, so they need no network, AWS credentials or real
account; three of them start the real server as a subprocess and talk to it over stdio.
