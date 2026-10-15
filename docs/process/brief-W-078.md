# Builder brief: W-078 executable order price, product and reduce-only (Tier A)

Core: from the real 15:10 depth of NIFTY26O1923550CE, BUY 1 lot gives executable limit 4.00 and slippage Rs 3.25 vs
LTP 3.95; BUY 2 lots gives limit 4.05 and Rs 523.25 vs Rs 513.50; a BUY limit derived as 3.975 is sent as 3.95.
Proof: step 1 is `tests/engine/test_executable_price.py` loading the REAL replies
`docs/research/kite-proof-2026-10-07/rest-2026-10-15-order/quote_CE.json` and `quote_PE.json`
(`json.load(..., parse_float=Decimal)`). Write it FIRST, red.

Tier: A (decides the price sent to the broker). Model: sonnet (builder routing).
Budget: 60 min wall-clock, 64 tool calls. HARD limit: at call 60 commit, push, report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~300 words.
Copy from: none - spec/technical-design/legacy-reuse.md has no tick-rounding or depth-limit row (searched: tick, depth, slippage).

Read first: `docs/process/builder-brief.md`, `work/W-078.md`, `spec/decisions/ADR-080.md` (decision and real cases),
`spec/requirements/REQ-059.md`, `backend/ofo/execution/safety.py` (reduce-only check `EXIT_NOT_REDUCE_ONLY`
~460-530), `backend/ofo/orders/model.py` (`Order`), `backend/ofo/execution/send_guard.py` (`_BrokerRequest`), the
skill `options-math-review` checklist (`.claude/skills/options-math-review/SKILL.md`, read with the Read tool),
`CLAUDE.md`.

## Spec basis
- ADR-080: "every entry and adjustment order is NRML (carry forward), with no product choice on screen"
- ADR-080: "BUY rounds down, SELL rounds up - so the price sent is never worse than the price the
  user accepted"
- ADR-080: "a price outside the day''s circuit band blocks that leg with the reason, never a silent clamp"
- ADR-080: "when the 5 levels cannot fill
  the quantity, the review says so and offers price protection"
- REQ-059 AC-4: "Validation never silently changes the user's strategy."

## What to build
1. `round_to_tick(price, tick, side)` in the engine (`backend/ofo/engine/`), exact Decimal: BUY floor to the tick, SELL
   ceil; tick from the catalogue (`tick_size`, stored per broker row); a non-positive tick or price -> ValueError.
2. `executable_limit(depth_side, side, quantity)` - walk the 5 levels on the ask side for BUY, bid side for SELL,
   cumulative quantity until the whole quantity is covered; the limit is the worst level price needed, rounded per 1;
   returns the limit, the cost at that limit vs the cost walking the levels (report both: what a LIMIT at the worst
   level costs if fully filled at that level is NOT the walked cost - state in the result which number is the
   slippage base; ADR-080's worked case uses the walked cost: 65 @ 4.00 + 65 @ 4.05 = 523.25), and a `fillable`
   flag; when the 5 levels cannot fill the quantity, `fillable` is false and no limit is invented.
3. Slippage per leg and total, in rupees: executable (walked) cost minus planned cost at the planned price (LTP or the
   user's price), signed so that a worse price is a positive cost for BUY and for SELL (SELL: planned minus walked).
4. Circuit band: a limit below `lower_circuit_limit` or above `upper_circuit_limit` blocks the leg with a four-part
   catalogue message naming the band; never clamps.
5. Product: add a closed `Product` value (NRML; MIS only as a value read from Zerodha positions) to the order model and
   the broker request; entries and adjustments are NRML; an exit takes the product of the position it reduces; the
   reduce-only check in `safety.py` refuses an exit whose product differs from the position's (tested on Kite's
   documented position row shape - the owner's account has no positions, so mark those tests `unproven on real data
   until the 4b order` in their docstrings).

## Reviewer checklist (write first; each red when mutated)
- BUY rounding up or SELL rounding down -> red (3.975 BUY -> 3.95; 3.975 SELL -> 4.00).
- BUY walking the bid side, or SELL the ask side -> red (use quote_PE.json too).
- Worst-level vs first-level limit for 2 lots -> red (4.05 not 4.00).
- 5 levels short of the quantity -> `fillable` false, never a limit beyond level 5.
- Circuit block: a limit 0.01 above the upper band blocks; exactly at the band passes.
- Float input anywhere -> raises.
- Exit with a different product than its position -> refused; same product -> passes.
- Every guard has a killing test; list them. Apply the `options-math-review` checklist items that touch prices.

## Rules
- Targeted tests only: `python -m pytest -q -p no:cacheprovider tests/engine tests/execution tests/orders tests/strategy`.
  No database needed. Then your worktree's own `scripts/orchestrator/atool.py <worktree> W-078 --no-tests`.
- Do not touch `backend/ofo/charges/`, the freeze code (`backend/ofo/instruments/` freeze parser, the freeze review
  block), migrations, kit files, `spec/`, `views/`, `knowledge/findings/INDEX.md`. If you must edit
  `backend/ofo/execution/review.py`, keep the change minimal and say so (the freeze item edits it too).
- Never write `evidence/`. Never mark anything verified. Commit and push `build/W-078-executable-price`. No PR.
