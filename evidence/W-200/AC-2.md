---
work_item: W-200
requirement: REQ-046
ac: AC-2
result: fail
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "e618beec6ef5"
commands: "read frontend/src/lib/adjustDrawer.js; read frontend/src/components/strategy/AdjustDrawer.vue; grep -i 'utilis|OI|IV' AdjustDrawer.vue adjustDrawer.js AdjustCompare.vue adjustCompare.js tracking.js"
---
adjustDrawer.js:22-52 (cardRows + replyRows) gives P&L, booked, unbooked, index, open legs, max profit, max loss, breakevens, net delta, gamma, theta, vega, 'Margin needed' and days to expiry. Missing from the AC: margin UTILISATION (only the amount needed) and the relevant options' IV, OI and LTP; none appears in the drawer, the compare or the layer-2 rows.

The backend reply has no IV or OI for held legs; ChainRow.oi is used only for liquidity (F-78: no live source gives OI).

Recorded by the orchestrator from the verifier's returned block.
