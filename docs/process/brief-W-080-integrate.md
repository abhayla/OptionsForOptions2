# Builder brief: W-080 integration with today's main before merge (Tier A: egress gate)

Core: on branch `land/W-080` (worktree below, main already merged in at 3 commits past bd19ba7), every test under
`tests/` passes while the runtime egress gate keeps refusing, IN THE API PROCESS, every non-loopback/non-database connect
and every process start outside a door. Two current reds: (1) `tests/errors/test_write_allowlist.py` flags
`backend/ofo/broker/egress.py:230` and `:238` (`_PENDING.ok = ...`, a thread-local written outside self/cls); (2)
`tests/test_edit_lint_hook.py::test_real_ruff_run_names_rules` fails with `EgressRefused: subprocess.Popen refused: the
backend starts no process` because `import ofo` installs the gate process-wide and the hook test starts ruff.
Proof: both tests green; `tests/test_egress_gate.py`, `tests/test_no_order_placement.py`, `tests/test_door_names_private.py`,
`tests/broker` and `tests_app/test_egress_gate_doors.py` still green; plus a new test proving the API process still
refuses a process start and a connect to 192.0.2.1 after your change.

Model: opus.
Budget: 40 min wall-clock, 75 tool calls. At budget STOP and report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under 250 words, head sha pushed.
Copy from: none - this branch's `backend/ofo/broker/egress.py`.
Findings checked: guard-by-banned-shapes, targeted-tests-miss-dependent-files, live-work-shares-test-database
Tests: `python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/broker tests/execution` and `tests_app/test_egress_gate_doors.py` via the main checkout's `scripts/orchestrator/db_run.py <worktree> ...`.

## Spec basis
REQ-073 AC-4 and its scope text (ADR-098, on this branch); ADR-054; ADR-093/REQ-075 (the write allow-list guard).

## Constraints
- Fix (1) the way the write-allowlist guard intends: either a named ALLOWLIST entry with a reason (the gate's own
  thread-local state) or rewrite the thread-local writes so the guard accepts them. Do not weaken the guard.
- Fix (2) without any switch that app code could flip to turn the gate off (no env var, no module flag reachable by a
  literal name). Acceptable shapes, your choice with a reason: the gate is installed by the API entry point (app
  startup) instead of on `import ofo`, keeping a test that `create_app()` / the lifespan installs it before the first
  request; or an explicit, closed allow-list of program files the gate lets start, held by the gate module itself.
  If you move installation, every round 1-10 egress test must still install the gate the way the app does.
- Think about every other process that imports `ofo`: alembic migrations, `scripts/orchestrator/*`, the domain test
  suite, dev scripts that call Kite read-only. List what changes for each.
- Never connect anywhere except loopback/192.0.2.1 in tests; no Kite requests.

## Where
Worktree `C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\159f685c-1dc7-4616-a983-d235398aeeff\scratchpad\wt-w080`
(branch `land/W-080`, pushes to `origin land/W-080:land/W-080-r8`). Commit messages without the word "spec"; no PR;
never write `evidence/`, `work/` or the spec.
