# GrindGains — Product & Technical Spec

> Written 2026-09-17 by reading the existing Backend/Frontend code (this was a
> half-built MVP already, not a from-scratch spec) — see `GrindGains-Frontend/_docs/plan.md`
> for the pointer from that repo. Treat this as the shared source of truth for both
> repos; update it (not just the code) when a decision here turns out to be wrong.

## 1. Product vision

A personal training log for one or a small invite-only group of lifters. Users log
individual movements (exercises) either as **sets × reps with load** (isotonic) or as
**timed holds with optional added weight** (mobeta / isometric), and see history +
trend charts per movement. No coach/trainee relationship, no social feed, no programmed
routines — it's a diary, not a program.

## 2. Users

- Invite-only signup: every account needs a valid, single-use invite code
  (`src/invite_trigger.py`).
- Each user only ever sees their own data (`PK = USER#<cognito sub>`); there is no
  sharing, no coach view, no admin UI beyond the `create_invite_codes.py` script.
- Optional unique display username (3-20 chars, `[a-zA-Z0-9_]`), enforced backend-side
  and validated frontend-side on the signup form.

## 3. Core concepts

- **Movement** = one exercise (e.g. `pushup`, `plank`). Identified by `movement_id`
  (slugified from a free-text name client-side: lowercase, spaces → `_`).
- A movement has exactly one **mode** for its lifetime in the UI: `isotonic` or
  `mobeta`. The backend doesn't enforce this — it's the frontend inferring mode from
  the most recent logged entry (`useMovement` in `api/hooks.ts`); a brand-new,
  never-logged movement takes its mode from the `?mode=` query param chosen on
  creation. See §7 open question.
- **Entry** (a "set" or a "hold") belongs to one movement and carries:
  `mode, weight, reps_or_time, sets, rpe?, timestamp`. `timestamp` is server-assigned
  and doubles as the entry's identity for edits.
- There is **no "Workout" as a session/grouping concept** on the backend — "workout" in
  the UI is just the per-movement view. Multiple entries can share a calendar day; the
  detail charts group by day (`groupByDay` in `lib/format.ts`) so a multi-set session
  shows as one point.

## 4. Feature scope (what's actually built)

### Auth
- Sign up (username + email + password + invite code) → Cognito email verification
  code → confirm → auto-login.
- Log in / log out. Session persisted via Cognito's refresh token; ID token
  transparently refreshed (1 hour expiry).
- Route guard (`RequireAuth`) protects `/workouts*` on the frontend.

### Workout list (`/workouts`)
- Lists every movement the user has ever logged (backend's "no `movement_id`" GET
  mode), one card per movement showing mode, last-logged date, entry count.
- "New Workout" inline form: free-text movement name + mode picker → routes to
  `/workouts/:id/log?mode=...` for the first entry.

### Movement detail (`/workouts/:id`)
- Isotonic view: training log table (editable, see below) + two line charts (volume =
  Σ weight×reps×sets per day; average weight per day).
- Mobeta view: same page-split pattern as isotonic (`WorkoutDetailMobeta.tsx`) — not
  yet reviewed in the same detail as the isotonic view, see §7.
- "Log Set" / "Log a Hold" button → `/workouts/:id/log`.

### New entry (`/workouts/:id/log`)
- Isotonic: one or more set rows (reps, weight, optional RPE 1-10), submitted as
  separate `POST`s (one per row/set logged individually — not batched under one `sets`
  count).
- Mobeta: a hold timer (start/stop → seconds) + optional added weight, single `POST`
  per hold.

### Editing a logged entry
- Inline edit in `TrainingLogTable` (reps/weight/RPE) → `PUT` full-replace, keyed by
  `movement_id` + `timestamp`. Fully wired end to end (frontend UI → hook → client →
  backend `PUT` handler).

## 5. Data model (DynamoDB single-table, `TrainingLogs`)

| Item type | PK | SK | Notable attrs |
|---|---|---|---|
| Training log entry | `USER#<sub>` | `MOVEMENT#<id>#LOG#<iso-timestamp>` | `mode, weight, reps_or_time, sets, rpe?` |
| Invite code | `INVITECODE#<code>` | `STATUS` | consumed atomically on signup |
| Claimed username | `USERNAME#<lowercased>` | — | claimed atomically alongside invite-code check (`TransactWriteItems`) |

## 6. API contract (Lambda Function URL, no API Gateway)

Full request/response shapes, error table, and deploy/auth details are documented in
this repo's `README.md` — that stays the single canonical copy (the frontend used to
carry a duplicate that drifted out of date; it was deleted, see §8). Summary:

All requests need `Authorization: Bearer <Cognito ID token>` → `401` if missing/invalid.

| Method | Purpose | Key/body |
|---|---|---|
| `POST` | Create one entry | `movement_id, mode, weight, reps_or_time, sets?, rpe?` → `201` + created entry |
| `PUT` | Full-replace an existing entry | same body + `timestamp` (identifies the entry) → `200` + updated entry, `404` if no match |
| `GET ?movement_id=X` | History for one movement, oldest-first | → array of entries |
| `GET` (no param) | One entry per movement (latest) — powers the list page | → array of entries |

## 7. Open questions / follow-ups

- **Mode enforcement**: nothing stops two entries for the same `movement_id` from
  having different `mode` values (e.g. a client bug, or the same movement logged with
  different modes from two devices). Decide whether the backend should enforce
  "one mode per movement_id" or whether "last write wins" is fine at this scale.
- **Mobeta detail page**: `WorkoutDetailMobeta.tsx` hasn't been reviewed against this
  spec as closely as the isotonic page — confirm it matches (charts, editing) before
  treating this doc as ground truth for it specifically.
- Carried over from `README.md`'s "Notes / follow-ups for later hardening": no rate
  limiting, no pagination on either `GET` mode, no password-reset UI, no
  routine/session grouping, no sharing/coach/admin UI, no built-in audio/video
  recording. None of these are MVP requirements — call them out explicitly if that
  changes.

## 8. Resolved drift (2026-09-17)

When this spec was first drafted, two things had drifted between the repos and were
fixed as part of writing it down:

1. `GrindGains-Frontend`'s `api/client.ts`/`hooks.ts` carried comments claiming `PUT`
   and `rpe` were "not yet supported by the backend." False — both were already
   implemented and wired end-to-end in the UI. Comments corrected.
2. `GrindGains-Frontend/README backend.md` was a stale, out-of-date mirror of this
   repo's `README.md` (missing `PUT`, `rpe`, username uniqueness). Deleted; this repo's
   `README.md` is the single source of truth for the API going forward.
