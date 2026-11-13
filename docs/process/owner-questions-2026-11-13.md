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

## Q4. The "needed to recover the current loss" line shows on every trade from the moment it is placed. Keep it so?

Parked 13 Nov 23:2x IST (after 22:00: no question box). Nothing waits on it.
Business call: it changes a line the user reads on every fresh trade.
Spec basis: ADR-306 (4): the line shows X = the current loss = minus the Total P&L after charges. ADR-302: the line
appears when Profit left is larger than Max profit. Neither says anything about a loss that is only the charges.
Real case: an iron condor just placed has Total P&L after charges -241.43 (charges paid plus the estimated cost to
close, no price move). Max profit 2,764.83, Profit left 3,006.26, and the line reads "includes Rs 241.43 needed to
recover the current loss". True, and it adds up, but it appears before the market has moved at all.
Why a user reads the line: to understand why Profit left is bigger than Max profit.
Recommendation: keep it as built. It is the truth, and hiding it below some size would bring back a Profit left that
looks larger than Max profit with no explanation. If the wording reads oddly on a fresh trade, change the words for
that case only ("includes Rs 241.43 of charges to earn back"), not the rule.
Options: (a) keep as built (recommended); (b) different words when the loss is only charges; (c) hide the line below
a threshold (not recommended: an unexplained gap returns).

## Q7. The 12 finished builder folders cannot be removed until the branch is pushed. Leave them, or allow another way?

Parked 14 Nov 02:5x IST. Nothing waits on it; it costs disk space only (each folder links to the main checkout's
installed packages, so the space is small).
Business call: none; this is a process rule of yours meeting a delivery instruction of yours, so it is yours to weigh.
Spec basis: none: the spec says nothing about work folders. Your standing rules: (1) a work folder is removed in the
session its use ends, only with the removal tool, never by a plain delete; (2) 13 Nov: one branch, ONE push at the very
end. The tool refuses to remove a folder whose commits are not on origin (exit 3; `-Discard` needs a sha on
origin/main: exit 7). All 12 folders are clean and fully contained in `fix/gc-icfix` (checked one by one).
Recommendation: (a) leave them until the single push, then remove all 12 with the tool. It keeps both rules intact and
loses nothing. Options: (b) push the integration branch to origin now as a backup-only branch (no pull request, no
CI): then the tool can remove them, and the work is also safe off this PC; it bends "nothing leaves this PC before the
push"; (c) authorise removal outside the tool: not recommended, the tool exists because plain deletes twice wiped the
main checkout through its links.

## Q5. Profit left and Loss left: answered

ANSWERED 13 Nov 2026 (question tool): Make it add up (Recommended) -> ADR-306 (Profit left = Max profit - Total;
Loss left = Max loss - Total; all after charges). This replaced the profit-left part of ADR-301.

## Q6. Plan box against the rule set: answered

ANSWERED 13 Nov 2026 (chat): the plan box wins; an empty Target means no target alert -> ADR-305. Sentence for an
emptied Target approved ("Target: no target is set for this trade").

## Notes decided by the run (information, not questions)

- Target rule and the adjustment count "3 of 2": see the run log.
