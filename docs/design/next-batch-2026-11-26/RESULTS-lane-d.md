# Lane D: the 32 deferred issues #724 to #755 (26-27 Nov 2026)

Step: clean-up D-07 (one triage pass on open issues), allowed beside any step of `docs/process/standing-direction.md`.
Branch `fix/deferred-1126` from `origin/integration/nb-1126` at 3d7aaf7. Paper only; no migration; no issue closed
here (the coordinator closes).

Spec basis: ADR-002, ADR-003, ADR-008 (one engine, exact money), ADR-016..019, ADR-237 (4), ADR-250, ADR-328 (3),
ADR-330 (3), (23), (34), (36); REQ-049, REQ-109, REQ-133 AC-3, REQ-138, REQ-154.

## Summary counts

| Class | Count | Issues |
|---|---|---|
| FIX NOW | 18 | #725 #726 #727 #728 #729 #730 #734 #736 #737 #738 #739 #740 #741 #743 #745 #746 #748 #749 |
| NEEDS THE OWNER | 3 | #732 #733 #753 (questions in `owner-questions-lane-d.md`) |
| WAITS FOR A STAGE | 4 | #735 #742 (D-12, after step 4), #750 #751 (step 4: sign-in, migration) |
| ALREADY FIXED | 1 | #747 (46b970e) |
| OTHER LANE NOW | 5 | #724 #744 #752 (Lane R), #754 #755 (Lane G) |
| NOT WORTH DOING | 1 | #731 |

Older `deferred` issues (135 open below #724): not triaged one by one in this pass; see "Older issues" below.

## Triage table

Harm: what a user loses. Size: small = one small push. Line numbers are on this branch at 3d7aaf7.

| # | What the user sees | Harm | Size | Class | Note |
|---|---|---|---|---|---|
| 724 | Builder leg list of a paper trade: the price now comes from the paper book (42b49f4), but the "as of" time next to it and the "Oldest leg price as of" line still come from the other (outcome) reply, so the time can belong to a different price | low | small | OTHER LANE NOW (Lane R) | Same reader class as #744 in `StrategyBuilderPage.vue`, where Lane R works today; remainder = `quoteAtById` / `oldest_quote_at` at `StrategyBuilderPage.vue:1257` |
| 725 | Paper P&L rows from the tracking reply: an open leg whose contract was closed and reopened shows only today's open part, not the part already booked | medium | small | FIX NOW | `routes/tracking.py:314` uses `.unbooked` for an open leg; ADR-328 (3) says the leg's total result. The panel's own rows read the book total since 42b49f4; the server row is still wrong for other readers |
| 726 | A tracking exit is stored with the time of the price quote; an exit from the orders screen is stored with the time it was placed, so History can show a tracking exit earlier than it happened | low | small | FIX NOW | `tracking.py:562` vs `paper.py:1388`; `paper_monitor.py:23` "never back-dated" |
| 727 | Exiting from the tracking panel when the price read fails shows a raw server error; the same failure on the orders screen shows a named "prices not live" refusal | medium | small | FIX NOW | `tracking.py:548` `on_read_error="raise"` |
| 728 | The two exit screens disagree on "not connected": one refuses when the broker link is down, the other goes on with what it has | low | small | FIX NOW | `paper_exit.py:64` `connected_rule`; one rule (provider status) for both, fail closed |
| 729 | An exit from the tracking panel closes only the lots read before the lock; if the leg grew in between, part of it stays open without a word | high | small | FIX NOW | `tracking.py:554`; `paper_exit` already supports `closes="locked"` |
| 730 | "Review and add" dialog built on an old view of the trade can still post an exit after the trade changed in another tab (the server still refuses an exit larger than what is open) | low | small-medium | FIX NOW | `StrategyBuilderPage.vue:434`; reuse the `contractsChanged` gate. Hot file (Lane R/U): last in order |
| 731 | Two tabs can each send a partial exit of the same lot; both are stored | none | medium + migration | NOT WORTH DOING | The store locks the strategy and re-checks the open quantity under the lock (`paper_store.py:85-95,128-138`), so the two exits can never close more than is open; each is a legal order the user sent. An idempotency key needs a migration for no loss |
| 732 | A price-level exit does not fire while any of the trade's contracts has no live price, and nothing tells the user it is waiting | medium | medium | NEEDS THE OWNER | Needs alert wording and kind (ADR-003) and a repeat rule; question D-Q1 |
| 733 | "Keep this level" re-arms a level that the index may already have crossed, so it fires on the next tick | low | medium | NEEDS THE OWNER | Refuse a crossed level, or let it fire as the first arm does; question D-Q2 |
| 734 | A stop that fires in the first second after the watcher reloads can record "index value not available" in its alert | low | medium | FIX NOW | `paper_monitor.py` reload / `_fire`; alerts path, Tier A |
| 735 | internal: no user effect today. Four display price readers do not go through the one market reader | none | large | WAITS FOR A STAGE | Structural debt D-12 waits until step 4 is done |
| 736 | A deleted strategy's adjustment plan can still be read and changed, and its alerts styled | medium | small | FIX NOW | `playbook_store.py:329` `_OWNS_STRATEGY` lacks `deleted_at IS NULL`; `strategy_store._OWNED` has it |
| 737 | internal: a "not a number" price from the broker would pass into the execute checks instead of reading as no price | low | small | FIX NOW | `execute_plan.py:102`; money, Tier A |
| 738 | internal: a "not a number" or infinite strike or tick size in the instrument list would be stored | low | small | FIX NOW | `ofo/instruments/parser.py:52` |
| 739 | Outside India near midnight, "days left" to expiry on the Option Chain is one day off | low | small | FIX NOW | `displayFormat.js:144` `localDay`; one caller `useChainLive.js:155` |
| 740 | internal today (same holiday table): the stop watcher decides "market open" by its own rule, not the rule the rest of the app uses | low | small | FIX NOW | `paper_monitor.py:180` vs `may_act.market_open` |
| 741 | A trade with a buy and a sell leg of the same contract shows that contract's whole P&L on both rows of the Paper P&L panel, so the rows add up to twice the total | medium | small | FIX NOW | `TrackingPanel.vue:138-141` keyed by contract only |
| 742 | internal: 17 read-only routes count as reaching order code because of one import, so the order-closure guard protects nothing for them | none | medium | WAITS FOR A STAGE | Structural (D-12); the fix also changes guard pins, which need the owner's own words |
| 743 | When the daily alert cap or quiet time holds an alert, a price swinging across the higher step writes one "held" history row per candle for the rest of the day | medium | small | FIX NOW | `alert_gate.py:262-267` judges the hold on the step, not the rule's line; Tier A |
| 744 | Builder per-leg prices of a paper trade read other sources | - | - | OTHER LANE NOW (Lane R) | Full table and leg list fixed by 42b49f4; only `AdvancedDetails.vue:23` (bid/ask) left in the guard's REMAINING list |
| 745 | Create Strategy: a red "server took too long" box stays above a list that loaded fine | medium | small | FIX NOW | `CreateStrategyPage.vue:76-112` one shared error slot, cleared only at the start |
| 746 | When the database is busy, adopting a holding says the holding is wrong instead of "busy, nothing was changed" | medium | small | FIX NOW | `order_book_store.py:146-158`; `errors._busy_database_error` exists |
| 747 | Orderbook shows quantity in lots | - | - | ALREADY FIXED | 46b970e (on this branch): `tests_app/test_paper_order_lots.py`, `orderbook-columns-s25.test.js`; ready to close after the owner's re-test |
| 748 | Option Chain: after picking a new expiry, every price reads "Unavailable: no price has been received" for up to 26 s instead of "waiting for the first price" | medium | medium | FIX NOW | REQ-133 AC-3 gives the wording; catalogue `outcome_waiting_first_price` exists; `chain_push.py:415-418` |
| 749 | Builder closed-leg table: the stop-loss sentence wraps to 3 lines inside the narrow Exit column | low | small | FIX NOW | `ClosedRows.vue:14`; render as a full-width row |
| 750 | Builder Settings has only "Show legs as", and a choice is lost on reload | medium | large | WAITS FOR A STAGE | Step 4 (signed-in user, a settings table = migration) |
| 751 | An unsaved builder strategy is lost on reload | medium | large | WAITS FOR A STAGE | Step 4 (REQ-154, stored draft per user = migration) |
| 752 | After the close, prices keep moving under a 15:30 banner | - | - | OTHER LANE NOW (Lane R) | ADR-330 (36) built on fix/screen-findings-1126 (0e6f6ac, d73508f) |
| 753 | Editing a plan saved before ADR-247 silently adds the 2x-credit stop line to it | medium | medium | NEEDS THE OWNER | "Saved before" from `accepted_at`, which every edit restamps; a once-set marker is `created_at` (meaning changes) or a new column (migration); question D-Q3 |
| 754 | internal: an egress test is red when a proxy is set | - | - | OTHER LANE NOW (Lane G) | not touched |
| 755 | internal: the gate is red while a builder worktree sits under `.claude/worktrees/` | - | - | OTHER LANE NOW (Lane G) | not touched; this lane keeps helper worktrees outside the repo |

## Order of fixing (harm first, related ones in one push)

1. Push 1, backend exit and stores (Tier A): #729, #727, #725, #726, #728 (tracking exit door); #746, #736, #743, #740,
   #737, #738.
2. Push 2, screens: #741, #745, #748, #749, #739, then #734 and #730 if time allows.

## Older issues

135 open `deferred` issues below #724 were not triaged one by one in this pass (budget). Small-looking candidates
from the titles alone, for a later pass: #602 (status time without a date), #614 ("exited 1 legs"), #710 (alert label
with no amount), #711 (raw instrument id on a trade page), #600, #597.

## Fixes

(filled in as each push lands)

## Ready to close (for the coordinator)

- #747: fixed by 46b970e (already on integration/nb-1126).

## To file as deferred issues

(none yet)
