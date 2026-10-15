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
