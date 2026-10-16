# Live proofs, 2026-10-16 (market hours, the owner's Kite session, ofo_dev)

These are the night plan's morning step 3. Every Kite call was read-only: `/user/margins`, `/margins/basket`, `/quote`,
`/quote/ltp` and `/charges/orders`. No order was placed. The scripts read the stored session from ofo_dev and never print
the token.

| Mechanism | Result | Files |
|---|---|---|
| Kite session after the morning login | Stored and accepted (`GET /user/margins` ok, equity.net -497) | `live_session_check.py` |
| Margin gate (W-081, REQ-055) | 1 lot NIFTY26O1923550CE BUY @5.00: Kite needs Rs 263.25; available -497; refused (MARGIN_201) | `live_margin_check.py` |
| Kite basket margin rule (F-39, ADR-094) | Margin = qty x min(limit, live price): 09:06 and 09:29 single CE; 10:33 2-leg CE+PE (`option_premium` 724.75 = 65 x 11.15; 1348.75 = 65 x 20.75) | `live_ltp_vs_margin.py`, `live_basket_premium.py` |
| Executable price from depth (W-078, ADR-080) | 12/12 single-level and 14/14 multi-level cases (up to 3 levels, up to 3510 units) equal a hand walk; 2 oversized orders gave `depth_too_thin`. Tick 0.05 read from `broker_instruments`. Not exercised: off-tick level prices | `live_proof.py`, `live_depth_proof.json`, `live_proof2.py`, `live_depth_proof2.json` |
| Charges (W-074, ADR-082, F-35) | 12 orders: brokerage, STT, exchange, SEBI and GST equal Kite's `/charges/orders`; stamp on BUYs Kite 0 vs ours up to Rs 0.47 (the stamp exception F-35 already records) | `live_charges_proof.json` |
| Live feed after release+acquire (gate 4a D-1, PR 300) | main froze the spot for 59 frames (09:36, 09:52); the fix moved 55 and 40 distinct spots in 60 s | `d1_before_8765.json`, `d1_after_8767.json`, `d1_after2_8767.json` |
| Leg picker on unheld legs (gate 4a D-2, PR 302) | main: 2 of 4 legs unpriced; the fix: 4 of 4 priced in 0.67 s (23150 CE 56.80; Kite LTP 64.95 at 10:08) | `d2_before_8765.json`, `d2_after_8768.json` |

The scripts were written in the session scratchpad and copied here unchanged. They run through
`scripts/orchestrator/dev_run.py` (ofo_dev only).
