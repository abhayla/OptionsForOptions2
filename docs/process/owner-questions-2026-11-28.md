# Owner questions, 28 Nov 2026 (written by Lane X2; owner away: not decided, not auto-resolved)

## Q1. A paper order accepted from an adjustment opportunity: is the closed word "Acted on" or "Completed"?

**Business call:** which word the opportunity shows after the user confirms a PAPER order from it.
**Spec basis:** REQ-112 AC-2 and AC-3; ADR-330 decision (53) (owner 27 Nov afternoon, a SPEC CHANGE to REQ-112 AC-2).

The two texts that clash (verbatim, shortened only where marked):
- **REQ-112 AC-3:** "Completed" and "Partly completed" are set only from Zerodha's confirmed fills (REQ-057 AC-2), never from the user pressing Execute; a basket not placed on Kite leaves the suggestion at "Acted on" with "Not sent to Zerodha" (ADR-135).
- **ADR-330 (53):** an opportunity is marked "Acted on" only when a paper order from it is accepted. Opening the builder from the opportunity and cancelling leaves it open, and the user can act on it later.

**Real case (28 Nov, Lane TG2, cloud, worker running):** after Confirm of a paper order from an opportunity, the row closed as "Completed at <time>", not "Acted on - Paper - not sent to Zerodha". A paper order has no Zerodha fill, so by AC-3 it can never be "Completed".

**Recommendation (not applied):** "Acted on - Paper - not sent to Zerodha" for a paper order (it follows AC-3 and (53) together), so the cloud's "Completed at" is a product defect to fix, not a spec word. The PC plan row W-10 says "owner question": the PC writes the word it sees; neither word is a FAIL until the owner answers. The answer goes into the spec as a decision row the same turn it is given.
