STATUS 00:09 IST | WAVE 1 HEAD ON ORIGIN: integration/weekend-r3-1129 at 8425feead324acc7bdac0abd9cf4a78f8f6d68c9, prepush --jobs 4 TOTAL PASS 1042.8s on that commit (wave 0 a1d70422599c0db530f98b66cec2c8b886da8c66 TOTAL PASS 954.9s; e2da71f5 TOTAL PASS 1454.4s; 4d975129 TOTAL PASS 1374.3s; 829ff65f: no recorded line); this hand-over is on branch docs/z3-handover-1129 (docs only, so the CI run on pull 881 is not cancelled) | MERGED: FJ 4aeb42652, FJ2 d93fce449, RA 951aa698c, RA2 dc1aeebd8 (nothing newer), B2 b2e8e29c3 (migration 0064), F2 4e8074a07, F3 505542d80, T 5342dcb2c, fix/ic-live-test-1123 c4f4f0be | LEFT OUT: B3 ecf8e8f99 (order B), RA2 after dc1aeebd8 (only via B1b), feat/real-same-screens-*, f23-handoff | DB PROOFS on 8425feea (PostgreSQL 16, 76 files, one clone per file): 1086 passed, 1 xfailed, 6 failed (see Found, not assigned: F-1 to F-5); FE2's three tests pass | REVIEW: not done (owner's order of 23:35: no new tasks, no successor review) | PULL ORDER: not written | CI on 8425feea: still running when this was written | ROUND 3 READY FOR THE PC: no | SAFE TO CLOSE

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

## Wave 1 (rebuilt without B3; one combined check)
Order of merge on a1d70422: RA2 dc1aeebd8, B2 b2e8e29c3, FJ2 d93fce449, F2 4e8074a07, F3 505542d80, T 5342dcb2c. A first build that included B3 (ecf8e8f99) failed three ways and was dropped by the coordinator's order B (kept locally as branch backup-z3-w1-with-b3 at 63917b44, never pushed).
| Conflict | Resolution | Side |
|---|---|---|
| backend/ofo/errors/templates.py (B2 vs RA2) | both gates kept: `execution_return_changed` (589, RA2) and `order_outcome_unknown` (590, B2) | both |
| frontend/src/components/strategy/AdjustPlanSheet.vue (F3 vs F2) | F2's levels logic (coordinator's rule). F3's side had `?? ''` and cleared all boxes when the server gives no figure; F2's keeps a typed box and clears only a server-filled stale one | F2 |
| frontend/src/components/strategy/PlanEntry.vue (F3 hand-off vs F2; git merged both without a text conflict, then the build failed: `levelText` declared twice) | F2's file taken whole. F3's only change here was the FJ2-9 Target/Stop block, which duplicates F2's I-197 `planLevels` block (same test ids), so both cannot stand. The Plan card prints F2's wording ("Stop: 15.38 % (Rs 400.00)", "No stop is set for this trade."), not FJ2-9's ("Stop: 25.00 % of max loss", "not set"); both pending owner read | F2 |
| docs/process/friction-log.md (F3 vs B2) | rows of both kept | both |
- Migration: B2's `0063_order_attempts.py` renamed `0064_order_attempts.py` (git mv; revision id, `Revises`, the `_load` module name, one docstring line of tests_app/test_order_outcome_b2_1128.py). No other file named the old id. B2's migration holds no copy of the allow-list chain text (it only calls the allow-list function with 'pre' and 'post'), so it does not compete with RA2's 0063. Fresh PostgreSQL 16 database: upgrade head 81 s; downgrade to 0062 59 s; upgrade 59 s; `alembic heads`: one (0064_order_attempts).
- Gate before the check: ruff ratchet OK, repo_scan 1647 passed, template-code + select-tests + broker-name tests 143 passed, frontend lint 0 errors and build ok, findings index current.
- What went wrong on the way (all mine or the environment, all fixed before any push): (1) I committed test_select_app_tests.py with conflict markers because the command that removes them was blocked and I did not read its result (the ratchet's `invalid-syntax` caught it); (2) the PlanEntry.vue double declaration above; (3) the container lacked `fakeredis` (a lane added it to requirements-dev.txt): `pip install -r requirements-dev.txt -r requirements-app.txt`; (4) the B3 clashes.

## Decided for the owner (wave 1)
- The Plan card's stop and target lines come from F2's version (I-197), as the coordinator's rule says, not from the hand-off's FJ2-9 version. To keep the gate green I REMOVED `frontend/tests/plan-card-levels-fj2-1128.test.js` (3 tests, all about the dropped block); `plan-entry-levels-f2-1128.test.js` has 10 tests on the same states. I did this before the coordinator's rule "do not remove another lane's tests in a merge": the coordinator can reverse it (restore the file from backup-z3-w1-with-b3 or origin/fix/r3-frontend-f3-1128) and then F3 or FJ2 must re-write it against F2's wording.

## Question for the owner
- Wording of the orders line beside the closed-market sentence: with "The market is closed." (RA2 item 9, d9b55050a, the older pinned tests moved with it) or without (B3 item 4, its test test_the_entries_sentences_do_not_repeat_the_market_closed_prefix). The build has RA2's wording.

## Hand-over for my successor (Lane Z4)
- Branch: integration/weekend-r3-1129; the head is on origin after the wave 1 push. Local DB for proofs: `pg_ctlcluster 16 main start`, `redis-server --daemonize yes` (dump dir /tmp), database ofo_test (migrate to head with ALEMBIC_DATABASE_URL=postgresql+asyncpg://postgres:postgres_ci_dummy_pw@localhost:5432/ofo_test), roles as in .github/workflows/app-tests.yml; proof runner is a scratch script: pytest -c pytest-app.ini with OFO_REQUIRE_DB_TESTS=1 OFO_TEST_DB_PER_FILE=1, TEST_DATABASE_URL (ofo_app) and TEST_ADMIN_DATABASE_URL (postgres), REDIS_URL, the CI Kite placeholders and a generated BROKER_TOKEN_KEY. Never use db_run.py here (it targets the owner's host).
- Environment of a new container: `pip install ruff==0.15.12` (the ratchet needs the module), `pip install -r requirements-dev.txt -r requirements-app.txt`, `npm ci` in frontend/, `git fetch --unshallow`.
- Rules learned: knowledge/findings/INDEX.md is regenerated with `python tools/build_findings_index.py .`, never taken from a side; template_pins.json conflicts are merged as data (union of keys); after every conflict resolution run `python -c "import ast..."` on the file and `git grep -nE '^(<<<<<<< |>>>>>>> )'`; a `git commit` must be its own call; `--jobs 4` (nproc 4, 14 GB free).
- Wave 2 (01:45 IST): RA2 only through B1b (fix/r3-backend-b1b-1128); B3 on its own branch once it drops its duplicate template and uses RA2's key; R1 and R2 (feat/real-same-screens-*) only from a commit the coordinator names; R1's 0063_position_tags will need renumbering (0065 or later). Final wave 08:00, freeze 10:00.
- Open at the freeze: the Opus review (attack list in the scratch notes: releaseForeignDecided, adoptForeignLock, reload lock window with and without B2's server block, routes/execute.py Execute door deadline, the Redis key store, real Exit path in LiveStrategyCard, RA2 88500c2a9..940fb2240, round 2's minors T1, N2, T2, G1, N5 to N8, F1, F3); the PC pull order (migration step "against the live database with the method the PC used for 0059 to 0061", never db_run.py; per migration beyond 0061 whether round 2 code runs on it, 0062: yes, 52 tests of round 2 head 829ff65f pass on a database at 0062; rollback; restart order API, worker, feed, frontend server); the final STATUS "CI on <commit>: green / red / still running".


## Database proofs on the wave 1 head 8425feea
Runner: scratch script (not in the repo): `pytest -c pytest-app.ini -q -rs -p no:cacheprovider <76 files>` with OFO_REQUIRE_DB_TESTS=1, OFO_TEST_DB_PER_FILE=1, local PostgreSQL 16 database ofo_test migrated to 0064_order_attempts (owner role postgres, app role ofo_app), local Redis, the CI Kite placeholders. The 76 files: the worker chain, exit watches, request-key, door, FE2 and FD2/FD3 files plus every tests_app file changed by waves 0 and 1 (including `*_b2_1128` and `*_ra2_1128`).
| Run | Head | Result |
|---|---|---|
| baseline | e2da71f5 | 274 passed (28 files) |
| wave 0 tree (RA + FJ) | before FJ2 | 716 passed, 1 xfailed, 1 failed (test_n7) |
| round 2 code on a database at 0062 | 829ff65f | 52 passed (request-key, paper-orders, exit-door-real, worker-chain files) |
| wave 1 | 8425feea | 1086 passed, 1 xfailed, 6 failed (below) |
Migration chain on a fresh database: upgrade head 81 s, downgrade to 0062 59 s, upgrade 59 s; one head 0064_order_attempts. The three FE2 tests of tests_app/test_real_position_stops_fe2_1128.py that failed on round 2 pass.

## Removed tests (coordinator confirmed: keep the removal; Lane F2 proves each case is covered or adds it in wave 2)
`frontend/tests/plan-card-levels-fj2-1128.test.js` had four tests, all removed with the file because F2's PlanEntry.vue replaced the block they test:
1. plan with both: "Target: 50.00 % of max profit" and "Stop: 25.00 % of max loss" (the server's words) (failed under F2's file)
2. the server sent a figure but no words: the figure with its percent unit (failed)
3. no target and no stop in the plan: each says it is not set, never a blank or a 0 (failed)
4. no plan at all: no target / stop lines (the "No plan" line stands) (passed either way; removed with the file)
Restore from origin/fix/r3-frontend-f3-1128 if wanted.

## Found, not assigned (owner's order of 23:35: not fixed, not handed on; evidence from the wave 1 database run, /tmp log not kept)
- F-1 tests_app/test_exit_door.py:732 (2 tests: test_monitor_and_tracking_exit_at_once_one_wins_no_deadlock[before_claim] and [before_place]): the test's cleanup `_remove_paper_rows` (test_exit_door.py:615) calls `_remove_own_rows` (tests_app/test_execution_plan_store.py:539), which runs `DELETE FROM public.strategies WHERE user_ref = ...`; B2's new table order_attempts has a foreign key to strategies, so the delete fails: `ForeignKeyViolationError ... order_attempts_strategy_id_fkey ... Key (id)=(35) is still referenced`. The cleanup helper does not know B2's table. Owner lane: B2 / Lane T (tests).
- F-2 tests_app/test_order_request_key_durable_fd3.py:208 (test_an_unknown_outcome_leaves_a_hint_and_the_durable_table_decides_the_repeat): after a commit that crashed (outcome unknown), repeating the SAME key and body returns 409 STRATEGY_VALIDATION_590 ("An earlier order for this strategy has no known result yet.", B2's block) where FD3's contract expects 201 (the durable table replays/decides). B2's block refuses every further order request "whatever its key or body"; FD3's test expects the same key to be decided by the durable key table. Two lanes' designs disagree on what a same-key repeat after an unknown outcome does; this is a product behaviour question on an order path. Needs the owner's decision (ADR-016 to ADR-019, ADR-330 (58)).
- F-3 tests_app/test_paper_triggers_routes.py:554 (test_d05_two_identical_saves_at_one_instant_on_two_connections_store_one_row): `assert (r1.status_code, r2.status_code) == (201, 201)` got (201, 409). Same family as F-2 (B2's one-open-attempt-per-strategy block answering the concurrent identical save with 409 instead of the stored answer). Owner lane: B2.
- F-4 tests_app/test_route_latency_budget.py: `adjustment-check: 388 ms alone, budget 200`. This file already failed on round 2 (Lane Z2's list: statement counts over ceiling in the same file), so it is probably not new; not attributed.
- F-5 (known as D1 below): tests_app/test_exit_door_real_fd3.py:292 test_n7; CI on pull 881 saw it on wave 0 too.
- Wording question for the owner (RA2 vs B3): the orders line beside the closed-market sentence with "The market is closed." (RA2 item 9, d9b55050a, in the build) or without (B3 item 4).
- Environment: a new container needs `pip install ruff==0.15.12`, `pip install -r requirements-dev.txt -r requirements-app.txt` (fakeredis), `npm ci` in frontend/, `git fetch --unshallow`.

## Done / not done (queue of the brief)
| Item | State |
|---|---|
| 1 FJ merge, four Exit tests | done: 24 passed; later FJ heads merged in waves 0 and 1 |
| 2 RA merge | done (951aa698c), RA2 dc1aeebd8 |
| 3 batches | waves 0 and 1 done; waves 2 and final: NOT DONE (owner's order: no successor, no new tasks) |
| 4 proofs | done on the wave 1 head (above) |
| 5 Opus review of the frozen head | NOT DONE |
| 6 PC pull order and the final STATUS line | NOT DONE; facts for it: 0062 is additive (round 2 code runs on it: 52 tests), 0063 and 0064 are in the build; migration step must be written "against the live database, with the method the PC used for 0059 to 0061" (never db_run.py); PC timings for 0060+0061 were 5 minutes |

SAFE TO CLOSE (wave 1 head 8425feea on integration/weekend-r3-1129, this hand-over on docs/z3-handover-1129; left: B3, RA2 after dc1aeebd8 via B1b, feat/real-same-screens-*, waves 2 and final, review, pull order, green CI on the frozen commit)

## Defects found
- D1 (Lane RA, tests_app/test_exit_door_real_fd3.py:292, `test_n7_a_stop_stored_then_a_failed_kind_read_still_answers_success_with_the_line_unknown`): `assert calls["n"] >= 2` gets 1. FD5's N7 expected the answer to read the position kind a second time after the commit and fall back to "unknown"; RA's N7 (routes/paper.py create-trigger and cancel routes, comment "RA N7 (Opus F-2)") reads the kind once BEFORE the commit and passes it to `_triggers_out(kind=...)`, so no second read happens. It fails on RA's own branch alone (13 passed, 1 failed, run in a temporary worktree), so it is not a merge artefact. Both designs fail closed (a failed read before the commit refuses with nothing changed; the stored stop is never reported live). The owner lane decides whether the test's assertion is stale or the second read must come back; I did not edit either. Not in the pre-push gate (database tests are CI's).

## To file as deferred issues
- D1 above.
