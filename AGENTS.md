# GrindGains Backend

Read `_docs/plan.md` first — product/technical spec shared with the frontend repo.
Read `README.md` for the full API contract, deploy steps, and data model — it's the
canonical copy; don't recreate it elsewhere.

Before creating or implementing any issue, read `_docs/process.md` (the issue →
branch → PR → merge → revert workflow) and `_docs/task-template.md` (the issue
format).

Before writing or changing tests, read `_docs/testing-guidelines.md`.

## Commands

- `sam build --use-container` / `sam deploy --guided` — build and deploy (container
  build is required for `PyJWT[crypto]`'s compiled extension)
- `pip install -r requirements-dev.txt` — install test dependencies (once, in a venv; Python 3.10+
  because of the MCP SDK, so the macOS system `python3` 3.9 will not work)
- `python3 -m pytest tests/ mcp-server/tests/` — run tests (backend and MCP server)
- `python3 scripts/create_invite_codes.py --count N --region ca-central-1` — mint
  invite codes

## Rules

- Don't add API Gateway — Lambda Function URLs only, to keep this at $0/month.
- Auth is verified in application code (`src/auth.py`), not via AWS SigV4 — keep it
  that way.
