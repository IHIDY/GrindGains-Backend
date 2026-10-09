# Process

How we go from a feature discussion to a merged, revertible change. Applies to both
this repo and `GrindGains-Frontend` (not duplicated there — see that repo's
`_docs/process.md` for the pointer, same reasoning as `plan.md`).

## Issues

- One issue = one independently-implementable, independently-verifiable unit of work
  — small enough for one session. If a discussion turns out to be bigger than that,
  split it into multiple issues rather than writing one large one.
- Every issue follows the four-section template in `_docs/task-template.md` (Goal /
  Acceptance Criteria / Out of Scope / Constraints).
- A feature that touches both repos gets one issue per repo, each linking to the
  other in its description.

## Branches

- One branch per issue: `issue-<number>-<short-slug>`.
- Never commit directly to `main`.
- Commits reference the issue (`Refs #N`), kept small and single-purpose.

## Pull requests

- One PR per issue. Body includes `Closes #N` and checks off each acceptance
  criterion from the issue.
- Before merging, re-read the issue and `_docs/plan.md` — confirm the diff still
  matches the acceptance criteria, not just that it "looks reasonable."
- Merge with squash, so `main` gets exactly one commit per issue.
- Delete the branch after merge.

## Acceptance criteria and tests

- Every acceptance criterion must be provable by a test. The issue names the test
  that will prove it (see `_docs/task-template.md`).
- The tests are written in the same PR as the code, not afterwards.
- The PR body lists each criterion with the test that proves it, plus the test
  command and its result (for example "`npm test`: 19 passed").
- Do not merge while the test suite fails.
- If a criterion cannot reasonably be automated (visual layout, documentation), the
  issue must give explicit manual steps for it, and the PR records that they were
  followed. Treat this as the exception, not the default.
- Current limit: the frontend deploy workflow does not run tests yet. Until it does,
  run the suite locally and paste the result into the PR; CI will not catch a
  failure for you.

## Reverting

- To undo a shipped feature: `git revert <its squash commit on main>` — safe because
  each issue is exactly one commit on `main`.
- To abandon in-flight work: close the PR and delete the branch without merging; the
  issue stays open for later.

## Before implementing anything

- Read the issue in full, plus `_docs/plan.md`, before writing code — every time,
  even mid-session — to catch drift between what was discussed and what's about to
  be built.
