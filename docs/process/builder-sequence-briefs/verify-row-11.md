# Verifier brief: builder sequence row 11 (REQ-114 feed health check and reconnect, price socket part / W-139), Tier A, round 1

Independent, adversarial verifier; you built none of it. READ-ONLY: never edit, create, commit or delete a tracked file
in any checkout; scratch and mutation copies only in
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\b9b5cb32-ea0c-400f-80e1-fbd7045cbf2a\scratchpad\verify-11`.

Code under test: worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-next`, branch `build/seq-row-11`, head <HEAD>
(part A 799b16ab backend; part B <B-SHA> frontend; base fb9a3702). Briefs: `docs/process/builder-sequence-briefs/row-11a-REQ-114-feed-health-backend.md`
and `row-11b-REQ-114-reconnect-text-frontend.md` (in the main sequence worktree `...\OptionsForOptions2-builder-reqs`;
read them there) - run every item of both `Attack list:` sections. Spec: `spec/requirements/REQ-114.md` (every AC),
ADR-015, ADR-053, ADR-119, F-32, F-54. The order-update stream parts are deferred (order path).

Attack first: (1) silence is measured on the CONNECTION (any frame, heartbeat included), never one contract's tick age
(F-32): quiet contracts with heartbeats -> no reconnect; 59.9 s vs 60.0 s on the injected clock; (2) back-off 1 s
doubling to a 30 s cap with up to 50% jitter (seeded test); a drop before the first data frame never resets it (no
storm); (3) `on_connected` only after every subscription is re-sent; quotes stale until a fresh tick; (4) a token-error
frame or a 403 ends the session, never retried in a loop; (5) market closed (a weekend, the 2026-10-20 holiday from the
dated NSE calendar `backend/ofo/market_calendar.json`, F-54): "market closed - last price <time>" and at most one
reconnect per 5 min; `timeutil.market_open` was REMOVED and replaced by `market_calendar.is_market_open` - find every
former caller (grep the whole backend and tests_app) and prove each now uses the calendar and that Execute's hours
gate is unchanged on a normal trading day and closed on the holiday; (6) logs carry the user, reason and timestamps,
never the token; (7) the browser shows exactly "Reconnecting - prices as of <time>" with the last push's SERVER time
in IST (a browser clock 5 h off changes nothing) and switches to live on the first fresh push; (8) the builder of part A
ran `ruff --fix` over the whole backend by mistake and restored the files - prove no file outside the row's list
changed (`git diff --stat fb9a3702..HEAD` names only the row's files); (9) the "market closed" template was marked
"pending owner read" - its wording comes from REQ-114 AC-7; check the pin; (10) delete each guard in scratch copies:
run `python scripts/orchestrator/mutation_gate.py` with your own mutants (results to your scratch folder).

Database: the row's builders ran NO database test (ADR-171 rule 4 kept the slot for row 10). YOU run the R13 selection
for this row's backend diff through
`python D:/Abhay/scratch/ofo2-builder-sequence/fresh_launch.py D:/Abhay/Ventures/OptionsForOptions2-builder-next python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini -o faulthandler_timeout=60 <files>`
- NOTE the checkout argument is THIS row's worktree (`-builder-next`), never the main sequence worktree; it holds the one
lock (WAITING is correct); start it first in the background. Classify every failure by running it on fb9a3702 (the
chunk head) in a temp worktree (plain `git worktree remove` after). Frontend: `npm run lint`, `npm run test:run` in
`frontend/` of this worktree; the e2e `feed-reconnect.spec.ts` if a Chromium is available (`PW_CHROMIUM_PATH`).
Known flaky, not this build: `tests/test_edit_lint_hook.py::test_real_eslint_run_flags_unused_variable`,
`tests_app/test_broker_status_route.py::test_core_proof_a_stored_session_reads_connected_and_ending_it_reads_disconnected`,
`frontend/tests/learn.test.js` (CRLF). Do NOT call Kite live.

Why Opus: Tier A (live-data liveness: a silent socket shown live, a reconnect storm, a holiday read as open on Execute).
BINDING: never stop a process by name; stop only PIDs you started. Kit guard: a shell command naming spec/, tools/,
.claude, factory, views or .github is blocked; use Read/Grep/Glob.

Return a JSON array, one object per AC: `{"row": 11, "req": "REQ-114", "ac": "AC-n", "result": "pass" | "fail" |
"partial" | "deferred", "commands": "...", "observed": "... file:line", "attack": "..."}`, then under 250 words: each
fail/partial with severity (CRITICAL / MAJOR / MINOR) and the smallest fix, and anything not checked.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 40 min wall-clock, 70 tool calls
Report: evidence-table
