# Review findings of the 23 Nov live iron condor test fixes

Each section is one independent review file, unedited except for scrubs.


## ic-live-test-2026-11-23\review-d01

# D-01 review (Tier B, read-only, commits d25c3d73 / f026a598 / 48040b55)

| Severity | Finding | file:line | Concrete failing scenario |
|---|---|---|---|
| MAJOR | A leg stop whose contract has no feed key is compared with the INDEX spot. `keys.get(cid)` falsy falls to `paper.price_of(snapshot.spot, ...)` | backend/ofo_app/routes/paper.py `_already_crossed` (price = ... else paper.price_of(snapshot.spot)) | Open leg with feed_key None (expired or untracked), stop "above 35": index 22533 >= 35 -> refused with the leg sentence although there is no live leg price (class says it must save). The monitor never watches such a trigger (paper_monitor.py ~L143-148: key None -> not watched). "below" saves, so behaviour is inconsistent. |
| MINOR | Lowercasing regex turns "Zerodha ..." reasons into "not saved: zerodha shows ..." (Zerodha, Kite, Sensibull reasons; "NIFTY" is safe, 2nd letter uppercase) | frontend/src/components/strategy/PaperStops.vue notSaved (48040b55) | Any 4xx with a Zerodha-leading reason from the Stops panel (e.g. templates.py L476-750 family). Lower only when the reason is known to be a sentence start, or lowercase nothing except the first word "The". |
| MINOR | Test gaps: no test for ctx None, market closed, read raising, stale LEG price, leg without feed key. The stale-spot test passes even if the check were removed. | tests_app/test_paper_triggers_routes.py (f026a598) | A refactor that makes `_already_crossed` raise inside the try is swallowed (log only) and only the refusal tests would notice; the no-price states are unguarded. |
| MINOR | Leg sentence is not the owner-approved text (ADR approves only the exit sentence); ADR header L6 still says "PENDING OWNER READ"; pins mark both new keys "pending owner read" | spec/decisions/ADR-317.md:6; tests/errors/template_pins.json:4244 and :4248 | Owner approved the exit sentence on 23 Nov 17:12. Pin for paper_trigger_already_crossed (L4244) can move to reviewed; the leg pin (L4248) stays pending until the leg wording is read. |

Holds: (1) same rule (`stops.crossed`, >= / <=, live only) and same index quote (provider spot); leg uses leg_price = price_of(quote). (2) stale/missing price -> `crossed` False -> saves; index and leg independent. (3) `except Exception` logs only; refusal tests would fail if the check broke. (4) strategy loaded FOR UPDATE before check; a cross between check and insert is fired by the monitor on the next tick (acceptable). Wording of the exit sentence matches ADR exactly.

Covers the class: no (leg stop with no feed key refused against index price)
Verdict: PASS WITH FINDINGS (fix the MAJOR before merge)


## ic-live-test-2026-11-23\review-d02

# D-02 review (Tier B, committed content 53dfc568..5f3b84aa)
| Severity | Finding | file:line | Scenario |
|---|---|---|---|
| MINOR | Stop-out alert lists prices in contract-id order (targets), not the recorded buys-first order | backend/ofo_app/paper_monitor.py ~231-236 | 4-leg condor stop: Orderbook shows both buy-backs first; alert body lists legs by contract id |
| MINOR | Entry-as-sent limit is only in a docstring ("keeps the trader's leg order"); it does not say an entry can show SELL before its hedge BUY | paper_store.py buys_first docstring | Entry [SELL c1, BUY c0, ...] is stored short-first; Orderbook shows naked short between fills |
| MINOR | Re-entry on a fully exited (flat, non-empty) book is reordered, and entry facts are not recorded (first_fill false) | paper_store.py place | Re-enter after full exit: buys first (safe), but a new contract's leg number follows the reordered sequence |
| MINOR | Same-side short legs (covered put: SELL future + SELL put as adds) keep sent order; no protection rule between two SELL adds | paper_store.py buys_first | Put sent before future: put short unprotected between fills. Unavoidable unless future is ordered first |
| MINOR | No test asserts recorded order through paper_limit.place_checked | tests_app (test_paper_adjustment_limit.py only) | Regression there would pass CI |
Attack 1: holds. Buys-first never leaves a short unprotected for debit spread, covered call/put exit, hedge roll, ratio shapes (protection is always a BUY; the only gap is two SELL adds, above).
Attack 2: holds. All callers build same-side exit+add on a flip; _check_reducing already refuses an add against the held side. No real caller builds a refused batch; test_paper_batch_buys_first line ~170 only covers a synthetic one.
Attack 3: holds. Same placed_at in a batch, booked P&L order-independent (tested), stable sort keeps same-contract exit before add.
Attack 5: confirm list key (rank by BUY, exit) equals server key; exitRowsFor matches. Only the stop alert differs.
Covers the class: yes
Verdict: PASS WITH FINDINGS


## ic-live-test-2026-11-23\review-d03-r2

# D-03 re-check (e31c98cb..11754f63), Tier B, read-only

Previous review: MAJOR stop/settle unmarked CLOSED (paper.py `_adjustment_marks`: `r.step != "entry" and not r.is_exit`). MAJOR silent Keep CLOSED (PaperStops.vue `keep`: Kept / Already kept line). MINOR Keep race CLOSED (keep route: `not await cancel(...)` raises 409; cancel is `UPDATE ... WHERE fired_at IS NULL ... RETURNING id`, empty list when fired). MINOR mark-build failure CLOSED (marks every armed exit with a generic line). Strike format CLOSED (strike passed through). STILL OPEN: pooled shorts across expiries and a call exit named when only the put side changed (`_adjustment_marks` calls/puts pooling); same-instant `created_at >= latest` tie.

Q2: Production, fired first: cancel returns [], 409, rollback; the monitor's claim is its own committed transaction, so Keep's rollback undoes only Keep's work (nothing written yet). No new row stored. The narrowed test still fails if the guard is removed (a second row id appears in `[r["id"] ...] == [first]`). It no longer proves the old row stayed "fired", acceptable.

| Severity | Finding | file:line | Failing scenario |
|---|---|---|---|
| MINOR | Read failure or invalid rows show NO line, same as "nothing armed". | PaperConfirmDialog.vue askArmedExits catch | Network blip: trader confirms a short-strike change, sees no armed-exit line. Exit stays armed and is marked afterwards, so no loss, but the spec's "list names each" is silently skipped. Show "could not check armed exits". |
| MINOR | Full exit shows nothing, and does not say the exits will be cancelled. | paper.py paper_armed_exits (`not positions`) | Trader closes all legs, sees no mention of the armed exit. |
| MINOR | Keep on a persistent mark failure re-stores the row each press and the generic mark remains. | keep route | Press Keep: "Kept", still marked. |

Q3: the dialog posts the same `orderOf` rows it sends to the endpoint; the endpoint uses the same `PaperOrdersIn` model. Ownership via `_load_strategy`. Test for another user's strategy not seen (unverified).
Q4: Entry is only the first history row. A hedge basket then a sell basket (different placed_at) marks only exits armed between the two, which is correct. Fired exit closes every leg, so no marks. History is built from orders only, so Greeks or price updates never count.
Q5: No new app-initiated move; only Keep (trader) cancels and re-creates.

Covers the class: yes
Verdict: PASS WITH FINDINGS


## ic-live-test-2026-11-23\review-d03

# D-03 review (e523ad71 + 0a26b488), Tier B, read-only

| Severity | Finding | file:line | Failing scenario |
|---|---|---|---|
| MAJOR | A fired leg stop (kind "stop") or an expiry settle is its own history row, step "stop"/"settle", never "adjustment". Legs change, exits are not marked. Nothing in the code or tests says this is intended. | paper.py `_adjustment_marks` (times = step=="adjustment"); adjust_history `_steps` | Short call leg stop fires, closing the call. "Exit above" stays armed, no mark, no "you no longer hold a short call". Same for one expiry settling in a two-expiry trade. |
| MAJOR | Keep success shows no result line. `run(...)` without saving=true and no saved text. Keep on an unmarked row, or when marks failed to build, is a silent 200 no-op and the mark stays. | PaperStops.vue `keep`; paper.py keep route | Trader presses Keep after a logged mark-read failure. Nothing changes, no line. |
| MINOR | Keep is not atomic against the monitor, which takes no strategy lock. If it fires the old row between the read and the cancel, the cancel result is ignored and a new armed row is added on a flat strategy. Nothing is lost: the monitor later cancels it. | paper.py keep route | Fire and Keep at the same instant leave one stray armed row. |
| MINOR | Mark-build failure marks nothing, only logs (item 5), and no test covers it. | `_adjustment_marks` except | One bad contract row hides the warning for the whole strategy. |
| MINOR | Strike prints unformatted ("22800") next to the level formatted "23,100.00" (item 4). Shorts from several expiries are pooled, so the lowest call may be a far-expiry leg. A call-side exit gets "your new short call is X" even when only the put side changed. | explanations.py; `_adjustment_marks` | Weekly short 25600 plus monthly short 25200: it names 25200. |
| MINOR | Same-instant tie: `created_at >= latest` means an exit saved in the same microsecond is unmarked. Trigger `created_at` source (now() vs clock_timestamp) was not verified. | paper.py | Unlikely. |

Item 1 holds: old row cancelled and new row added in one commit, so the DB never shows zero armed exits. Keep runs no "already crossed" check, so it cannot refuse. A stale monitor tick on the old id fails the claim, and the new row fires on the next tick after notify(). The new row has no alert or history link; the alert is made on fire. Leg stops return 404. Another user's strategy is refused by `_load_strategy`. Cancelled or fired exits return 409.
Item 2: both times come from the database (placed_at is not used), and a basket shares one placed_at. OK.
Item 3: Reduce and Close tested spreads count. A full exit is excluded (is_exit), tested. Two-expiry settle: see MAJOR.

Tests missing: leg stop and settle marks, a mark-read failure, two expiries, ratio shape, Keep on another user's strategy, Keep racing the monitor, a Keep result line, and Keep on an unmarked exit (the test comment claims it, but it asserts 409 on a cancelled row).

Covers the class: no (the main path holds; leg stop and settle changes, and the silent Keep, do not)
Verdict: PASS WITH FINDINGS


## ic-live-test-2026-11-23\review-d04-p2

# Review D-04 part 2 (commits e5749baf, 340155a6) - Tier B, read-only

| Severity | Finding | file:line | Failing scenario |
|---|---|---|---|
| MAJOR | No fallback when the entry shape has no type: `entry_position or position` is non-None, so a None type from the entry shape is final ("no playbook"). Strike gap is read from the ENTRY expiries; once those contracts leave the instrument master the gap is None and type None. | adjustment_check.py:174 (`entry_type`), strategy_type.py:59 | Strategy 164 (23 Nov + 1 Dec legs): after 23 Nov settles, entry legs' expiry is gone; if the master no longer lists it, rules AND the maximum vanish the next day - same defect class. Not verified whether the master keeps expired rows. Fix: fall back to the current shape when the entry type is None. |
| MAJOR | Entry batch = orders with equal `placed_at`; one confirm = one placed_at (paper.py:1040), so one confirm is fine, but an entry in two confirms (hedges first, shorts later; drafts mode in several confirms) gives entry shape = hedges only (e.g. long strangle -> longvol). Re-entry after full exit keeps the OLD first shape. | adjustment_readers.py `entry_position_of` | Condor entered as 2 confirms: entry = long-wing pair -> wrong rule set, maximum from the wrong playbook. Not verified that the builder ever splits confirms. |
| MINOR | Condor rules run on the put spread: T-05 side ratio -> NotChecked (side_value_not_positive); T-01/T-08 use current shorts only, no_short_leg -> NotChecked; approaches needing an untested side are refused by name (approaches.py:703). No crash found, no alert for a side not held. | adjustment_eval / adjust_ratios.py:76 | S-02 "trending day" uses net delta per lot against the condor limit 0.15; a put spread is directional by nature, so it can fire and offer rolls (not measured). |
| MINOR | Existing rows change on deploy, no migration: any plan-less strategy already reduced switches from its current-shape playbook to the entry one (164: credit/none -> condor, max 2). Intended by ADR-318 (4) but visible. | - | Open owner trade 164 shows "1 of 2" after deploy. |
| MINOR | Perf: no new query; `entry_position_of` is one in-memory netting over already loaded orders, and the classifier still runs once per call. Negligible against the 15-60 s check. | adjustment_readers.py | - |

Q3 holds: real book returns before `entry_position` (readers:152), `entry_position=None` -> current shape; orders with no time -> None.
Q6: only `strategy_type(` caller left outside `entry_type` is `adjustment_readers._guards_on` (:286), fed `tracked.entry_position or position` by adjustment.py:590, so covered.

Covers the class: no (entry type None has no current-shape fallback; split-confirm entry).
Verdict: PASS WITH FINDINGS


## ic-live-test-2026-11-23\review-d04

# D-04 review (commits 391cec9c 6c516c9c e7319797 0713b6ef vs ADR-318)

| Severity | Finding | file:line | Failing scenario |
|---|---|---|---|
| MAJOR | Reduce / Close tested spread are offered and marked "over your plan maximum", but the server still refuses them: check_adjustment_limit raises paper_adjustment_limit whenever the stored count after the basket > max. Not touched by the 4 commits; ADR-318 says nothing about it. | backend/ofo_app/paper_limit.py:67-99 (place_checked :130) | Strategy at 2 of 2, trader picks "Close the tested spread" (row reads "3 of 2; this would be adjustment 3, over your plan maximum of 2"), places it: refused. Offer is dead; owner decision (2) not deliverable. Only Exit all (net qty 0) passes. Needs owner/lead call: relax the server for risk-cutting baskets, or word the offer. |
| MINOR | A-26 "Buy back the decayed untested short" and A-27 "Buy back cheap shorts" stay offered at limit (in EXIT_REDUCE, KINDS close_part), same server refusal; ADR-318 names only Reduce and Close tested spread. | offered.py:21; approaches.py KINDS | Trader at limit sees A-26 offered with over-max mark; leaves a long wing, not a pure cut. Confirm intended. |
| MINOR | Exit all now carries value=stored, so it ties No change on "fewest adjustments"; 3 test expectations changed. Below the limit Exit all (and Take profit A-24, Time exit A-35) now also share the leader mark on that row. Behaviour change outside the class, though it follows ADR-255. Frontend not changed or checked by these commits (unverified). | compare.py:479-481 | Strategy 0 of 2: before, only No change led the row; now Exit all also leads. |

Q1 withheld: A-01, A-05, A-11, A-02, A-04, A-06 (rolls, shift, convert; reason "plan maximum of N reached"). Kept with true count and over mark: A-29, A-28, A-25, A-26, A-27. No count: A-31, A-24, A-35 (any basket with trades and empty after). A-36 kept, shows stored. Nothing that opens risk is offered; A-30/A-12/A-09 etc. are not built. Take profit is treated like Exit all: yes.
Q2 used 3 of 2: rows "4 of 2; this would be adjustment 4, over your plan maximum of 2": holds. Header uses 3 of 2, true.
Q3 no max: "N used; no plan maximum set", Exit all "Not an adjustment". Max 0: "1 of 0; ... over your plan maximum of 0", withheld "plan maximum of 0 reached": holds.
Q4 header, rows, route all read tracked.adjustments_used; drawer (AdjustSteps.vue:83) reads totals from the same history count: holds.
Q7 wording: neutral, no advice: holds.

Covers the class: no (offer and server disagree for Reduce/Close at the limit)
Verdict: PASS WITH FINDINGS


## ic-live-test-2026-11-23\review-d05-r2

# D-05 r2 review (Tier B, read-only, commits 0c3a86a1 c65bc5e0 21d30cd0)

| Severity | Finding | file:line | Failing scenario |
|---|---|---|---|
| MAJOR | Stale list keeps live-looking Exit; price comes from the stale LTP text; no test | PaperStrategies.vue ask()/exitRowsFor (paperList.js:157-162) | Refresh fails, trader ticks a leg, Exit opens confirm prefilled with the old LTP and can post it. Nothing in the diff refuses it (REQ-109 AC-5 untested) |
| MAJOR | Mixed line trusts the local armed list | PaperStops.vue saveExit (diff +76) | Server only sets already_set when NOTHING new. List null/stale: a duplicate level is reported "Saved". List stale the other way (trigger cancelled/fired elsewhere): "Already set" while a row was stored |
| MAJOR | Stale note sits under the banner, not by the numbers | PaperStrategies.vue:13-15 | Long list: totals/LTP/P&L scroll off from the note; no per-figure marker; the old test that forbade figures is replaced by text only |
| MINOR | Stale comments now false: "A failed or unreadable read shows no figure" (file head), "old figure is never left on screen" (usePaperRefresh.js header) | PaperStrategies.vue:7 | Reader trusts a removed guarantee |
| MINOR | Backend concurrency test never run (commit says so); one asyncio.gather over two sessions, 5 rounds; lock-removed run claimed, not shown | test_paper_triggers_routes.py:+464 | Could be green by luck; cleanup is try/finally but `user` stays empty if _setup commits then raises, leaking committed rows in the shared DB |
| MINOR | Number() compare: "29,990.00" gives NaN (likely rejected earlier by paperPriceOk); leg-stop saves get no mixed line | PaperStops.vue | Two leg stops at one level not covered |

Holds: banner clears after next good read (test); first load fail then success works (items null, then set); 2xx bad shape keeps list, shows banner+note (code, no test); confirm dialog is cancelled on failure.

Tests missing: unreadable-shape keep; Exit from stale list; save with armed list null; leg-stop save; note adjacent to figures.

Covers the class: no (refresh and Stops-panel parts yes; stale-list actions and the mixed line with an unknown armed list are not covered).
Verdict: REVISE


## ic-live-test-2026-11-23\review-d05-r3

# D-05 r3 review (Tier B, read-only, commits d32d6e9c e3ea2b37)

Previous MAJORs: 1 CLOSED (one gap below), 2 CLOSED, 3 CLOSED.

| Severity | Finding | file:line | Failing scenario |
|---|---|---|---|
| MAJOR | Confirm dialog stays open when the refresh answer is 2xx but unreadable. show() sets errorParts but does not clear `confirm`; fail() does. doExit() has no stale check | PaperStrategies.vue:226-231, 270-276 | Trader opens Exit (prefilled from the last good LTP), the next poll returns an unreadable body; list is paused, dialog still open, Confirm posts the old price |
| MINOR | No test for the unreadable-shape dialog case; r3 tests cover failed read only | tests/paper-strategies.test.js | Above gap ships green |
| MINOR | "Add orders" / "Open in Builder" links stay live while paused; they only navigate to the builder (own live read), no order from old prices | PaperStrategies.vue:119-120 | None found |

1. Exit is disabled by `stale` (:122), reason line :123, `ask()` refuses (:271), and a disabled button cannot take keyboard input. No bulk exit exists. Failed read cancels the dialog (:239-241). Only gap: the finding above.
2. CLOSED. Totals, per-card figures, Breakeven/Max, Greeks, LTP, Booked/Unbooked/P&L, compact total all go through pnlText/shownFig/stale (:39-42, 71, 77, 108-111); reason "Paper P&L paused - prices not live" is shown. Avg also dashes (harmless). Cards, legs, open Stops panel stay.
3. CLOSED. Backend paper.py:1303-1315 computes `armed` and `fresh` from one read under lock_strategy; `duplicate` from the same sets. Frontend PaperStops uses only already_set / already_armed. Mixed, all-new, all-existing and leg-stop cases are correct by reading; only an all-new/mixed backend test exists (one test, not run by me).

New in r3: stale clears on the next good read (errorParts=null, :233); live prices are never paused (stale needs errorParts and items); first-load failure keeps the full-page error (items null).

Covers the class: no (the unreadable-reply path still allows an order from old prices).
Verdict: REVISE (one MAJOR)

Not checked: tests were not run; HeldNote contents assumed non-live.


## ic-live-test-2026-11-23\review-d05

# D-05 review (Tier B, read-only)

| Severity | Finding | file:line | Failing scenario |
|---|---|---|---|
| MAJOR | No test for concurrency. The lock test only checks call order via monkeypatch. Nothing fires two POSTs at once. | tests_app/test_paper_triggers_routes.py (7d83b78a) | Lock line deleted and ordering kept elsewhere: tests still green. Required "two requests at one instant store one row" has no assertion. |
| MINOR | Untested: cancelled/fired identical trigger must not block a new save (ADR-317 (3)); Decimal "25720" vs "25720.00"; leg stops on different contracts, same level. Code is correct (state filter, Decimal hash-equal), unguarded. | routes/paper.py ~1303 | Change filter to ignore state: suite stays green. |
| MINOR | Mixed save (above armed, below new) answers "Saved: exit above X and below Y" though X was already set. already_set is all-or-nothing. | PaperStops.vue saveExit | Reads as if both were newly stored. |
| MINOR | Lock is held across _already_crossed (live-price read) before the armed read. | paper.py:1293-1297 | Slow feed read delays place/monitor writes for that strategy. Same lock order as paper_store.place (strategy row, then inserts): no deadlock found. Monitor takes no strategy lock. |
| MINOR | "Not saved: could not get an answer" is shown on timeout though the server may have stored it. | PaperStops.vue NO_ANSWER | Retry yields "Already set": safe, but the first line was untrue. |
| MINOR | 4xx without parts and 2xx without triggers show "press Save again" though retrying will not help; a bad 2xx also nulls the trigger list. | PaperStops.vue run() | Spec gap only. |
| MINOR | Refusal line shows only what_happened; ADR wording "To close now, use Exit." is not shown. No test asserts the "Not saved: <reason>" string for a 4xx (the old test asserts the refusal text only). | PaperStops.vue notSaved | Owner-approved wording differs from screen. |

Holds: lock is SELECT FOR UPDATE in the request's own transaction (strategy_store._locked), taken before the read and insert, released at commit/rollback. Boxes cleared only on success. busy guard returns null, but the button is disabled, so no press is dropped. Error line is rendered below the buttons. Initial load shows "Saving..." and disables Save (covered by the first new test; harmless, brief). Stale lines: run() clears both at start; cancel clears Saved with no replacement. Changed network-failure assertion: stricter, not weaker (exact string, still checks the neutral text is gone). Scope creep: none. Wording is decision-support. Spec/ADR-318/digest edits are outside the files named.

Covers the class: no (concurrency and cancelled/fired/leg cases have no test)
Verdict: PASS WITH FINDINGS


## review-d60

# D-60 review (Sonnet, Tier B, read-only; code read, no tests run)

| Severity | Finding | file:line | Failing scenario |
|---|---|---|---|
| MAJOR | Warning/question key = instrument_id AND action; backend gate key = (expiry,type,strike), ignores action | LegList.vue sameContractAs; safety.py:191,399 | NIFTY 24500 CE BUY + SELL (AC-11 "two legs") shows no warning, no question; at execution gate_duplicate_leg blocks it. Trader finds out late |
| MAJOR | Paper path never runs the gate: check_pre_execution called only from execution/partial.py:654 | safety.py:656 | Kept-separate duplicate: Add to Paper unblocked (not proven that paper skips it; grep found no paper caller). "Blocks execution" holds for live only |
| MAJOR | Uncovered paths silent: Option Chain Add Selected, ReadyMade + extra leg, strike stepper (warning only) | OptionChainPage.vue, chainSelection.js, ReadyMadePanel.vue | Chain import of a held contract = silent second row (same-action warning appears; no question). Most likely trader path: Option Chain |
| MAJOR | Increase onto held leg just does lots+=n; no entry/paper-order handling, no max-lots recheck | LegPicker.vue ~531-537, 604 | Held leg 8 lots, max 10, increase by 5 -> 13 lots, no validation. Drafts mode on paper: held leg changed in place, not a pending order |
| MINOR | Double pick: increase raises lots of `clash` from the evolving `legs` copy, OK; but picking 2 contracts of same id impossible. Cancel aborts all picks (they stay selected: good) | LegPicker.vue 596-609 | Two duplicates = two sequential dialogs; Cancel on 2nd discards the 1st "Increase" (nothing emitted until end): consistent |
| MINOR | Dialog not modal: no Escape, no focus move/return, no focus trap; Done stays clickable (busy only) | LegPicker.vue ~679 | Keyboard user cannot dismiss; picker rows still active behind it; unmount mid-await leaves promise unresolved, busy stuck |
| MINOR | Edit-form by-contract onto clash: `old` row removed on Increase, fine; Cancel keeps form open | LegPicker.vue 526-537 | holds |
| MINOR | Same-token weekly/monthly: instrument ids differ but gate treats same expiry date as ambiguous | safety.py:191 | holds as gate concern; missing contract id (null instrument_id) matches other null legs |

Item 5: drafts-mode netting (REQ-109 AC-9) not examined (budget); question appears for same action only.

Covers the class: no
Verdict: REVISE


## review-order-fix

# Review: fix/ic-live-test-1123-order (53dfc568..6c516c9c), read-only, Opus, 2026-11-23

## Defect 1: BUY-first paper baskets. Covers the class: YES for paperOrdersFor; NO for every paper basket. PASS WITH FINDINGS.

Safety proof (all shapes): BUY phase: every fill only adds long or removes short, so position = before + bought options
(payoff >= 0 each). SELL phase: position = after + the not-yet-sold sells (each a long or a missing short, payoff >= 0).
So at every point the worst-case payoff is no worse than the worse of before/after. Holds for roll, shift, reduce,
close-spread, iron fly, diagonal, buy-back, full exit, plain entry, 2-lot unbalanced. Order WITHIN a phase does not
matter for payoff risk (SELL exit vs SELL add either way still = after + longs).
Same-contract exit-before-add DOES matter, for the server: paper_store.place `_check_reducing` (paper_store.py:88-90)
checks each exit against the running book; BUY add before BUY exit of a short (put roll, 25400 PE) nets to 0 and the
exit is refused. The comparator keeps exit (rank 0) before add (rank 1) for the same side: correct.
Margin/cash: the peak state is after all BUYs, before any SELL credit. Put roll: two lots of 25400 PE bought before the
25300 PE / 25500 PE credits. Payoff risk is lower, but the cash needed is higher than before or after. Paper: no effect. Real orders: premium for every BUY is needed up front.

Findings
- MAJOR frontend/src/lib/paperList.js:157 `exitRowsFor` (Paper tab "Exit (N)", PaperStrategies.vue:120,267,282) is a
  second paper-order builder that skips paperOrdersFor: rows go in tick/table order. Tick all four condor legs ->
  SELL long, BUY short ... as listed. Outside the stated class, but it is the same user-facing defect.
- MAJOR (server, not fixed) routes/paper.py:1029-1050 keeps body order; paper_store.place stores in order
  (paper_store.py:88-94). Other placers are not BUY-first: stop fire paper_monitor.py:222,231 `sorted(open_net)` =
  contract-id order, sides mixed; settlement paper_settlement.py:166-178 = `due` order; tracking exit
  routes/tracking.py:533 = body.legs order. Today's 4-leg stop-out went in contract-id order (I did not read the DB to confirm the sides).
  The proposed route sort is safe IF done before line 1029 (exit_prices keyed by index at 1041/1049/1060 are then
  consistent; new_ids at 1052 positional; basket_legs is a count) and with the same rank (exit before add per side).
  Better: sort once inside paper_store.place (the one writer), which covers all five callers (structural, C3).
- MINOR REQ-058 Q238 says "never mixes the two in one batch". A sorted single batch is fine for paper (one transaction).
  For real orders, the order of a list is not a guarantee (finding publisher-basket-order-not-guaranteed). Do not cite this fix as covering ADR-117.
- Tests: exact sequences asserted (roll with the same-strike double BUY, shift, close, diagonal, entry, stability, partial 3->1).
  Mutation (scratch copies, node): "SELL exits before BUY adds" and "adds before exits" both change the roll sequence
  -> red; no sort -> red. The two changed old tests match AC-6 (the buy-back first); no hidden behaviour change.
  Not covered: a 2-lot unbalanced reduce (it gives BUY 2 exit | SELL 1 exit, which is correct).

## Defect 2: Compare "adjustments used" count. Covers the class: PARTLY. PASS WITH FINDINGS.
- max None: counts +1 (test). max 0: "0 of 0" everywhere. used > max: stored count as the header shows. No-change: stored.
  The max-0 test change is legitimate under ADR-297 D4 (the header and rows agree).
- MINOR compare.py:480-481: at the limit S-11 offers only exit and reduce (offered.py:39-40). A full exit is not counted
  (adjust_history.py ADR-255, `made = used - 1 if closing`), so "2 of 2" is right for it. A REDUCE is counted, so
  taking it really makes "3 of 2", but the row now shows "2 of 2". Ties also make every approach a "leader" at the limit.
  The owner decides the wording (Business call).
- AdjustSteps.vue:83 prints the stored count: it agrees.

## Outside the defects: none. 5 files, no kit file, no response-model change.
## Not checked: the DB order of today's stop-out; exit-risk endpoint order independence; full suites.
