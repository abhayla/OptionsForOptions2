STATUS 17:50 IST | HEAD: this merge commit on integration/weekend-r3-1129 (first push 4d975129, TOTAL PASS 1374.3s on that commit; 631f1a03e6 TOTAL PASS 1418.2s; 829ff65f: no recorded line) | MERGED: FJ ddd65680503f6169708389c4a8ba0a55e1b4072f (carries 1ad97343; unknownLocks.js, PaperStrategies.vue + tests), fix/ic-live-test-1123 at c4f4f0bec01d0bfdae2c5b2e909dd92f5fd96c76 (process tooling, no product code; 6 document/script conflicts taken from the fix branch) | NOT YET: RA fix/r3-leftovers-1128 (not on origin), fallback fix/r3-backend-5-1128 at 20:00 | LINK TEST: send_message to @parent refused: "non-retryable (elevated_session_untrusted_device): the session you named needs proof of a trusted device, and the server would not vouch for this session. Nothing was sent or changed. Do not retry before the owner allows it." (confirm_repository_trust not called: it limits the session to trusted devices for good, nobody asked) | PROOFS: DB proofs, frontend unit on batch heads pending | REVIEW: pending | ROUND 3 READY FOR THE PC: no

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

## Defects found
None yet.

## To file as deferred issues
None yet.

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
- Side effect for the review: the gate on this branch is now the fix branch's faster check, so TOTAL PASS lines after this commit are from the newer prepush.py.
