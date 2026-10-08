# Builder brief: W-060 index spot, its health, and each expiry's parity forward

Core: on the real 2026-10-08 09:20:00-09:20:10 frames, the forward per expiry read from the chain equals the values in
work/W-060.md `proof`, and IV from that forward leaves the call and put at the same strike within 0.5 vol point,
where IV from spot does not.
Proof (step 1, before any catalogue or health change): `tests/marketdata/test_parity_forward.py` replays
tests/fixtures/kite_ws/frames-2026-10-08-092000-10s.bin.gz through the merged W-059 `KiteProvider`, computes the
forward per expiry at valuation 2026-10-08 09:20:09 IST with rate 0.065, and asserts the four forwards and effective
spots in the work item to 0.01, the strike counts (21, 20, 21, 21), and the IV gap at the ATM strike (spot vs forward).

Budget: 60 min wall-clock, 80 tool calls. Commit step 1 green before steps 2-4; at budget stop after a commit and
report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`).
Tier: B.

## Spec basis
- REQ-072 AC-1: "The platform's segment list gains NSE_INDEX and BSE_INDEX for the two index rows only (NIFTY 50, SENSEX); their
    identity is (segment, exchange token) and they are never mixed with Zerodha's NSE cash rows that share numbers (F-10)."
- REQ-072 AC-2: "The live NIFTY 50 and SENSEX values carry the same health states as option prices (REQ-049 AC-2); a stale or
    missing index value is shown as such and is never used silently in a calculation."
- REQ-072 AC-3: "IV, Greeks and Estimated Now use each expiry's put-call-parity forward (ADR-061)"
- ADR-061 (the method, the fallback below 3 strikes, the label "estimated from spot"); F-32; work/W-060.md
  "Measured robustness" (median kept; the 5%-quote-width filtered spread stored only as a quality figure).
- Copy from: none - algochanakya prices from spot; index identity follows W-056/W-057.

## What to build
1. **Parity forward (backend/ofo/marketdata/forward.py, stdlib, Decimal at the boundary):** for one expiry's chain
   snapshot plus spot and a valuation time: take the 21 strikes nearest spot; keep strikes where both CE and PE have
   bid and ask; F = median of K + e^(rT)(C_mid - P_mid); q = r - ln(F/S)/T; effective spot S e^(-qT). Return a frozen
   `ExpiryForward(expiry, forward, implied_yield, effective_spot, strikes_used, quality_spread, source)` where
   `source` is "parity" or "spot fallback" (fewer than 3 usable strikes) and `quality_spread` is max-min over the
   strikes whose two quotes are each within 5% of their mid. Stored with every chain snapshot (ADR-061).
2. **Engine use (backend/ofo/scenario/ and the IV/Greeks callers):** IV, Greeks and Estimated Now take the
   `ExpiryForward`; the engine is given S e^(-qT) for a what-if level S; delta scaled by e^(-qT), gamma by e^(-2qT);
   the result carries the label "estimated from spot" when `source` is the fallback. The payoff, CURRENT column and
   default range keep spot. Expected values from the work item and Hull's formulas, never from running the code.
3. **Index segments (AC-1, backend/ofo/instruments/):** NSE_INDEX and BSE_INDEX for NIFTY 50 (NSE exchange token
   1001) and SENSEX (BSE exchange token 1) only; identity (segment, exchange token); a test proves the NSE cash row
   with exchange token 1001 stays a different contract (F-10). Replace W-059's `INDEX_TABLE` in kite_provider.py by
   catalogue lookups through the per-broker table; INDIA VIX stays out (not in AC-1).
4. **Index health (AC-2):** the index quotes use the W-059 feed-state health; a stale or unavailable index makes
   every calculation that needs it refuse or carry the stale label - never computed silently (test with the
   inserted-gap replay).

## Standing items (run-discipline B4) and reviewer checklist
- (d) every answer state of the forward: enough strikes; fewer than 3 (fallback, labelled); spot missing or stale
  (refuse); T at or below zero (expired - refuse); a strike with ask below bid (skip, counted).
- Mutation tests first: drop the e^(-qT) delta scaling; use spot instead of the forward; silent fallback without the
  label; mix the NSE cash 1001 row with NIFTY 50. Each must turn a test red.
- Money/prices Decimal at every boundary; floats only inside the formulas.
- Kit CI stays green: tests/ imports no app packages; no wall-clock asserts.

## Rules
- Branch `build/W-060-forward` from origin/main (W-059 merged at 684ac91). Do not edit kit files or spec/. Never write
  `evidence/`. Never mark anything verified. Full domain suite once at the end (summary line captured). Commit, push.
