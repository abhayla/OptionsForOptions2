# Owner questions, 24 Nov 2026 (GC-ICLIVE Part B, cloud, owner away)

Written by the unattended Part B run. Each question names the two texts, the real case and a recommendation.
Nothing here was decided by the run.

## Q1 (D-17): which prices does "Time value" use in the builder summary?

Business call: two owner requirements give different answers; the run stopped D-17 and built nothing for it.

- **REQ-081 AC-3:** "The summary shows the strategy's intrinsic value (each option leg's value if it expired at the
  current spot) and time value (current premium minus intrinsic) ... Example: a bought NIFTY 22,900 CE at LTP 150.00".
  Time value is a LIVE figure.
- **Contract GC-ICLIVE-B (owner approved 24 Nov), "Decisions already taken":** "one basis per number, labelled on
  every screen that shows it (... time value: the same prices as the credit beside it ...)". The credit ("Get") uses
  the entry prices (plan or paper fills), so time value would use entry prices.
- **Real case (23 Nov):** draft X showed "Get 3,393" at plan prices beside "Time value -3,439" at live prices, so time
  value moved every second while the credit stayed frozen. C1 0-day condor: time value -2,295 to -2,412 with
  intrinsic 0.
- **What the run found when it tried the contract reading:** entry price minus intrinsic at TODAY's spot mixes two
  moments and gives impossible signs. Example from the test: a SOLD 25300 PE filled at 23.70, spot 25,250, read as
  time value +1,709.50, a "premium paid" sign for a sold leg.
- **Recommendation:** keep AC-3 (time value at live prices) and label it "at live prices, as of HH:MM:SS"; show the
  credit beside it with its own basis ("At plan prices" / "At paper fill prices", built under D-15). That gives one
  basis per number, each labelled, without the impossible sign. Not recommended: time value at entry prices (needs
  the spot at entry, which is not stored).

Spec basis: REQ-081 AC-3; contract GC-ICLIVE-B; ADR-008.
