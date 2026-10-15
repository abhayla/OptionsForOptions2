# Builder brief: W-075 charges in max-loss / max-profit sentences and expiry values (Tier A)

Core: the real 1-lot NIFTY iron condor of 2026-10-15 (SELL 23150 CE 53.30, BUY 23350 CE 17.30, SELL 22750 PE 65.15,
BUY 22550 PE 34.00; 65 units each) gets round-trip charges of about Rs 221 and the sentence
`At most â‚¹<8,635.25 + charges> at expiry, including about â‚¹<charges> of charges and taxes.`
Proof: step 1 is `tests/outcome/test_charges_in_sentences.py`: hand-compute the 8 orders (4 entries + 4 opposite
exits, same prices) from F-35's rates in the test (no calculator output pasted), and cross-check the 4 entry orders
against Kite's real rows in `docs/research/kite-proof-2026-10-07/rest-2026-10-15/charges_orders.json` (equal to 4
decimals except our stamp). Write it FIRST, red.

Tier: A (every max-loss number on screen; engine output). Model: sonnet (builder routing).
Budget: 60 min wall-clock, 64 tool calls. HARD: at call 58 stop, commit, push, report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~300 words.
Copy from: none - spec/technical-design/legacy-reuse.md has no charges row; this extends W-074 and the project's own outcome code.

Read first: `docs/process/builder-brief.md`, `work/W-075.md` (incl. its two decisions by role), `spec/decisions/ADR-082.md`,
`spec/decisions/ADR-071.md`, `spec/findings.md` F-35, `spec/business-rules/scenario-calculations.md`, the W-074 package
`backend/ofo/charges/` and store `backend/ofo_app/charge_rates_store.py`, the templates `summary_lose_at_most` /
`summary_make_at_most` (`backend/ofo/errors/explanations.py` ~935-939), `.claude/skills/options-math-review/SKILL.md`
(Read tool), `CLAUDE.md`.

## Spec basis
- ADR-082: "Every maximum-loss and maximum-profit sentence, and the expiry scenario values,
  include the round-trip charges of the strategy at its planned prices (entry and exit), and the sentence says so"
- ADR-082: "STT on exercise (bought options expiring in the money) is not in the planned-price round trip; the expiry scenario
  for a long leg that finishes in the money adds it at the scenario''s intrinsic value."
- REQ-034 AC-7: "Outcome numbers appear in plain language first"
- REQ-032 AC-1: "no component re-implements a formula"

## What to build
1. Engine: a round-trip charges function from the strategy's legs at planned prices -> `StrategyCharges` (W-074
   `charges_for_orders`), orders = entries + opposite-side exits of the same quantity at the same planned price.
2. Max loss including charges = max loss + round trip; max profit including charges = max profit - round trip
   (unlimited stays unlimited). Expiry scenario values = expiry P&L - round trip, minus `exercise_stt` for each BOUGHT
   option whose intrinsic at that level is > 0 (W-074's function does not check bought-and-in-the-money - you must).
   Estimated Now values: say in the report whether ADR-082 covers them (it names "expiry scenario values" only) - do
   not change them.
3. Templates: `summary_lose_at_most` / `summary_make_at_most` become
   `At most {amount} at expiry, including about {charges} of charges and taxes.` (catalogue text, pins updated in
   `tests/errors/template_pins.json`); ADR-071's old phrase stays only for the no-rates case (decision (b) in the card)
   with the CHARGES_UNAVAILABLE flag. Update every test that asserts the old sentence (grep
   `before charges and taxes` in tests/ and tests_app/) - expected values recomputed by hand, not pasted.
4. App: the outcome route passes the rates in force (store, DB clock) into the engine call; a draft with no session
   still gets charges (ADR-082: "with or without a Zerodha session").
5. Breakevens, risk boundaries and the 0-P&L columns are NOT changed by charges (ADR-008 locked formulas; ADR-082 names
   only max loss/profit sentences and expiry values) - a test pins that the breakeven values are unchanged.

## Reviewer checklist (write first; each red when mutated)
- Round trip = entries only (half) -> red; exits at a different price -> red.
- Charges added to max profit instead of subtracted -> red.
- STT on exercise applied to a SOLD option, or to an OTM bought option -> red.
- Breakevens moved by charges -> red.
- No rate set -> old phrase + flag, never a sentence with â‚¹0.00 charges.
- Apply the options-math-review checklist; list every guard with its killing test.

## Rules
- Targeted tests: `python -m pytest -q -p no:cacheprovider tests/outcome tests/scenario tests/errors tests/charges tests/table`;
  DB: `python D:/Abhay/Ventures/OptionsForOptions2/scripts/orchestrator/db_run.py agent:<your-agent-id> python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_outcome_catalogue.py tests_app/test_outcome_route.py`
  only. Never apply migrations to the shared ofo_test DB. Then your worktree's own atool `--no-tests`.
- No kit, `spec/`, `views/`, findings INDEX edits; never write `evidence/`. Commit, push `build/W-075-charges-sentences`. No PR.
