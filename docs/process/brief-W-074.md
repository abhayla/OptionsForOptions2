# Builder brief: W-074 charges rate table and calculator (Tier A)

Core: the rate table, applied to the real orders in Kite's 2026-10-15 `/charges/orders` replies, reproduces every
component Kite returned to 4 decimals (stamp duty excepted, see rule 5).
Proof: step 1 is `tests/charges/test_rates_reproduce_kite.py` on the REAL replies: 8 rows across
`docs/research/kite-proof-2026-10-07/rest-2026-10-15/charges_orders.json`, `rest-2026-10-15-order/charges_CE.json`
and `charges_PE.json`. Write it FIRST, red, then build until it is green.

Tier: A (charges enter every max-loss/max-profit number next, W-075; money). Model: opus.
Budget: 60 min wall-clock, 70 tool calls. HARD limit: at call 65 commit, push, report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~300 words.
Copy from: none - spec/technical-design/legacy-reuse.md has no charges row (searched: charges, brokerage); algochanakya has no charges model in the map.

Read first: `docs/process/builder-brief.md` (common rules, quality bar), `work/W-074.md`, `spec/decisions/ADR-082.md`,
`spec/findings.md` F-35 (line ~510), `spec/requirements/REQ-032.md`, `CLAUDE.md`.

## Spec basis
- REQ-032 AC-6: "The engine exposes margin-planning and charges interfaces (IC §5)."
- REQ-032 AC-4: "All money is computed in exact decimal or integer paise, never binary floating point"
- ADR-082: "The rates are admin settings with the date they were read; every amount is exact Decimal; STT and stamp duty are not
  rounded at order level"
- spec/findings.md F-35 (read it; its rate text, reproduced here without quote marks because the brief checker cites
  only REQ/ADR/Q ids): brokerage Flat Rs. 20 per executed order; STT 0.15% on sell side (on premium) and 0.15% of the
  intrinsic value on options that are bought and exercised; NSE transaction 0.03553% (on premium), BSE 0.0325% (on
  premium); GST 18% on (brokerage + SEBI charges + transaction charges); SEBI Rs 10 / crore; stamp 0.003% or Rs 300 /
  crore on buy side.

## What to build
1. `backend/ofo/charges/` (standard library only, domain layer): a `ChargeRates` value (each rate as Decimal, the
   exchange-specific transaction rate keyed by exchange segment `NSE_FO` / `BSE_FO`, the date the rates were read,
   the source URL) and a calculator: input = a list of orders (segment, side BUY/SELL, quantity, price as Decimal);
   output per order = brokerage, STT, exchange transaction, SEBI, stamp, GST, total, plus a strategy total. A
   separate function for STT on exercise (bought option finishing in the money: 0.15% of intrinsic value x quantity),
   used later by the expiry scenario (W-075).
2. Rates are exact Decimals from strings. NSE transaction = 0.03553% as ONE rate (Kite reports it as one
   `exchange_turnover_charge`; the calculator's 0.03503% + 0.0005% IPFT split is shown only in the rate's note).
3. Storage (app layer): Alembic `0012_charge_rates` (down `0011_strategy_planned_entry`) - a table of dated rate sets
   (one row per component per read date, NUMERIC, never float; the newest date in force wins; history kept,
   append-only). Seed the 2026-10-15 rates from F-35 in the migration. A store function returns the rates in force at
   a given date (DB clock, ADR-023) and an admin write function adds a new dated set (no UI, no route tonight). Run
   `python scripts/alembic_migration_guard.py`.
4. Fail closed: unknown segment, negative/zero quantity, negative price, a date before the first rate set -> ValueError
   (domain) / the catalogue error (app). No default rate anywhere.
5. Stamp duty: compute 0.003% of the BUY premium, unrounded (ADR-082). Kite's order-level reply shows stamp 0 on all 4
   real BUY rows (e.g. BUY 22550 PE 34.00 x 65, premium 2,210.00: rate gives 0.0663, Kite says 0). The proof test
   asserts our stamp equals the rate value AND records the per-row difference from Kite's 0 explicitly (a named
   constant / assertion message `Kite order-level reply carries stamp 0; contract-note rounding unmeasured until the
   4b order, F-35`). Every other component must equal Kite's to 4 decimals. Parse the fixtures with
   `json.load(..., parse_float=Decimal)` (Kite's numbers carry float noise such as 0.0034644999999999997).

## Reviewer checklist (write these tests first; each must turn red when its guard/rate is mutated)
- Each rate changed by one digit -> the proof test red (brokerage 20->21, STT 0.15%->0.16%, NSE rate, SEBI, GST 18->19).
- STT applied to a BUY, or stamp applied to a SELL -> red.
- GST base missing SEBI or transaction charge -> red.
- A float anywhere in money: a test feeding `price=3.95` as float must raise.
- BSE segment uses 0.0325% (hand-computed expected value in the test, e.g. 1 lot SENSEX option at a stated premium).
- Store: the newest rate set in force at a date wins; a set dated in the future is not in force; no rate set -> error.
- Every guard has a test that dies without it; list them in the report.

## Rules
- Targeted tests only: `python -m pytest -q -p no:cacheprovider tests/charges`; app:
  `python scripts/orchestrator/db_run.py . python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_charge_rates_store.py`
  (tunnel on 127.0.0.1:5432; if it is down, say so and leave the DB test to CI). Then
  `python <your-worktree>/scripts/orchestrator/atool.py <worktree> W-074 --no-tests`.
- No change to engine formulas, scenario values or any sentence (that is W-075). No kit or `spec/` edit. Never write
  `evidence/`. Never mark anything verified. Do not touch `views/` or `knowledge/findings/INDEX.md`.
- Commit and push `build/W-074-charges`. Do not open a PR.
