# Row 10 finish: REQ-118 (W-138) - prove the write-retry guard, lint back to baseline, busy text shown, R13 run

Common brief: docs/process/builder-brief.md (Budget hard stop: at 64 calls start nothing new, commit, report; R13-R18).
Size: M, 8 files, 5 items
CI: kit tests job (`tests/broker/test_rate_limit.py`, `tests/test_kite_http_guard.py`; vars: none); app job `api`
step (`tests_app/test_rate_limit_door.py`, `tests_app/test_kite_margin_client.py`, and every R13 file; vars:
TEST_DATABASE_URL only).
Expected (orchestrator, before dispatch, clock read at dispatch): 45 min / ~170k (a finisher, fresh agent - R5).

Core: a call that creates something at Zerodha is never retried - proven by a test that dies when the door's read-only
retry check is removed (mutants M8 urllib door, M9 httpx door survived the build).
Proof: step 1 - re-run M8 and M9 with `python scripts/orchestrator/mutation_gate.py` (on the branch since 83842bf3)
and find WHY the login-exchange tests did not kill them (likely: those tests stub below the door, so the door's retry
branch never runs); then a test through the REAL door: a 429 and a timeout on `POST /session/token` -> exactly one
request reaches the fake server; red on M8 and on M9.

Spec basis: REQ-118 AC-5: "A rate-limit answer or timeout on a call that creates or deletes something at Zerodha (a
trigger, REQ-100) is never retried". REQ-118 AC-3: "is refused at once with "Zerodha is busy - try again in a moment",
never queued without bound." REQ-118 AC-4 (the margin gate blocks on a failed read, ADR-094).
Copy from: none beyond the row brief's map rows.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`, head a11b61ee. You are the
ONLY agent writing here (ADR-171 rule 12). Leave the orchestrator's uncommitted files alone (`.claude/*`,
`docs/process/*`, `spec/*`, `scripts/orchestrator/overlap_gate.py`, `tests/orchestrator/test_overlap_gate.py`): commit
ONLY your own paths with `git commit -F <msg> -- <your paths>`; never `git add -A`, `stash`, `checkout --`, `reset`,
`restore`; do NOT push. Scratch: `...\b9b5cb32-ea0c-400f-80e1-fbd7045cbf2a\scratchpad\row10-finish`. The builder's
results and mutants: `...\scratchpad\row10\` (`mutation-results.txt`, `red-run.txt`, its mutate script).

## What to do
1. M8/M9 (above): a killing test through the real door for both modules; quote the gate's results file.
2. Lint: `python scripts/ruff_ratchet.py` rose on C901, E501, I001, PLR2004, RUF059, RUF100, S105, SIM300 - fix every
   rise in row 10's files (a11b61ee and yours) until the ratchet says OK; never by raising a baseline.
3. AC-3 user text: where a user-facing route gets a busy refusal from the limiter (quotes, margin, positions/orders
   reads behind a route - grep the callers named in the row brief), the reply carries the busy text from its ONE home
   (`ZERODHA_BUSY_TEXT`, errors templates) through the existing error envelope; a route test per caller group.
4. The margin half of attack 3: a 429 twice on the margin read -> the margin gate BLOCKS (ADR-094), never a wrong
   margin figure (`tests_app/test_kite_margin_client.py` or the outcome margin tests).
5. R13: run every `tests_app` file importing a changed module (31 files at the build) through
   `python D:/Abhay/scratch/ofo2-builder-sequence/fresh_launch.py D:/Abhay/Ventures/OptionsForOptions2-builder-reqs python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini -o faulthandler_timeout=60 <files>`
   - it holds the ONE database lock and waits if another run holds it; start it FIRST in the background; identify every
   failure (the build's partial run showed failures at the start, unidentified), run each failing test on main
   (3ccc8439) to tell yours from old, and fix yours.
Out of scope (recorded by the orchestrator as AC-6 partly built): a real Notifier HTTP sender - it needs the egress
gate opened to a new host, a separate reviewed item.

Attack list: (each names its test file)
1. A 429 on `POST /session/token` through the urllib door -> exactly one request (`tests_app/test_rate_limit_door.py`).
2. The same through the httpx door (same file).
3. A timeout on the login exchange -> exactly one request (same file).
4. A busy refusal on a user route -> the reply's text is the busy text from its one home (`tests_app/test_rate_limit_door.py` or the route's test file).
5. Two 429s on the margin read -> the margin gate blocks (`tests_app/test_kite_margin_client.py`).
6. The ratchet says OK; every R13 file listed with its result (commands in the report).

Standing items: (a) background jobs never take a user action's slot ahead of it (already tested - keep it green); (b) n/a: no CI step changes; (c) the door-coverage scan (tests/test_kite_http_guard.py) keeps failing closed on a door it cannot resolve; (d) Kite's answer states for a limited call - 200, 429, other 4xx, 5xx, timeout, refused, malformed - each still listed in `tests_app/test_rate_limit_door.py`.
Threat model: in scope - a retried write, a busy refusal shown as a wrong figure or a raw error, a lint rise reaching CI, an unrun dependent test; out of scope - the real Notifier sender.
Findings checked: dependent-tests-not-run-stale-later, caller-supplied-verdict-trusted, guard-as-forbidden-list
Reviewer checklist: M8/M9 red through the real door; ratchet OK; busy text from one home; margin gate blocks; every R13
failure identified and run on main; mutation results quoted from the gate's file; no new duplicated literal; reuse the
existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR (a changed API
reply model regenerates `docs/api/openapi.json`).

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table
