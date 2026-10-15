# Verifier brief: W-076 freeze limit from NSE's contract file, block at review (Tier A)

Core: parsing the real NSE contract-file sample gives NIFTY26O1923550CE (token 47185) freeze limit 3511 with file date
2026-10-15, stored per exchange with that date; through the store -> adapter -> review path a 55-lot NIFTY leg (3,575
units) is blocked and a 54-lot leg (3,510) passes; a contract with no stored limit gets ADR-081's warning.
Proof: re-run the tests yourself; the builder's report and the reviewers' PASS are claims.

Model: opus (Tier A verifier).
Budget: 30 min wall-clock, 30 tool calls. HARD: at call 27 stop and return what you have.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), then the JSON block below.

## Where
- Your own read-only copy: `git -C D:/Abhay/Ventures/OptionsForOptions2 worktree add <scratchpad>/v076 origin/build/W-076-freeze`
  (detached); remove it at the end from the main checkout (`git worktree remove` + `git worktree prune`).
- Brief + checklist: `docs/process/brief-W-076.md`; card `work/W-076.md`; ADR-081; `spec/findings.md` F-36; fixture
  `tests/fixtures/exchange/NSE_FO_contract_15102026_sample.csv` (+ README).
- AC: REQ-054 AC-4. Fingerprint (main checkout): `python tools/ac_fp.py REQ-054 AC-4 --yaml` -> currently `739ca370dc58`.

## Spec basis
- REQ-054 AC-4: "Lot size, tick size and freeze limit are stored per broker with the date the broker's list showed them."
- ADR-081: "A leg whose quantity is above the contract's freeze limit is blocked on the order review with the reason and the limit, never split."
- ADR-081: "While no freeze limit is stored for a contract, the review warns that Zerodha may reject a large order."

## Check (how could it fail?)
1. In `v076`: `python -m pytest -q -p no:cacheprovider tests/instruments tests/execution tests/errors tests/test_fixture_symbols.py tests/test_door_names_private.py`.
2. App, targeted only (never apply migrations; the shared test DB head may differ - judge the migration by its source
   and the chain test): `python D:/Abhay/Ventures/OptionsForOptions2/scripts/orchestrator/db_run.py <scratchpad>/v076 python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_freeze_store.py tests_app/test_freeze_allowlist_chain.py tests_app/test_migration_sql_parses.py`.
3. Read the real fixture row for token 47185 yourself (`MaxTradQty`, `MinLot`, `XpryDt`) and compare with the parser's
   output; confirm 3511 = 54 x 65 + 1 and that 3,510 passes, 3,575 blocks.
4. Attacks: `<` vs `<=` boundary; a symbol mapping to two catalogue entries -> warning; a stale (older) file never
   replaces a newer limit; a same-date file with a different limit refused; `freeze_limits` omitted -> TypeError, None
   -> warnings; 0013's down_revision is 0012_charge_rates and its allowlist keeps block 13 and adds 14.
5. Note honestly: the store keys per exchange with the file date - does that meet AC-4's "per broker with the date the
   broker's list showed them" given ADR-081's consequence (Zerodha publishes none, so stored per exchange)?
Never write in the main checkout; never write `evidence/`.

## Return
Evidence table, then one JSON block:
```json
[{"ac": "AC-4", "requirement": "REQ-054", "ac_fp": "<from ac_fp.py>", "result": "pass|fail",
  "commands": "...", "observed": "...", "attack": "..."}]
```
Plus defects (file:line, severity).
