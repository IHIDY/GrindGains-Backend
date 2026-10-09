# Testing guidelines

Read this before writing or changing tests, in either repo. It describes what the
tests already do; follow the existing patterns instead of inventing new ones. For the
process rules (criterion -> test, same PR, no merge while red) see `_docs/process.md`.

## General rules

- Every acceptance criterion in an issue is proven by a test, or by explicit manual
  steps when it cannot be automated. The PR lists the criterion, the test, the command
  and its result.
- Write tests in the same PR as the code. Fixing a bug starts with a test that fails
  for the bug.
- Test behaviour, not implementation: assert on responses, return values and what was
  sent, not on private details.
- Cover the awkward cases, not only the happy path: missing fields, out-of-range
  values, empty input, legacy data without a newer field.
- After writing tests, break the code on purpose once and confirm they fail, then
  restore it (done for the frontend tests in GrindGains-Frontend PR #9).
- A test must not need the network, AWS credentials, or a deployed backend.

## Backend (pytest) — `tests/test_app.py`

- Setup: `pip install -r requirements-dev.txt`, run `python3 -m pytest tests/`. CI runs
  the same on Python 3.11.
- Importing `app` must not touch AWS: the module is imported inside
  `with mock.patch("boto3.resource")`, and the `TABLE_NAME`, `AWS_REGION`,
  `USER_POOL_ID`, `USER_POOL_CLIENT_ID` environment variables are set first with
  `os.environ.setdefault`.
- DynamoDB is replaced by the `fake_table` fixture, which patches `app._table` with a
  `MagicMock`. Assert on `fake_table.put_item.call_args` and set
  `fake_table.query.return_value` for reads.
- Call the handlers directly (`app._handle_post`, `app._handle_put`,
  `app._handle_get`) with a small event dict and a user id, via the `_post` / `_put`
  helpers.
- Build request bodies from the shared `VALID_BODY` and override one field
  (`{**VALID_BODY, "rpe": 8}`) so each test shows only what it changes.
- Use `pytest.mark.parametrize` for a list of bad values and
  `pytest.raises(ValueError, match="field")` for validation errors.
- Keep a test for legacy items missing newer fields
  (`test_get_handles_legacy_item_without_rpe`).

## Frontend (Vitest) — `src/**/*.test.ts`

- Setup: Node 22, `npm ci`, then `npm test` (runs once and exits). Test files sit next
  to the code they cover (`src/lib/format.test.ts`, `src/api/client.test.ts`).
- Stub `fetch` with `vi.stubGlobal("fetch", fetchMock)` in `beforeEach` and restore
  it with `vi.unstubAllGlobals()` in `afterEach`; build responses with a small
  `jsonResponse` helper.
- `src/api/client.ts` reads `VITE_API_BASE_URL` when it is imported, so call
  `vi.stubEnv(...)` first and load the module with `await import("./client")`.
- Assert on what was sent (URL, method, headers, parsed JSON body) and on the
  normalized result, and test error responses (JSON error body and non-JSON body).
- Avoid assertions that depend on locale or timezone (for example `formatShortDate`);
  test the pure helpers instead.

## Not covered yet

- Integration tests (real DynamoDB behaviour, frontend against backend). Conventions
  will be added when the first ones exist.
- Backend: `src/auth.py` (JWT verification), `src/invite_trigger.py` (invite code and
  username transaction), and `lambda_handler` routing with its 401 and 500 responses
  have no tests.
- Frontend: no tests for hooks, auth, pages or components.
