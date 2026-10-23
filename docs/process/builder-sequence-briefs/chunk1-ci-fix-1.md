# Chunk 1 CI fix 1: the three red jobs on draft PR #525 (row 11's 14 database failures, two test-harness reds)

Common brief: docs/process/builder-brief.md (Budget hard stop: at 64 calls start nothing new, commit, report).
Size: M, about 10 files, 3 items
CI: app tests job `api` (the 14 failures below); kit tests job `lint-and-test`; app tests job `frontend` (its pytest step runs `tests/test_bundle_secret_scan.py`).
Expected (orchestrator, before dispatch): 45 min / ~250k.

Core: CI run 39936199752 (`api`) and 39936199933 (`lint-and-test`) on chunk head 0e574b58 are red. Logs are in
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\7a0c81e3-1fa0-4c0c-ab2b-6ae5a07ae075\scratchpad\api.log`,
`ci-kit.log` and `fe.log` in the same folder. Never read a whole log; grep it.
Proof: step 1 runs the listed failing tests and sees them fail for the logged reason, for example
`TypeError: WorldSocket.__init__() got an unexpected keyword argument 'user_ref'`. After the fix the same tests pass,
and CI on the pushed head is green for the three jobs.

RCA (one per class; confirm each before fixing):
1. Row 11 (REQ-114 AC-8) added a `user_ref` argument to the live socket. The test fakes and door registries that
   mirror the socket's signature and public names were not updated. Class: every test fake or registry that copies a
   signature or the public name list of `backend/ofo_app/kite_ws.py`, `live_market.py` or `feed_main.py`. Grep for
   `WorldSocket`, `FakeSocket`, `__all__` users and door-name lists, not only the 14 failing tests.
2. `tests/orchestrator/test_db_run_fresh.py` imports `scripts/orchestrator/db_run_fresh.py`, which imports `asyncpg`.
   The kit tests job installs only `pyyaml jsonschema pytest`, so the module import fails at collection. Class: every
   `tests/` file whose import chain reaches an app-only package (`asyncpg`, `fastapi`, `httpx`, `sqlalchemy`).
3. `tests/test_bundle_secret_scan.py::test_with_ci_set_and_no_build_the_bundle_scan_fails_and_without_ci_it_skips`
   still toggles `CI`, but the scan now switches on `OFO_REQUIRE_BUNDLE_SCAN`. In the frontend job, where that
   variable is set, the "skips" half fails.

The 14 failing tests (all in `tests_app/`): `test_live_login_pickup.py` (9:
test_session_ended_goes_live_after_a_login, test_two_logins_at_once_start_one_socket,
test_live_on_a_and_a_login_stores_a_again_does_not_restart,
test_session_ended_on_a_with_b_already_stored_restarts_onto_b_once,
test_session_ended_with_a_still_stored_reads_once_and_does_not_loop, test_close_cancels_a_pending_re_read,
test_start_with_a_session_builds_the_socket_without_logging_the_token, and the two at lines 147/166/197),
`test_egress_gate_doors.py::test_each_doors_public_names_equal_all[ofo_app.kite_ws]`,
`test_zerodha_rules_cited.py::test_the_real_tree_has_every_rule_cited_and_every_order_type_site_listed`,
`test_kite_ws_resubscribe.py`, `test_strategy_live_push.py`
(test_a_live_state_with_a_finished_socket_task_is_not_connected), `test_reconnect_positions_read.py`, and
`test_the_socket_door_opens_door_context_only_for_the_real_connect`. Confirm the full list from `api.log`.

Fix rules:
- Update the fakes and registries to the real signature and names. Do NOT loosen a guard: a door-name or
  rules-cited test is fixed by listing the new name or rule with its citation, never by widening a pattern or
  skipping. If a test shows a real product defect (for example `user_ref` not passed on a real call path), fix the
  product code and say so; that makes the checker Opus.
- Item 2: `pytest.importorskip("asyncpg")` before the import, with a comment naming the kit job.
- Item 3: the self-test sets `OFO_REQUIRE_BUNDLE_SCAN=1` for the fail half and removes it (`raising=False`) for the
  skip half, and also removes `CI` for the skip half.

Spec basis: CLAUDE.md fast delivery rule 5: "Red CI or a failed core proof is never deferred". REQ-114 AC-8 (the
socket's log lines carry the user reference). ADR-178: database tests run in GitHub CI through the draft chunk PR.
Copy from: none - test harness fixes, no legacy module.
Reference: screens 010-039 - copy nothing new here: REQ-114's open records RD-039, RD-046, RD-047, RD-065, RD-066, RD-068 are the chunk-1 copy builder's, not this fix's.
Mutation gate: run `python scripts/orchestrator/mutation_gate.py` on any guard you touch (door names, rules cited) and quote its results file; a test-fake-only change needs no mutants - say so.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-ci-fix`, branch `build/seq-chunk1-cifix`, from chunk head 0e574b58.
Commit with `git commit -F <msg> -- <your paths>`; do NOT push. BINDING: never stop a process by name; stop only
PIDs you started. Database: ONE local run only, of the failing `tests_app/` files, through
`python D:/Abhay/scratch/ofo2-builder-sequence/fresh_launch.py D:/Abhay/Ventures/OptionsForOptions2-ci-fix python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini -o faulthandler_timeout=60 <files>`
(it holds the one database lock; waiting is correct). Output to a log in your scratch folder; tail only. CI re-runs
everything after the orchestrator pushes. If a write is refused by `verifier_inflight_gate` (a verifier of another
row is running), wait 2 minutes and retry once. If it is still refused, keep working on reads and edits, and report
which commits are pending. Scratch:
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\7a0c81e3-1fa0-4c0c-ab2b-6ae5a07ae075\scratchpad\ci-fix`.

Attack list: (each names its test file)
1. The live socket built with a session logs `user=` and never the token; the fake takes `user_ref` (`tests_app/test_live_login_pickup.py`).
2. The `kite_ws` door's public names equal its `__all__` with the new name listed, not a widened pattern (`tests_app/test_egress_gate_doors.py`).
3. Every Zerodha rule is cited in the real tree, including any site row 11 added (`tests_app/test_zerodha_rules_cited.py`).
4. The kit job collects `tests/orchestrator/` without `asyncpg` installed (`tests/orchestrator/test_db_run_fresh.py`).
5. With `OFO_REQUIRE_BUNDLE_SCAN=1` set externally, the bundle self-test passes both halves (`tests/test_bundle_secret_scan.py`).

Standing items: (a) n/a: no time-budgeted job; (b) the kit job's install step is unchanged, and the import is skipped where the package is absent; (c) no detector is loosened; a registry gains entries, never wider patterns; (d) n/a: no other system's answer is decided on.
Threat model: in scope - a guard loosened to make CI green, a real `user_ref` defect hidden by a fake; out of scope - row 11's product behaviour (verified in round 2).
Findings checked: dependent-tests-not-run-stale-later, guard-as-forbidden-list
Reviewer checklist: each of the 14 failures named with its RCA class and fix; no skip or widened pattern added
except the asyncpg importorskip; the class grep quoted; no new duplicated literal; reuse the existing helper;
ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table
