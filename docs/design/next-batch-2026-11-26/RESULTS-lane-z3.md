STATUS 18:56 IST | HEAD: the commit this file is pushed in on integration/weekend-r3-1129 (merge tree e5e302db36af9724f10e7c6476846c32ad520f88 plus this RESULTS file); earlier pushes 4d975129 and e2da71f5 (TOTAL PASS 1454.4s); 829ff65f: no recorded line | WAVE 0 MERGED: RA fix/r3-leftovers-1128 951aa698c (FD5 b093db5b2, FE4 9d8204079, migration 0062), FJ fix/r3-frontend-joins-1128 4aeb42652, FJ2 fix/r3-frontend-2-1128 68a46dd62; earlier: FJ ddd65680, fix/ic-live-test-1123 c4f4f0be | HELD: RA2 fix/r3-leftovers-2-1128 77315690e (coordinator hold) | NOT YET: wave 1 (22:45) | PROOFS on PostgreSQL 16 (local, per-file clone, local Redis): wave-0 tree before FJ2 (FJ2 changes only frontend): 716 passed, 1 xfailed, 1 failed (test_n7 in test_exit_door_real_fd3.py:292, Lane RA, see Defects); baseline on e2da71f5: 274 passed; the three FE2 tests (test_real_position_stops_fe2_1128.py) now PASS (5 of 5); migration 0061 to 0062 up, down, up: one head 0062_order_request_keys_expiry; frontend unit in the gate | REVIEW: pending (after the 10:00 freeze) | ROUND 3 READY FOR THE PC: no (waves 1 and 2 and the review are still to come)

# Lane Z3 (round 3 build), 28 Nov 2026

Paper only; no broker call made. Base: origin/integration/weekend-r2-1128 at 829ff65f26716f1efbcbac98ea3ba6aefdc350d9 (untouched, as is integration/weekend-1127).

## Decided for the owner
- Environment: ruff must be 0.15.12 as a Python module (`pip install ruff==0.15.12`; the ratchet fails closed otherwise), `pip install -r requirements-app.txt`, `npm ci` in frontend/.

## Batch 1 (FJ at 1ad97343)
| Step | Result |
|---|---|
| `git merge --no-edit origin/fix/r3-frontend-joins-1128` | clean, no conflict; 4 test files changed, 1 new (exit-rule-all-doors-r3-fj.test.js); no product file |
| 4 named Exit tests (vitest) | 4 files, 24 tests passed |
| ruff_ratchet | OK, no rule rose |
| repo_scan | 1644 passed, 3 skipped, 47 xfailed |
| select-app-tests + broker-name tests | 141 passed |
| prepush.py --jobs 2 on 631f1a03e6 | TOTAL PASS 1418.2s |


## Batch 2 (FJ ddd65680 and fix/ic-live-test-1123 c4f4f0be)
- FJ merge: clean. Product change: frontend/src/lib/unknownLocks.js, frontend/src/components/strategy/PaperStrategies.vue (+ tests).
- fix/ic-live-test-1123 (coordinator's order): conflicts in six files, all documents or process scripts; taken from the fix branch (`--theirs`), none in backend/, frontend/src/ or alembic. No product file changed by this merge.
  - docs/design/next-batch-2026-11-26/RESULTS-lane-g2.md (add/add)
  - docs/process/coverage-register.md
  - docs/process/gate-speed-2026-11-26.md (add/add)
  - docs/process/runbook.md
  - knowledge/findings/INDEX.md
  - scripts/orchestrator/prepush.py (--jobs kept, file parses)
  Auto-merged: coverage-stages.yaml, spec/decisions/ADR-330.md, tests/orchestrator/test_select_app_tests.py (to re-check in the gate).
- First check on 31c95bd4 FAILED (ci_checks step 14 and preflight scans: knowledge/findings/INDEX.md stale). Cause: that file is generated from both sides' findings and I had taken the fix branch's copy in the conflict. Fix: regenerated with `python tools/build_findings_index.py .` (200 findings), not by hand. domain_tests/app_tests/frontend_unit were stopped by the preflight failure, not failed on their own. Rule for later merges: knowledge/findings/INDEX.md is regenerated, never taken from a side.
- Plain `ruff check` on changed .py files shows 12 errors that arrive with the fix branch's files; the ratchet (the gate) is OK; not mine to edit.
- Side effect for the review: the gate on this branch is now the fix branch's faster check, so TOTAL PASS lines after this commit are from the newer prepush.py.

## Wave 0 (RA 951aa698c, FJ 4aeb42652, FJ2 68a46dd62)
- All three merges clean, no conflict, no side taken. One alembic head: 0062_order_request_keys_expiry (RA, narrows the INSERT grant of order_request_keys to six columns and adds expire_order_request_keys(); additive, round 2 code writes the same six columns). Up, down to 0061, up again on a local PostgreSQL 16: ok.
- Gate: ruff ratchet OK, repo_scan 1647 passed (47 xfailed), select-tests + broker-name tests 141 passed, findings index current (`build_findings_index.py --check`).
- Database proofs (list: the worker chain, exit watches, request-key, door, FE2 and every tests_app file this wave changed; `OFO_TEST_DB_PER_FILE=1`): 716 passed, 1 xfailed, 1 failed. The three FE2 tests that failed on round 2 now pass.
- Check lines per pushed commit are in the STATUS line.

## Defects found
- D1 (Lane RA, tests_app/test_exit_door_real_fd3.py:292, `test_n7_a_stop_stored_then_a_failed_kind_read_still_answers_success_with_the_line_unknown`): `assert calls["n"] >= 2` gets 1. FD5's N7 expected the answer to read the position kind a second time after the commit and fall back to "unknown"; RA's N7 (routes/paper.py create-trigger and cancel routes, comment "RA N7 (Opus F-2)") reads the kind once BEFORE the commit and passes it to `_triggers_out(kind=...)`, so no second read happens. It fails on RA's own branch alone (13 passed, 1 failed, run in a temporary worktree), so it is not a merge artefact. Both designs fail closed (a failed read before the commit refuses with nothing changed; the stored stop is never reported live). The owner lane decides whether the test's assertion is stale or the second read must come back; I did not edit either. Not in the pre-push gate (database tests are CI's).

## To file as deferred issues
- D1 above.
