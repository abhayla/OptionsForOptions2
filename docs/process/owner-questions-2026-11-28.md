# Owner questions, 28 Nov 2026 (written by Lane X2; owner away: not decided, not auto-resolved)

## Q1. A paper order accepted from an adjustment opportunity: is the closed word "Acted on" or "Completed"?

**Business call:** which word the opportunity shows after the user confirms a PAPER order from it.
**Spec basis:** REQ-112 AC-2 and AC-3; ADR-330 decision (53) (owner 27 Nov afternoon, a SPEC CHANGE to REQ-112 AC-2).

The two texts that clash (verbatim, shortened only where marked):
- **REQ-112 AC-3:** "Completed" and "Partly completed" are set only from Zerodha's confirmed fills (REQ-057 AC-2), never from the user pressing Execute; a basket not placed on Kite leaves the suggestion at "Acted on" with "Not sent to Zerodha" (ADR-135).
- **ADR-330 (53):** an opportunity is marked "Acted on" only when a paper order from it is accepted. Opening the builder from the opportunity and cancelling leaves it open, and the user can act on it later.

**Real case (28 Nov, Lane TG2, cloud, worker running):** after Confirm of a paper order from an opportunity, the row closed as "Completed at <time>", not "Acted on - Paper - not sent to Zerodha". A paper order has no Zerodha fill, so by AC-3 it can never be "Completed".

**Recommendation (not applied):** "Acted on - Paper - not sent to Zerodha" for a paper order (it follows AC-3 and (53) together), so the cloud's "Completed at" is a product defect to fix, not a spec word. The PC plan row W-10 says "owner question": the PC writes the word it sees; neither word is a FAIL until the owner answers. The answer goes into the spec as a decision row the same turn it is given.

## From the PC's round 2 (PR #722 comment, 28 Nov 22:50 IST, build 829ff65f): four notes "for the owner, not faults" (recorded, not decided)

### Q2 (a). Alerts > "Exit the position" stores the alert answer before the dialog opens
**Business call:** may Cancel on the exit dialog leave the alert answered and gone from Active? **Spec basis:** ADR-330 (3) and (12) (by design today).
**Real case (28 Nov, the PC's Exit-then-Cancel hand check on Alerts):** after Cancel the alert was answered and no longer on Active, although no exit was placed.
**Recommendation (not applied):** answer the alert only when an exit order is accepted, as decision (53) does for an opportunity ("Acted on" only when a paper order is accepted); Cancel leaves it open.

### Q3 (b). The Add to Paper name box saves a draft before the dialog opens
**Business call:** is a draft created by pressing the name box acceptable, or should it be saved only on Confirm? **Spec basis:** none found yet (not searched beyond the plan's SW-6 text).
**Real case:** the PC's SW-6 check saved draft #226 "New Strategy" before the dialog opened; it was not deleted.
**Recommendation (not applied):** no draft until Confirm.

### Q4 (c). 4 of the 9 running trades have no plan
**Business call:** should a running trade with no plan read "Not being watched: the worker does not list this trade." (today, by design) or a plainer sentence? **Spec basis:** reader design in `monitoring_state.py` ("no plan, or not traded yet"), per Lane TG.
**Real case:** 4 of the PC's 9 running trades have no plan; round 1's "all nine unwatched" was partly this.
**Recommendation (not applied):** "No plan: nothing is watched for this strategy" as the main line and drop "the worker does not list this trade" for unplanned trades.

### Q5 (d). After Exit then Cancel on the builder, a staged exit stays and the first Discard does not clear it
**Business call:** is a leftover staged exit after Cancel intended (W-26 case B is already an owner decision)? **Spec basis:** ADR-330 (59).
**Real case:** one staged exit stayed after Cancel; the first Discard did not clear it; a reload did.
**Recommendation (not applied):** Cancel clears a staged exit that this dialog staged; Discard clears everything on the first press.
