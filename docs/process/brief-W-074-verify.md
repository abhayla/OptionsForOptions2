# Verifier brief: W-074 charges rate table and calculator (Tier A)

Core: the rate table applied to the 8 real orders in Kite's 2026-10-15 `/charges/orders` replies reproduces every
component Kite returned to 4 decimals (stamp: our 0.003% vs Kite's 0, stated); rates are dated, append-only, exact.
Proof: re-run the tests and hand-compute yourself; the builder's report and the reviewer's PASS are claims.

Model: opus (Tier A verifier).
Budget: 30 min wall-clock, 30 tool calls (batch commands). HARD: at call 27 stop and return what you have.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), then the JSON block below.

## Where
- Your own read-only copy in the scratchpad: `git -C D:/Abhay/Ventures/OptionsForOptions2 worktree add <scratchpad>/v074 origin/build/W-074-charges`
  (detached; remove it at the end from the main checkout with `git worktree remove` + `git worktree prune`).
- Brief + checklist: `docs/process/brief-W-074.md`; card `work/W-074.md`; ADR-082; F-35 (incl. the 2026-10-16 addendum).
- AC: REQ-032 AC-6. Fingerprint (main checkout): `python tools/ac_fp.py REQ-032 AC-6 --yaml` -> currently `080da64fa2a1`.

## Spec basis
- REQ-032 AC-6: "The engine exposes margin-planning and charges interfaces (IC §5)."
- ADR-082: "The rates are admin settings with the date they were read; every amount is exact Decimal; STT and stamp duty are not
  rounded at order level"

## Check (how could it fail?)
1. In `v074`: `python -m pytest -q -p no:cacheprovider tests/charges`.
2. Hand-compute two real rows yourself from F-35's rates (one SELL, one BUY, e.g. SELL NIFTY26O1923150CE 53.3 x 65 and
   BUY NIFTY26O1922550PE 34 x 65) and compare with Kite's reply files and with the calculator's output.
3. App, targeted only: `python D:/Abhay/Ventures/OptionsForOptions2/scripts/orchestrator/db_run.py <scratchpad>/v074 python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_charge_rates_store.py tests_app/test_migration_sql_parses.py`
   (never the full app suite; the shared test DB is at a different head because of parallel builders - if a migration
   test fails only on the DB's current revision, say so and judge the migration from its source).
4. Attacks: a rate typed as a percentage (stt 0.15) refused in code and by the DB CHECK; a float price refused; a
   same-date second set and a back-dated set refused; a future-dated set not in force; a mixed-date answer impossible.
Never write in the main checkout; never write `evidence/`.

## Return
Evidence table, then one JSON block:
```json
[{"ac": "AC-6", "requirement": "REQ-032", "ac_fp": "<from ac_fp.py>", "result": "pass|fail",
  "commands": "...", "observed": "...", "attack": "..."}]
```
Plus defects (file:line, severity).
