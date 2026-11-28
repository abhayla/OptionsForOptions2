STATUS 23:31 IST | HEAD: the commit this file is pushed in on integration/weekend-r3-1129 (wave 1, WITHOUT B3); wave 0 a1d70422599c0db530f98b66cec2c8b886da8c66 TOTAL PASS 954.9s (--jobs 4); 829ff65f: no recorded line | WAVE 1 MERGED: RA2 fix/r3-leftovers-2-1128 dc1aeebd8 (nothing newer: hold), B2 fix/r3-backend-b2-1128 b2e8e29c3, FJ2 fix/r3-frontend-2-1128 d93fce449, F2 fix/r3-frontend-f2-1128 4e8074a07, F3 fix/r3-frontend-f3-1128 505542d80, T test/r3-tests-t-1128 5342dcb2c | LEFT OUT: B3 fix/r3-backend-b3-1128 ecf8e8f99 (coordinator's order B: its Return-door template duplicates RA2's code 589 and its entries-sentence test contradicts RA2's wording; B3 fixes on its own branch, enters wave 2), RA2 newer than dc1aeebd8 (only through B1b), feat/real-same-screens-* (held), fix/r3-frontend-f23-handoff-1128 | CHANGE: B2's migration renumbered 0063_order_attempts to 0064_order_attempts after RA2's 0063_basket_facts_spot_at; one head 0064_order_attempts; fresh database up 81 s, down to 0062 59 s, up 59 s, no hang | CONFLICTS (sides): templates.py both gates kept (589 RA2, 590 B2); AdjustPlanSheet.vue F2's; PlanEntry.vue F2's whole file (auto-merge declared levelText twice); friction-log rows of both | DISCLOSED: I removed frontend/tests/plan-card-levels-fj2-1128.test.js (3 tests, F3's hand-off FJ2-9 block superseded by F2's I-197): coordinator may reverse | PROOFS: DB proofs on the pushed head follow the push; check line in the wave line | CI on pull 881: wave 0 red (4 known), wave 1 not yet run | REVIEW: pending (after the 10:00 freeze) | ROUND 3 READY FOR THE PC: no

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

## Defects found
- D1 (Lane RA, tests_app/test_exit_door_real_fd3.py:292, `test_n7_a_stop_stored_then_a_failed_kind_read_still_answers_success_with_the_line_unknown`): `assert calls["n"] >= 2` gets 1. FD5's N7 expected the answer to read the position kind a second time after the commit and fall back to "unknown"; RA's N7 (routes/paper.py create-trigger and cancel routes, comment "RA N7 (Opus F-2)") reads the kind once BEFORE the commit and passes it to `_triggers_out(kind=...)`, so no second read happens. It fails on RA's own branch alone (13 passed, 1 failed, run in a temporary worktree), so it is not a merge artefact. Both designs fail closed (a failed read before the commit refuses with nothing changed; the stored stop is never reported live). The owner lane decides whether the test's assertion is stale or the second read must come back; I did not edit either. Not in the pre-push gate (database tests are CI's).

## To file as deferred issues
- D1 above.
