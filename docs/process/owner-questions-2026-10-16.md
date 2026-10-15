# Owner questions parked overnight, 2026-10-16

Parked under run-discipline A2 while the owner sleeps; each has a recommendation. None blocks tonight's build.

## OQ-1: How does price protection split a strategy-level tolerance into per-leg limits? (ADR-080 item 3)
- **Spec basis:** ADR-080 (3): "price protection splits the user's strategy-level tolerance into per-leg limits" - the
  split rule is not stated (searched: price protection, tolerance, per-leg, split). REQ-056 AC-7 (Q28) is the
  requirement; issue #45 item 2 tracks the unchecked price.
- **Real case:** BUY 2 lots NIFTY26O1923550CE (planned 3.95, depth walk Rs 523.25 vs Rs 513.50 planned, slippage Rs 9.75)
  in a 4-leg strategy with a user tolerance of, say, Rs 50 in total.
- **Options:** (a) pro rata to each leg's planned value (premium x quantity); (b) equal rupees per leg; (c) the same
  number of ticks per leg.
- **Recommendation: (a) pro rata to planned value** - a leg worth 80% of the premium gets 80% of the tolerance, so
  cheap far-OTM legs are not given an absurd per-tick allowance; each leg's limit is then rounded toward the user per
  ADR-080 (2).
- **Why parked:** it changes the price a user's order is sent at (class 3); not decided by role.

## OQ-2: Does ADR-081's "never split" also cover Complete / Retry / exit orders, which REQ-058 slices today? (#255)
- **Spec basis:** ADR-081 "blocked on the order review with the reason and the limit, never split"; REQ-058 (Verified,
  W-028 "Complete/Retry split into lot-aligned freeze slices"); ADR-054/REQ-073 (one basket order per leg, placed by
  the user).
- **Real case:** 55 lots NIFTY = 3,575 units vs freeze 3511 (F-36): W-076 blocks it, but the review still lists slices
  1,755 / 1,755 / 65 from the old 1,755 placeholder.
- **Recommendation:** entry and adjustment baskets never split (ADR-081 as written); Complete / Retry / exit follow the
  same rule now that the user places one basket order per leg (ADR-054), and the 1,755 placeholder (#43) is replaced
  by the stored limit. REQ-058's slicing ACs are re-worded accordingly.
- **Why parked:** it changes a Verified requirement (class 3).

## OQ-3 (information, already applied - reverse if you disagree): "Checked at" for not connected = the answer time
- **What changed:** ADR-088 first said not connected shows "the time of the last connection attempt". That was my
  wording in the question's option text, not part of the one-rule choice you made. The server keeps no record of
  connection attempts, so the W-077 verifier failed AC-3 on the mismatch. Under your overnight instruction I clarified
  ADR-088 to the answer time (what the one rule says) and recorded the provenance in the ADR.
- **Real case:** a draft opened at 09:20:05 IST with no Kite session shows `Checked at 16 Oct 2026, 09:20:05 IST`.
- **If you want the attempt time instead:** a small item - the live-market provider records each connect attempt and
  the not-connected answer returns it.

## OQ-4: Should the max-loss sentence include STT on exercise when a bought option is held into expiry in the money?
- **Spec basis:** ADR-082 (2): the sentences use "the round-trip charges of the strategy at its planned prices (entry
  and exit)", and "STT on exercise ... is not in the planned-price round trip; the expiry scenario for a long leg that
  finishes in the money adds it at the scenario's intrinsic value."
- **Real case (W-075, 1-lot NIFTY condor of 15 Oct):** sentence "At most ₹8,850.21 at expiry, including about ₹214.96 of
  charges and taxes" (squared off at planned prices). The expiry table, which adds STT on exercise for the long 23350
  CE left in the money, shows a larger loss far out - about ₹650 more at NIFTY 30,000 (0.15% of the long call's
  intrinsic). So the table can show more than the "at most" sentence. The W-075 reviewer adds: it is every cell past a
  bought strike, not only far out (₹0.0975 per point for 65 units), and the 0-P&L (breakeven) columns now show about
  −₹215 under a breakeven label, because the expiry values subtract the round trip while the breakeven levels do not
  move (ADR-008 formulas locked).
- **Options:** (a) keep as built and add one line under the sentence: "Holding a bought option to expiry in the money
  adds STT on its value; squaring off before expiry avoids it." (b) make "at most" the worst table value including
  exercise STT (it then grows with the level, so it is no longer a fixed number for spreads); (c) leave as is.
- **Recommendation: (a)** - the sentence stays a fixed, honest number for the normal squared-off case, and the trap is
  named in plain words (decision-support wording, ADR-003); the table already shows the held-to-expiry numbers.
- **Also corrected tonight (no decision needed):** ADR-082's own example said "about Rs 221" round trip; that is 2 x the
  entry charges and puts STT on the exit buys. The correct round trip is Rs 214.96 (STT falls on the exits of the
  bought legs, which are sells). The example is corrected with W-075.
