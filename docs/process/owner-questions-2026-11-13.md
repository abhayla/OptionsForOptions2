# Owner questions, GC-ICFIX, 13 Nov 2026

Parked here so the run does not stop. Each has a recommendation. Until answered, the tasks named under "Waits"
do not start; everything else continues.

## Q1. What goes into "Profit left" and "Loss left": only the cost to close, or also charges already paid?

Business call: it changes a money figure the user reads on the trade page.
Spec basis: REQ-109 AC-9 says "'Profit left' and 'Loss left' (the open legs' expiry P&L range from their LTP)", with no
charges. ADR-263 says "Max profit, max loss, profit left, loss left ... are shown AFTER charges (charges already paid
plus the estimated charges to close what is open)". The two texts clash.
Real case: strategy 138 showed Profit left 4,644.25 (before charges) beside Max Profit 4,374.40 (after charges).
Recommendation: follow ADR-263 as written (paid charges plus the estimated cost to close), so "left" and "max" are on
one basis, and correct REQ-109 AC-9 to say so.
Waits: u124.
ANSWERED 13 Nov 2026 (question tool): After all charges (Recommended) -> ADR-301.

## Q2. "Profit left is never above max profit" is not true while a trade is losing. Keep the cap, or drop it?

Business call: it changes what the user reads as the money still to be made.
Spec basis: REQ-109 AC-9 measures Profit left from now; Max Profit is the whole trade. The plan's task u124 says "never
above max profit". Spec silent on the cap (searched: REQ-109, ADR-263, ADR-259, "profit left").
Real case: strategy 138 with an unbooked loss of 500 gives Profit left 5,173.50 against a credit of 4,673.50, both
before charges. The larger number is correct arithmetic: the trade must first win back the 500.
Recommendation: drop the cap. Keep Profit left measured from now, on the same after-charges basis as Max Profit, and
add one line when it is larger: "includes Rs X needed to recover the current loss". A cap would hide a true number.
Waits: u124.
ANSWERED 13 Nov 2026 (question tool): Drop the cap (Recommended) -> ADR-302.

## Q3. How do charges split between booked and unbooked P&L?

Business call: it changes two money figures on the trade page.
Spec basis: ADR-263 says "total / booked / unbooked P&L ... AFTER charges". No text says which charges go where
(searched: ADR-263, REQ-109, ADR-259).
Real case: strategy 141 closed: booked -32.50, charges paid 403.45, after charges -435.95.
Recommendation: booked minus all charges already paid; unbooked minus the estimated cost to close what is open. Then
booked + unbooked = total after charges, and a closed trade shows its full cost in booked.
Waits: the booked / unbooked lines of u123 (the total itself does not wait).
ANSWERED 13 Nov 2026 (question tool): Paid in booked, close cost in unbooked (Recommended) -> ADR-303.

## Notes decided by the run (information, not questions)

- Target rule and the adjustment count "3 of 2": see the run log.
