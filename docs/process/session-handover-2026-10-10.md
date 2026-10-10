# Session handover - 2026-10-10 ~04:45 IST (read first in the next session)

Previous: `session-handover-2026-10-09.md`. Plan: `docs/process/master-plan-2026-10-07.md` Stage 4a. Open owner items:
`docs/process/owner-questions-2026-10-10.md`.

## 0. This PC is the Windows VPS (new since 2026-10-09)
- Checkout `C:\Abhay\Ventures\OptionsForOptions2` on the Windows VPS (103.118.16.189, 2 vCPU, 6 GB). Its PostgreSQL 16
  holds `ofo_test` AND serves **IPODhan production and staging** (connections from the Hostinger host). No SSH tunnel:
  the DB is local at 127.0.0.1:5432. `GLOBAL.env` is `C:\Abhay\GLOBAL.env` (db_run.py finds it).
- **Owner decision 2026-10-09: light local, heavy in CI.** Targeted test files only; the full app suite, Playwright,
  the frontend build and any scale test run in CI's own PostgreSQL. Every brief - reviewers and verifiers too - carries
  a DB load cap (probes < 30 s, no benchmarks here).
- Project `.env` was rebuilt here (owner OK): `ofo_app` password reset (old PC's .env no longer reaches the DB),
  fresh `BROKER_TOKEN_KEY` / `KITE_TOKEN_CACHE_KEY`, `KITE_EXPECTED_USER_ID=DA1707` (from GLOBAL.md; unconfirmed).
- `.git/info/exclude` ignores `.claude/worktrees/` (builder agents create spare worktrees there).
- Repo is **public** (ADR-070); `main` requires up-to-date `lint-and-test` + `coverage`, admins included.
- `ofo_test` is at revision `0009_minute_history`.

## 1. Merged this session (main at 8b46b35 + this check-in)
- #168, #169, #173, #175, #177 docs/tooling batches: ADR-070; findings (lax jsonpath, absolute paths, CI mirror
  subset, loss-region from breakevens, guard-as-forbidden-list, targeted tests miss dependents); portable helpers;
  `atool.py` = every ci.yml lint step + repo-wide guard tests (`--no-tests` skips only the full suite; `--show <tool>`).
- #134 **W-061 Save Draft** done: positive plpgsql validators in the guard triggers (independent review after two red
  rounds), filled-map round trip; verifier PASS REQ-038 AC-5.
- #176 **#163** done: Kite login refusals redirect to `/broker/refused?code=<closed code>`, page fetches the catalogue
  message from `GET /api/broker/refusals/{code}`, every refusal logged by code.
- #178 **W-067** done: one-minute history in PostgreSQL (`0009_minute_history`), non-blocking writer queue, set-based
  finalize per ADR-067 (earliest 16:00 IST; full day 1,603 instruments = 46.8 s in CI); verifier PASS REQ-051 AC-3/4/5.

## 2. PARKED / BLOCKED
- **W-066** (#151 outcome text from the catalogue) PARKED as **#172** after the owner's final round: a bounded loss
  split by one zero point crashes. The #151 goal itself is met on `build/W-066-on-main` (draft PR #170); ADR-071 (owner:
  "before charges and taxes") and ADR-072 (loss regions from the payoff) are on that branch. Resume per #172 "What is
  left". Worktree `C:\Abhay\Ventures\OptionsForOptions2-W-066` kept (TTL: until resumed; owner question 4).
- **W-065** live push: built on `build/W-065-live-push` (no PR), worktree `...-W-065` kept. Needs the owner's Kite login
  after 09:15 IST (owner question 1) for the in-process proof `docs/research/kite-proof-2026-10-07/w065_live_push_proof.py`
  run from the W-065 worktree. Its websocket route registers only after W-066 (no W-024 exemption - orchestrator
  decision 2026-10-09). Merge main into it first (main moved a lot).

## 3. NEXT (in order)
1. W-065 live proof with the owner's login (market hours), then its phase 2 (frontend composable + Playwright replay).
2. Resume W-066 (#172), then register W-065's route.
3. Leg picker + Save Draft button - after the owner answers which requirement the picker delivers (owner question 2).
4. Deferred fixes: #179 (wall-clock in tests_app), #174, #171 (needs a decision row), #167, #148, #155, #156.
5. #154: the BEHIND-refusal proof is still unobserved (no PR has been merely behind main since protection was set).

## 4. Owner items
`docs/process/owner-questions-2026-10-10.md`: Kite login; leg-picker requirement; ~85 templates to read (16 merged
with W-061, 69 + ADR-071/072 changes on the W-066 branch); W-066 resume timing.

## 5. Traps learned (all in `knowledge/findings/`)
- Read the decision text before writing a rule into a brief; `check_brief` only checks QUOTED text (W-067 r2 brief
  contradicted ADR-067 - `brief-rule-from-memory`, 12th occurrence).
- A guard is an allow-list (`guard-as-forbidden-list`, builder-brief quality bar).
- Targeted runs: grep tests/ and tests_app/ for every changed route/code/message (`targeted-tests-miss-dependent-files`).
- tests/ never imports ofo_app (guarded by `tests/test_no_app_imports.py`); tests_required files must exist
  (guarded by `tests/test_tests_required_exist.py`; kit issue Startup-Factory#94).
- The kit guard blocks shell text naming `spec`, `views`, `tools/`, `.claude`, `.github` - even inside a commit message,
  a heredoc body or an echo label; write bodies with the Write tool and pass file paths.
- `gh pr edit` can fail on a GraphQL "Projects (classic)" error without changing anything: use
  `gh api -X PATCH repos/<repo>/pulls/<n> -F body=@file` and read the body back.
- A closed issue must leave `docs/process/coverage-stages.yaml` in the next PR; a new open issue needs a row before any
  other PR's coverage check passes.
