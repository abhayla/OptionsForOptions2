# GC-ICGUIDE: new user-facing texts for the owner's one-batch read (task 24 -> 25), 2026-11-09

Every text below is new in this run (pins added since b52ee472 in `tests/errors/template_pins.json`, all marked
"pending owner read"; none of the older pins changed). `{x}` is filled by the server. Decision-support wording only
(ADR-003). Answer per row: OK, or the wording you want.

| # | Key | Text | Where it shows |
|---|---|---|---|
| 1 | paper_adjustment_limit | "This plan allows at most {limit} adjustments, and these orders would make adjustment {number}." / impact: "No order was stored; a partial exit counts as an adjustment, the entry does not." / next: "Exit the whole strategy, or raise the plan's most adjustments, then place the orders again." | paper confirm, 3rd adjustment past the plan max (C9) |
| 2 | paper_adjustment_limit_unread | "The plan's most adjustments could not be read, so these orders cannot be checked against it." / "No order was stored; an adjustment is never saved without checking the plan's limit." / "Place the orders again in a moment." | paper confirm when the plan cannot be read |
| 3 | adjust_reduce_below_one_lot | "Dividing {leg} or its wing by {divisor} leaves less than one whole lot to close." | drawer: why "Reduce size" is not offered (C11) |
| 4 | adjust_cmp_rupees_estimated | "{amount} (estimated at the nearer expiry)" | Compare cells of a roll to the next expiry (C12) |
| 5 | adjust_cmp_near_no_iv | "Not available: {leg} has no implied volatility to value it at the nearer expiry." | Compare, two-expiry roll |
| 6 | adjust_cmp_near_no_rate | "Not available: no interest rate was read to value the later expiry's legs." | Compare, two-expiry roll |
| 7 | adjust_cmp_curve_estimated | "estimated at the nearer expiry" | Compare chart legend, dotted line |
| 8 | adjust_current_na | "not available: {reason}" | drawer layer 2 (REQ-046 AC-2) |
| 9 | adjust_current_older | "{value} (older price)" | drawer layer 2 on stale prices |
| 10 | adjust_current_leg | "{action} {strike} {kind}" | drawer layer 2, one line per held option |
| 11 | adjust_current_leg_line | "IV {iv}, OI {oi}, LTP {ltp}" | drawer layer 2 |
| 12 | adjust_current_util_no_margin | "this strategy's margin is not available" | margin utilisation reason |
| 13 | adjust_current_util_no_funds | "Zerodha's available funds were not read" | margin utilisation reason |
| 14 | adjust_current_util_no_room | "Zerodha stated no usable available funds" | margin utilisation reason |
| 15 | adjust_current_iv_absent | "no implied volatility could be worked out for this option" | drawer layer 2 |
| 16 | adjust_current_oi_absent | "no live source gave open interest for this option" | drawer layer 2 (F-78) |
| 17 | adjust_current_ltp_absent | "no live price for this option" | drawer layer 2 |
| 18 | adjust_current_loss_absent | "the current position's max loss was not worked out" | drawer layer 2 |
| 19 | adjust_condition_line_rupees | "{label}: {value} (rule {threshold})" in rupees, e.g. "Spot crosses a breakeven: −₹1,065.00 (rule ₹0.00)" | warning line for T-02 (#650) |
| 20 | adjust_condition_line_count | same shape as a whole count, e.g. "...: 2 (rule 2)" | warning line for T-18 |
| 21 | suggestion_lapsed_not_monitored | "The strategy is no longer monitored" | inbox: why an open warning closed (#652) |
| 22 | completed_figures_unavailable | "Not available: this strategy's orders could not be read right now." | Completed tab (C13) |
| 23 | (frontend label) | "the server sets the exit price when you confirm" (or "about {price}, ...") | paper confirm dialog, exit rows (C10) |

## Wording defect found in the core proof (fix proposed, task 32)

After an adjustment, a rule that is already true at the new starting point (ADR-258) still reads "Already true when
tracking started." (measured 2026-11-09, strategy 120 after A-01: T-01 0.2731 %). Proposed text: "Already true when
adjustment {n} was placed." with the same next action ("Watch it: it flags if it clears and then comes back.").
