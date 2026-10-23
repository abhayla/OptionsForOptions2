# Row 10 finish 2: REQ-118 (W-138) - two red repo guards, the busy text on user routes, the R13 run

Common brief: docs/process/builder-brief.md (Budget hard stop: at 48 calls start nothing new, commit, report). Run
`python scripts/orchestrator/mutation_gate.py` on the new route guards before reporting; quote its results file (R18).
Size: M, 7 files, 3 items
CI: kit tests job (`tests/errors/test_write_allowlist.py`, `tests/errors/test_producer_inventory.py`, the guard line;
vars: none); app job `api` step (`tests_app/test_rate_limit_door.py`, the route test files you touch, and the R13 list
`...\scratchpad\row10\dbfiles.txt`; vars: TEST_DATABASE_URL only).
Expected (orchestrator, before dispatch, clock 09:5x): 40 min / ~150k (finisher 2, fresh agent - R5).

Core: a user action refused because Zerodha is busy tells the user "Zerodha is busy - try again in a moment" - never
a generic broker error and never a wrong figure.
Proof: step 1 is a route test failing first: the fake Kite door answers 429 twice on a quote read behind a user route
-> the reply's message is exactly the REQ-118 AC-3 text, rendered from its one home through the error envelope.

Spec basis: REQ-118 AC-3: "is refused at once with "Zerodha is busy - try again in a moment", never queued without
bound." The wording is settled by the requirement itself (no owner read needed). REQ-118 AC-4 (a failed read applies
the caller's stale or fail-closed rule).
Copy from: none beyond the row brief's map rows.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`, head ae5fe864 - the only agent
writing here. Leave the orchestrator's uncommitted files alone. Commit ONLY your own paths with
`git commit -F <msg> -- <your paths>`; never `git add -A`, `stash`, `checkout --`, `reset`, `restore`; do NOT push.
BINDING: never stop a process by name (taskkill /IM, Stop-Process -Name, pkill, killall) - record and stop only your
own PIDs. Database only through `fresh_launch.py` (the one lock). Scratch:
`...\b9b5cb32-ea0c-400f-80e1-fbd7045cbf2a\scratchpad\row10-finish2`.

## What to do
1. The two red repo guards (`tests/errors/test_write_allowlist.py::test_backend_ofo_writes_only_through_self_or_cls_or_a_named_allowlist_entry`,
   `tests/errors/test_producer_inventory.py::test_every_producer_in_scope_is_routed_through_render`): first run both on
   main 3ccc8439 (`git worktree add` a temp copy in your scratch folder, then a PLAIN `git worktree remove`) to tell
   old from new; fix the new ones IN CODE (likely `rate_limit.py`'s `_installed` holder dict and the top-level
   `ZERODHA_BUSY_TEXT` import), never by loosening a guard.
2. The busy text on user routes: the routes that catch the limiter's busy refusal (`KiteReadError` with the busy code,
   `kite_margin_busy`, `kite_read_busy`) answer with a gate template carrying the AC-3 text from its one home
   (`ZERODHA_BUSY_TEXT`); add the template, its pins (the template-pins test) and a route test per caller group; a
   changed reply model regenerates `docs/api/openapi.json`.
3. R13: run the list in `...\scratchpad\row10\dbfiles.txt` through
   `python D:/Abhay/scratch/ofo2-builder-sequence/fresh_launch.py D:/Abhay/Ventures/OptionsForOptions2-builder-reqs python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini -o faulthandler_timeout=60 <files>`,
   started FIRST in the background; identify every failure; run each on main to tell yours from old; fix yours.

Attack list: (each names its test file)
1. Both repo guards green, no guard loosened (`tests/errors/test_write_allowlist.py`, `tests/errors/test_producer_inventory.py`).
2. A busy quote read behind a user route -> the exact AC-3 text (the route's test file).
3. A busy margin read -> the margin gate blocks and the user sees the AC-3 text, no figure (`tests_app/test_kite_margin_client.py` or the outcome margin tests).
4. A busy positions/orders read -> the AC-3 text, last rows kept as stale (the route's test file).
5. Every R13 file listed with its result; each failure classified yours/old by its main run (report).

Standing items: (a) n/a: no time-budgeted job change; (b) n/a: no CI step changes; (c) the repo guards stay allow-lists and fail closed; (d) the limiter's answer states for a user route - slot granted, busy (wait > 5 s), 429 after retries, timeout, write refused - each mapped to what the user sees in the route tests.
Threat model: in scope - a busy refusal shown as a wrong figure or a raw error, a guard loosened to pass, a dependent test left red; out of scope - the real Notifier sender.
Findings checked: dependent-tests-not-run-stale-later, guard-as-forbidden-list, process-kill-by-name-hits-others
Reviewer checklist: guards fixed in code; AC-3 text from one home; template pins updated; openapi regenerated if a
model changed; every R13 failure classified; gate results quoted; no new duplicated literal; reuse the existing helper;
ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR except openapi.json.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table
