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

**Answered by the owner 25 Nov 2026: refuse Take profit at an after-charges loss (ADR-326 (1)).**

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

## Q3 (D-40): which figures does the paper page header add up when some strategies sit on expired contracts?

**Answered by the owner 25 Nov 2026: keep as built (ADR-326 (2)).**

Business call: the spec does not say; the Part D run took option A (ADR-324, PENDING OWNER READ) and kept the old
scenario strategies.

- **Option A (built):** every header figure (Total, Booked, Unbooked, Decay, Charges, after-charges figures) is the sum
  over the strategies that can be priced. A strategy with an open leg on an expired contract is named as expired on its
  own row and left out; the header adds "N strategies left out: their contracts have expired." Total = Booked +
  Unbooked always holds.
- **Option B:** only Total, Unbooked and Decay leave the expired strategies out; Booked and Charges keep adding every
  strategy (the 23 Nov screen: Booked +10,947.43, Charges 6,140.07 over all of them). Total would then not equal
  Booked + Unbooked, and the header would mix two sets.
- **Real case (23 Nov):** PATH-60 and PATH-61 (old scenario strategies) hold open legs on expired contracts, so Total,
  Unbooked and Decay were dashes with "This contract has expired", while Booked and Charges summed every strategy.
- **Recommendation:** A. One set under every figure, no partial sum (REQ-109 AC-5), and the line says how many were left
  out. B keeps Booked and Charges larger but cannot be added up by the trader. Deleting the old strategies stays the
  owner's call (not done).

Spec basis: REQ-109 AC-5; ADR-311; ADR-210; ADR-324.

## Q4 (D-38): what does a page say when a read takes too long, and does it keep what the trader typed?

**Answered by the owner 25 Nov 2026: keep as built (ADR-326 (3)).**

Business call: the contract says "a page that times out says so and keeps the user's input"; the words and the
failed-pick behaviour are the run's choice (ADR-324 point 4, PENDING OWNER READ).

- **Built:** a read that hits the browser's 10 s limit says it took too long ("The plan took too long to load. Nothing
  was changed.", "The settings took too long to load, so no value is shown.", and on Create Strategy step 4 "The server
  took too long to answer." with "Your choices on this page are kept."). A failed playbook pick, for any reason, keeps
  the plan sheet and the typed fields and shows the could-not-load line inline.
- **Not built:** replacing the sheet with the could-not-load state on a failed pick (the 23 Nov behaviour), which
  throws away the typed target and stop.
- **Real case (23 Nov):** settings page 10 s then "could not be read" (the second try worked); plan dialog
  "Loading the plan..." 5 to 12 s on every paper add.
- **Recommendation:** keep as built; change only the words if wanted.

Spec basis: contract GC-ICLIVE-D (D-38 line); ADR-324 point 4; ADR-210 (reason sentences).

## Q5 (D-57): may the "Last updated" disconnect sentence use 24-hour time? (CLASH, not decided)

**Answered by the owner 25 Nov 2026: 24-hour IST everywhere, the disconnect sentence included (ADR-326 (4)).**

Business call: two owner texts give different answers; the run did not change the two sentences and marked D-57
`Needs owner decision`. Everything else of D-57 is built (one date formatter, "23 Nov 2026", 24-hour IST times).

- **ADR-015 Q182** (and REQ-049 AC-5 quoting it): on disconnect: *"Live market data disconnected. Last updated:
  10:42:17 AM. ..."*: a 12-hour clock with AM/PM.
- **ADR-320 (owner 24 Nov), D-57:** "dates read '23 Nov 2026' and 24-hour IST times everywhere; one formatter."
- **Real case (23 Nov):** the adjustments page showed '11/11/2026, 12:33:17 AM' beside '23 Nov 2026' elsewhere.
  The disconnect sentence would still read "10:42:17 AM" while every other time reads "15:45:00 IST".
- **Recommendation:** 24-hour everywhere, ADR-015 Q182 amended to "Last updated: 10:42:17 IST". One rule, no AM/PM
  on any screen. The two sites are named exceptions in the backend scan until you answer.

Spec basis: ADR-015 Q182; REQ-049 AC-5; ADR-320 (D-57); ADR-325 point 17.

## Q6 (D-67): how many minutes after entry should an adjustment pop-up stay quiet for a rule already true at entry?

**Answered by the owner 25 Nov 2026: quiet for 5 minutes after entry when the rule was already true (ADR-326 (5)).**

Business call: the owner direction says the pop-up "is not raised in the first minutes after entry for a rule
already true at entry"; the spec gives no number, so the run invented none (ADR-325 point 5).

- **Built:** pop-ups sit in the sticky header block and no longer float over page buttons. The rule keeps firing
  from entry.
- **Real case (23 Nov):** C10 166 gamma 2.95 % against the 2 % rule and C11 167 tested delta 0.3809 against 0.35, both
  raised within 1 to 3 minutes of opening.
- **Options:** (A) a quiet period of N minutes after entry for a rule already true at entry (you give N); (B) no
  quiet period, only the placement fix (as built).
- **Recommendation:** A with N = 5, matching the existing 5-minute alert cool-down of REQ-170, so a trade opened into
  an already-true rule is not told at once what the trader just accepted.

Spec basis: ADR-320 (D-67); REQ-170 (5 min cool-down); ADR-246 (quiet until 09:20); ADR-325 point 5.

## Q7 (D-68): what does "Today" add up?

**Answered by the owner 25 Nov 2026: keep as built (ADR-326 (6)).**

Business call: the decision row is the run's choice (ADR-325 point 2, PENDING OWNER READ).

- **Built:** total after charges of the real trades opened or closed on the current trading day (the India date of the
  newest snapshot), whole trade; scenario strategies left out; a trade opened earlier and only partly exited today is
  left out.
- **Option not chosen:** only what was booked today (the part exited today plus today's move of open legs).
- **Real case:** 25 Nov test trades (N-6): the tester wanted one figure for the day's test trades.
- **Recommendation:** keep as built for the test-day use; ask again when real trading starts.

Spec basis: REQ-109 AC-5; ADR-320 (D-68); ADR-325 point 2.

## Q8 (D-47): should the lots box show on every strike row?

**Answered by the owner 25 Nov 2026: keep as built (ADR-326 (7)).**

Business call: the run kept the lots box behind the first click (ADR-325 point 4).

- **Built:** Buy and Sell always drawn; the footer adds "N already in the draft".
- **Not built:** the lots box on every row (doubles the row height of the picker).
- **Real case (23 Nov):** draft X with 4 legs: "0 legs selected", Buy/Sell only on hover, lots only after a click.
- **Recommendation:** keep as built.

Spec basis: ADR-320; ADR-325 point 4.
