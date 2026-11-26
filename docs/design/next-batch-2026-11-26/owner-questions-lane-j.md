# Lane J owner questions (26 Nov 2026)

## LJ-1 The fired leg stop's max-loss line: priced at the stop level or at the fill? ANSWERED

Owner 26 Nov evening (question tool, through the coordinator): "The real exit price", option 1, as built. Recorded as
ADR-330 (41) on fix/ic-live-test-1123.

Spec basis: ADR-330 (6): "If this stop fires, max loss becomes Rs X (now Rs Y)" ... "The same line is in the alert
when the stop fires." The spec does not say which price the alert's figure uses when the fill gaps past the level.

Real case (Tier A review on integration/nb-1126, the 25 Nov iron condor book of tests_app/test_leg_stop_risk.py):
stop on the short call at 140.70; the tick jumps to 180.00 and the leg exits at 180.00. Priced at the level the alert
reads "max loss becomes Rs 12,005.50"; the position actually held after the exit has max loss Rs 14,560.00 (the
Positions page shows that). Without a gap (fill = level) both are the same.

Options:
1. (Recommended, built) Price the alert's line at the recorded fill, the same message's "exited at" price: the figure
   is true for the position the user now holds and matches the Positions page.
2. Price it at the stop level: the same figure the user saw before saving, but wrong for the position after a gap.
3. Both: "max loss becomes Rs 14,560.00 (Rs 12,005.50 at your stop level; now Rs 2,860.00)".

Built: option 1 (`backend/ofo_app/paper_monitor.py` `_max_loss_line`, one argument; reversible in one line).
