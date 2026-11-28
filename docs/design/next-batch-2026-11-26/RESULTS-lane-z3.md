STATUS 17:11 IST | HEAD: product tree 631f1a03e6b7ffcdcec2a4876c23133e3ad57a80 plus this RESULTS commit on integration/weekend-r3-1129 | PRE-PUSH: 829ff65f: no recorded line (Lane Z2's file has none); first recorded pass is on 631f1a03e6b7ffcdcec2a4876c23133e3ad57a80: TOTAL PASS 1418.2s (--jobs 2) | MERGED: FJ origin/fix/r3-frontend-joins-1128 at 1ad97343 (tests only on top of round 2; the Exit product code was already in 829ff65f) | NOT YET: FJ newer head ddd65680 (next), RA fix/r3-leftovers-1128 (not on origin; fallback fix/r3-backend-5-1128 at 20:00), fix/ic-live-test-1123 (coordinator item, after this push) | PROOFS: four Exit tests exit-market-closed-adr330-60 (7), exit-closed-entry-points-r2-fa + exit-market-closed-positions-r3-fj (5 together), exit-rule-all-doors-r3-fj (12): 24 passed, 4 files; DB proofs and frontend unit on batch heads: pending | REVIEW: pending | ROUND 3 READY FOR THE PC: no (first batch only)

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
