# Verifier brief: W-075 charges in max-loss / max-profit sentences and expiry values (Tier A)

Core: the real 1-lot NIFTY iron condor of 2026-10-15 (SELL 23150 CE 53.30, BUY 23350 CE 17.30, SELL 22750 PE 65.15,
BUY 22550 PE 34.00; 65 each) gets round-trip charges of Rs 214.96 and "At most ₹8,850.21 at expiry, including about
₹214.96 of charges and taxes." (max profit ₹4,149.79); with no rate set the old ADR-071 phrase stays.
Proof: re-run and hand-compute yourself; the builder's report and the reviews are claims.

Model: opus (Tier A verifier).
Budget: 30 min wall-clock, 30 tool calls. HARD: at call 27 stop and return what you have.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), then the JSON block below.

## Where
- Your own read-only copy: `git -C D:/Abhay/Ventures/OptionsForOptions2 worktree add <scratchpad>/v075 origin/build/W-075-charges-sentences`
  (detached); remove it at the end from the main checkout.
- Brief: `docs/process/brief-W-075.md`; card `work/W-075.md`; ADR-082, ADR-071, ADR-008; F-35.
- Known and accepted: ADR-082's example "about Rs 221" is an arithmetic error (2 x entry rows puts STT on the exit
  buys); the correct round trip is 214.96 and the orchestrator corrects the ADR example at merge. The sentence vs
  expiry-table difference from STT on exercise is an owner question (OQ-4), not a defect of this item.
- AC: REQ-034 AC-7. Fingerprint (main checkout): `python tools/ac_fp.py REQ-034 AC-7 --yaml` -> currently `5250eb0c6b9d`.

## Spec basis
- REQ-034 AC-7: "Outcome numbers appear in plain language first"
- ADR-082: "Every maximum-loss and maximum-profit sentence, and the expiry scenario values,
  include the round-trip charges of the strategy at its planned prices (entry and exit), and the sentence says so"

## Check (how could it fail?)
1. In `v075`, separately: `python -m pytest -q -p no:cacheprovider tests/outcome`, `tests/scenario`, `tests/charges`,
   `tests/table`, `tests/errors`, and `tests/test_door_names_private.py tests/test_no_wall_clock_asserts.py`.
2. App, targeted (never apply migrations): `python D:/Abhay/Ventures/OptionsForOptions2/scripts/orchestrator/db_run.py <scratchpad>/v075 python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_outcome_charges_wiring.py tests_app/test_outcome_catalogue.py tests_app/test_outcome_route.py tests_app/test_charge_rates_store.py tests_app/test_freeze_allowlist_chain.py tests_app/test_migration_sql_parses.py`.
3. Hand-compute the 8 orders from F-35's rates (entries + opposite exits, same prices) and the two sentences; compare
   with the code.
4. Attacks: no rate set -> old phrase + charges_unavailable; an unpriceable leg (futures / unknown index / zero price) ->
   old phrase, no "₹0.00", no crash; breakevens unchanged by charges; Estimated Now unchanged; STT on exercise only for
   a BOUGHT option in the money in an expiry cell; stamp 0.003 or SEBI 0.0001 typed as a percentage refused (caps).
Never write in the main checkout; never write `evidence/`.

## Return
Evidence table, then one JSON block:
```json
[{"ac": "AC-7", "requirement": "REQ-034", "ac_fp": "<from ac_fp.py>", "result": "pass|fail",
  "commands": "...", "observed": "...", "attack": "..."}]
```
Plus defects (file:line, severity).
