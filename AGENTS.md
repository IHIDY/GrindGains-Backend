# GrindGains Backend

Read `_docs/plan.md` first — product/technical spec shared with the frontend repo.
Read `README.md` for the full API contract, deploy steps, and data model — it's the
canonical copy; don't recreate it elsewhere.

## Commands

- `sam build --use-container` / `sam deploy --guided` — build and deploy (container
  build is required for `PyJWT[crypto]`'s compiled extension)
- `python3 -m pytest tests/` — run tests
- `python3 scripts/create_invite_codes.py --count N --region ca-central-1` — mint
  invite codes

## Rules

- Don't add API Gateway — Lambda Function URLs only, to keep this at $0/month.
- Auth is verified in application code (`src/auth.py`), not via AWS SigV4 — keep it
  that way.
