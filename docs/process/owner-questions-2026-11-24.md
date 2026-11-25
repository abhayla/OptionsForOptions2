# Owner questions, 24 Nov 2026 (GC-ICLIVE Part B, cloud, owner away)

Written by the unattended Part B and Part C runs. Each question names the two texts, the real case and a recommendation.
Nothing here was decided by the run.

## Q1 (D-17): which prices does "Time value" use in the builder summary?

**Answered by the owner 25 Nov 2026: time value at live prices, labelled (ADR-322 point 2).**

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

## Q2 (D-25): may "Take profit" be offered when the trade is a loss after charges?

Business call: two owner texts give different answers; the Part C run stopped D-25 here (it kept the built change,
which adds figures and removes nothing).

- **ADR-238 (6):** A-24 and A-25 are "refused, with its reason, when the whole trade (booked plus open legs at the
  planned exit prices) is not in profit; a user is never shown "Take profit" beside a loss."
- **ADR-294 (4) and contract GC-ICLIVE-C, D-25 line (owner approved 24 Nov):** the "is the trade in profit" test is
  BEFORE charges, and "their offer screen always shows the after-charges result beside the before-charges one".
  ADR-294 (3) accepts that a profit rule can fire "on a trade that is a loss once closing costs are paid".
- **Real case (23 Nov):** strategy 162 showed P&L -223 (after charges, the headline basis of ADR-263) and offered
  Take profit with the same figures as Exit (debit 8,468). If its before-charges figure was above zero, both texts
  cannot hold at once: ADR-294 offers it (with "-223 after charges" beside it), ADR-238 (6) forbids it.
- **What the run built (kept):** the offer now names both figures: "Whole trade closed at the planned prices:
  {before} before charges (the figure the profit test used), {after} after charges." No path offers or accepts Take
  profit at a before-charges loss (independent review, 25 Nov).
- **Recommendation:** refuse A-24/A-25 also when the after-charges result is a loss, with the reason "Not in profit
  after charges: {after}"; Exit (A-31) stays offered. The name "Take profit" promises a profit, and the headline a
  trader reads is after charges. ADR-294 (4) was an assistant call under the 13 Nov standing rule, so changing it
  touches no direct owner answer. Not recommended: keep the before-charges test only (the 23 Nov complaint stays).

Spec basis: ADR-238 (6); ADR-294 (3), (4); ADR-263; contract GC-ICLIVE-C (D-25).
