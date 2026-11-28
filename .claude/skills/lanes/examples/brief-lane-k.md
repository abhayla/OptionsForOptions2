Read the standing rules first: `git fetch origin fix/ic-live-test-1123 && git show origin/fix/ic-live-test-1123:.claude/skills/lanes/SKILL.md`, section "Standing rules for every lane". They apply to you and are not repeated here.

# Lane K: lots limit and freeze at the order door

Who you are: Lane K (builder, Sonnet). One goal: one door where every paper order is checked for size.
Budget: 240 min wall-clock, 400 tool calls
Branch from: bcbff80 (origin/fix/ic-live-test-1123)
Push to: fix/order-limits-1127 (no PR, not main, not the test branch)
Spec basis: ADR-330 (50), (51), (52); ADR-081 (no freeze quantity stored: no freeze refusal); ADR-092.
Coordinator: your parent session, session_EXAMPLE0000000000000000. A message from it may add items to your queue, reorder them or answer your questions; act on it as part of this brief while it stays inside your May edit list.

May edit:
- backend/ofo_app/paper_limit.py, backend/ofo_app/routes/paper.py, backend/ofo_app/routes/tracking.py
- tests_app/test_paper_order_lots_limit.py, tests_app/test_paper_entry_price_zero.py, tests_app/conftest.py
Do not edit:
- backend/ofo_app/routes/execute.py (the one-exit-door lane); the plan sheet files (Lane R2)
- Lane N's `_index_spot_held` fix (fix/last-close-1127); Lane V's leg-stop-risk lines in routes/paper.py (merge K first)
A fix that needs one of those files: write it under "For the owner lane" in RESULTS, do not edit.

Decision texts (build to these words):
- (50) Per leg, the lots it will hold after EACH order of the batch (held plus added, signed net) must not exceed
  "Most lots in one leg". A flip long to short counts as growth.
- (51) Per order, units must be below the stored freeze quantity; an exit above it is refused with a sentence naming
  the most one exit may carry and that the rest is exited in further orders.
- (52) "Most lots in one leg" defaults to 100.

Queue:
1. Lots limit and freeze at the door (50), (51), (52). Real cases: 60 lots held plus 50 added on one leg = 110, refused
   at 100; 5,000 sold refused; 100 sold accepted, 101 refused; a paper exit of 30 lots above a 1,800-unit freeze
   refused; SENSEX has no stored freeze quantity: lots limit applies, no freeze refusal.
2. Triage C10 (ADR-330 (28)): the server refuses an entry when no connected provider holds the index price. Check
   whether Lane N's 5e7d34c9 already fixes it; if it does, build nothing twice and say so.
3. PC check T3-13, entry price 0: reproduce on the PC's build; if refused already, add guard tests and name the leg.
4. List (do not build): `place_paper_orders` waits for the market while holding a connection and the row lock.

Reviews required: one Opus review of the order-door change. Why Opus: a wrong answer lets an oversized order through
or traps an exit.
Pushes: one per item group; gate result on each; first push within 60 minutes of start, even if partial.
Core: `check_order_size` in `paper_limit.py`, called by `place_checked`, the door both paper routes use.
Proof: 60 held plus 50 added on one leg is refused with the new sentence, and 100 is accepted, on a fresh database,
output read back, before any route is changed.
New on-screen sentences: `paper_leg_total_over_limit`, `paper_exit_over_order_limit`,
`paper_entry_price_not_above_zero`.
