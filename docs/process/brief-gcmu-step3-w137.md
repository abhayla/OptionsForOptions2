# Brief: GC-MU step 3 - W-137 / REQ-113 finish: feed restart core re-proven, #520 MINORs fixed, the liveprices role named

Core: the market-data process holds the Kite price socket; restarting the API process does not reconnect it, and fresh frames reach the restarted API (W-137 core).
Proof: step 1 of this brief - `tests_app/test_feed_restart_core.py` re-run on the head of build/gcmu-feed, green, before any change.
Budget: 45 min wall-clock, 60 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Class: feed-process lifecycle states that tests model differently from production - before: 3 known (ended status with the real store, store read failure masking the expiry check, isolation test on session files not a database); after: each pinned by a test that uses the production shape.
Round: 1/2
Findings checked: F-58, F-59 (spec/findings.md); knowledge/findings grep for feed_main, session expiry, ended
Spec quote: REQ-113 "The live price feed and the broker order-update feed run in their own process, so an API deploy never cuts users' feeds"
Threat model: in scope - a session past its expiry shown as stopped instead of ended to a later reader; an unreadable store at expiry time leaving the Kite socket open; isolation proven only on files; out of scope - the two-user browser test (needs a multi-user API, ADR-060; stays deferred), order-update feed (AC-4 deferred).
Sensibull: n/a - server process, no screen.
Reference: none - searched price feed process, websocket restart (server only, no screen)
Copy from: none new - W-137 already copied/adapted its rows in chunk 1; this brief changes only feed_main.py lifecycle checks and adds an entry module.
Tier: A (fresh Opus verifier follows; live-data path).

## Where
Worktree `D:\Abhay\Ventures\OptionsForOptions2-gcmu-feed`, branch `build/gcmu-feed` (from `build/gcmu`). Commit there only. Never push. Never touch `main`, `feature/adjustments`, `build/settings`, any `build/gcset-*` tree. Do NOT edit `backend/ofo_app/live_market.py` (shared with another session); if unavoidable, stop and report.

## Read first
`gh issue view 520 -R abhayla/OptionsForOptions2` (items 1-3 are this brief), `work/W-137.md`, `spec/decisions/ADR-220.md` decision (1) (the five roles; liveprices = holds the only Kite live connections), `backend/ofo_app/feed_main.py` (esp. `_one`, ~lines 234-260, and `main` ~393), `tests_app/test_feed_session_expiry.py`, `tests_app/test_feed_user_isolation.py`, `tests_app/test_feed_restart_core.py`.

## Do, in order
1. CORE PROOF: run `tests_app/test_feed_restart_core.py` on the head as-is (DB tests: one file only, through `python scripts/orchestrator/db_run_fresh.py . python -m pytest -c pytest-app.ini tests_app/<file>.py`; the shared DB host also serves production - never a whole suite). Record pass/fail. A red core = stop and report.
2. #520 item 2 (failing test first): a test where the store read raises at/after `run.expires_at` -> the socket is ended (expiry check runs BEFORE the store read, it needs only in-memory expiry). Then move the check.
3. #520 item 1 (failing test first): the test store answers "no session" after expiry (production shape); a later reader still sees "session ended", not "stopped", for a fingerprint already in `expired`. Then fix.
4. #520 item 3: an isolation test on the throwaway database (`db_run_fresh.py`), two users, one user's session never drives the other's socket.
5. Name the liveprices role (ADR-220 (1)): a new entry module `backend/ofo_app/liveprices.py` so `python -m ofo_app.liveprices` starts the feed process (delegates to `feed_main.main`, no logic copied), plus a small `backend/ofo_app/roles.py` naming the five roles from ADR-220 (1) as constants with their start module (`liveprices` -> `ofo_app.liveprices`; the others listed with `None` until built, `background` is step 4). Test: a subprocess run of `python -m ofo_app.liveprices --help` (or the existing dry-run flag of feed_main) exits 0; roles test pins the five names.
6. Run in full every test file changed (DB files one at a time via db_run_fresh), plus guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan`, ruff on changed files, `python scripts/ruff_ratchet.py`. Logs to a file, tail only.

## Standing items
- One test per acceptance criterion (one per #520 item), each red before the fix, green after; record both runs.
- Every test file you changed is run in full; a skipped test counts as not run.
- Store answer states for `_one`: session stated, absent, read failed, expired fingerprint, store empty - each has a test (most exist; add the missing ones).
- Tier A: at most 5 mutants on a scratch copy (move the expiry check back after the read; drop the `expired` keep; etc.) each turns a test red.
- Known bypasses in the module docstring.
- No new duplicated literal; ruff/mypy baselines must not rise; no regenerated files.
- Commit after each item passes. End the report with the final commit sha on build/gcmu-feed.
