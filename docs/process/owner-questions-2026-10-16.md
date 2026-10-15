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
- **Applied tonight (reversible):** the scenario table gets a "Charges and taxes (estimate)" row between the legs and
  TOTAL, so the legs plus that row equal TOTAL in every column (the W-075 verifier found TOTAL included charges while
  the legs did not, with no explanation: at 21,500 the legs summed to −₹8,245.25 and TOTAL showed −₹8,528.60).
- **Held:** W-075 is verified but NOT merged; I merge it after this morning's 4a gate run, so the gate's screenshots
  and D8 checks run on a stable screen and you see this question first. Say "merge W-075" (or pick (b)/(c) above).
- **Also corrected tonight (no decision needed):** ADR-082's own example said "about Rs 221" round trip; that is 2 x the
  entry charges and puts STT on the exit buys. The correct round trip is Rs 214.96 (STT falls on the exits of the
  bought legs, which are sells). The example is corrected with W-075.

## OQ-5 (information, already applied - reverse if you disagree): breakeven labels for the four single-breakeven shapes ADR-089 did not name
- **What changed:** the W-082 reviewer found four real strategies with one breakeven that ADR-089's text did not cover,
  which would have shown no Lower/Upper label at all. Added to ADR-089 and scenario-calculations §4: loss on both sides
  (credit-0 iron fly, sell 23000 CE+PE @50, buy 25000 CE / 21000 PE @50) -> 23,000 shows as both Lower and Upper BE; no
  loss region at all (zero-cost bull call spread, buy 22200 CE @100 / sell 22400 CE @100) -> the old profit-side rule
  (profit above 22,200 -> Lower BE).

## OQ-6 (information, applied - reverse if you disagree): a Zerodha average price finer than paise when adopting a position
- **Spec basis:** ADR-084 "An adopted leg's entry price is Zerodha's average price for that position ... editable"; the
  spec says nothing about averages with more than 2 decimals (searched: average, decimals, paise, multi-fill).
- **Real case:** a position built in several fills shows an average like 91.525.
- **Applied (W-083, decided with the reviewer):** the row stays adoptable and shows Zerodha's exact 91.525; if the
  strategy model cannot hold more than 2 decimals, confirming that group asks you to set the entry first (e.g. 91.53),
  and no leg of the group is adopted until every row can be (no half-adopted groups). It is never rounded silently to
  the tick (the average is a cost, not an order price).

## OQ-7: "Add a held position to an existing strategy" - build it order-free now, or defer it in the spec? (REQ-061 AC-2)
- **Spec basis:** REQ-061 AC-2 "the user can add it to an existing strategy, create a new strategy, or leave it
  standalone"; ADR-084 "The user can move any position ... into an existing strategy"; ADR-002 (every order belongs to a
  strategy).
- **Found tonight:** every existing path that adds legs to a strategy (W-027 proposals, `StrategyRecord.edit`,
  `propose_execution`) PREPARES ORDERS for the added legs. Using it for a position you already hold would buy/sell it
  a second time (double exposure). So W-083 refuses "add to existing" with "not available yet"; create-new and
  standalone work and are verified (AC-1, AC-4 pass; AC-2 fails on this one choice).
- **Options:** (a) build an order-free "adopt into existing strategy" that records the held legs as a new strategy
  version with no order (a new small item, Tier A); (b) defer it - write into REQ-061 that adding to an existing
  strategy comes later, and close AC-2 on the other two choices.
- **Recommendation: (a)** - it is the only choice that lets a calendar's far leg join the near one you already track,
  and the order-free version path is needed anyway for reconciliation fixes; until it lands, the refusal is honest and
  safe.

## OQ-8 (information, applied - reverse if you disagree): expired standalone records and expired contracts still at Zerodha (#279)
- **Spec basis:** REQ-060 owner decision (Q269, ADR-083): an expired leg "is closed in the platform at the settlement
  price ... reconciliation expects it gone"; REQ-060 AC-7: standalone quantity is part of the compare. Nothing said
  what happens to a standalone record when its contract expires (searched: standalone, expired, expiry, retire).
- **Real case:** none on a live account yet (no standalone recorded). In a 4,000-case fuzz, 309 expired standalones
  would have shown "awaiting" forever and 878 expired contracts were labelled "missing" or "side" wrongly.
- **Applied (ADR-083's "expected gone" applied to standalones):** a one-time non-blocking note, then the standalone
  record is retired; an expired contract Zerodha still shows with a different quantity is labelled as that. Blocking
  is unchanged (0 differences in blocked strategies over the fuzz). Written into REQ-060 as a clarification.
- **Alternative if you disagree:** keep the standalone record and keep showing the note until you clear it.

