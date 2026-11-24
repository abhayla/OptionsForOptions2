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

## A4 review 1 (2026-11-24): D-05 last fix, commit ef733f08

Reviewer: fresh-context helper, read-only, diff only. Class: every path to a paper exit from the paper list while
prices are paused (REQ-109 AC-5). Verdict: no CRITICAL, no MAJOR. `frontend/tests/paper-strategies.test.js` 19/19.

Paths traced in `PaperStrategies.vue`: Exit button disabled while `stale` (l.122) and `ask()` refuses while stale
(l.273); a confirm already open when a refresh fails or comes back unreadable is closed by `fail()` (l.242) and the
`show()` unreadable branch (l.229); keyboard: the Modal handles only Escape and the Tab trap; no exit-all in this
component; compact mode has no exit buttons; the parent `v-if` chain cannot hide the reason line while stale. Server:
`POST /paper/strategies/{id}/orders` reads live prices itself (`_server_exit_prices`, `backend/ofo_app/routes/paper.py`
960-985) and refuses with `tracking_exit_prices_not_live` (409); tests at `tests_app/test_strategy_tracking_list.py:242,274`.

Findings:
1. MINOR `PaperStrategies.vue:283`: the new `if (stale.value) return cancelExit()` cannot run (every stale path nulls
   `confirm` first, so `doExit` returns at `!c`). Harmless defence in depth. Class: yes.
2. MINOR `PaperStrategies.vue:229,242`: closing the confirm while a POST is in flight drops the dialog; if that POST
   ends "unknown", the "unknown outcome, open Orderbook" notice (ADR-017) is not seen. A repeat exit is still refused
   by the server's EXIT_EXCEEDS_OPEN check under the row lock. Not run. Class: no (different class).
3. MINOR `PaperStrategies.vue:122`: `stale` means "refresh failed", not "server reports PAUSED"; a group the server
   marks PAUSED keeps an enabled Exit, and the refusal comes after Confirm (server 409). The server checks only the
   named legs: exiting a live leg while another leg is unpriced is accepted. AC-5 reading (per named leg) to confirm.

Covers the class: yes for the screen (every paper-list exit path passes `ask()`/`doExit()`, stale-gated; confirm nulled
on a failed or unreadable read); the server refuses independently. Not in this class: builder `PaperBookPanel` exit,
`TrackingPanel` exit, trigger fires while paused.

## A4 review 2 (2026-11-24): D-04 server change 2915daf6 and fallback 6972d3d7

Reviewer: fresh-context helper, read-only, static read of HEAD ac04a0a. Class: every paper basket at or over the plan
maximum (ADR-318 points 1 to 5); rules from the entry shape with the fallback (ADR-318 point 4). Verdict: REVISE.

Findings:
1. MAJOR, screen and server disagree when the entry shape cannot be classified. The server (`paper_limit.py:42`) calls
   `check.entry_type`, which falls back to the current shape (`adjustment_check.py:176-177`). The screen's offer path
   (`routes/adjustment.py:590`) passes `tracked.entry_position or position` to `guards_of`, and
   `adjustment_readers.py:287` classifies that position alone, with no fallback. Case: a condor entered on an expiry no
   longer listed, rolled, now at 2 of 2: the screen finds no playbook, shows no limit notice and offers rolls and adds;
   the server refuses the same basket with STRATEGY_VALIDATION_505. Also the server classifies with spot None while the
   screen uses the live spot. Fix: route the offer path through `check.entry_type`. Class: yes (offered against refused).
2. MINOR, permissive paths with no "not checked" note: (a) entry and current shape both unclassifiable, or no listed
   contracts (`paper_limit.py:133`): no limit, opens accepted; (b) `adjustment_readers.py:190-192` returns no entry shape
   when any order lacks `placed_at`, so the current shape decides. These are the existing "no playbook means no limit"
   state. Class: partly.
3. MINOR, accepted set wider than offered: any basket made only of exit, stop or settle is accepted
   (`paper_limit.py:99`), including closing only a protective wing. Matches ADR-318 (5) literally ("close or reduce open
   legs"); not a defect. `paper_store._check_reducing` refuses an exit that does not strictly reduce.

Basket matrix at or over the maximum (`paper_limit.py:78-102`): close only, reduce only, buy back a short, exit all,
draft quantity reduction: accepted. Open a new leg, add to a leg, mixed close and open, roll, strike change, draft that
crosses zero: refused. Already over the maximum: reduce accepted, open refused. The entry basket is never checked.

Bypass check: `place_checked` has two callers (`routes/paper.py:1065`, `routes/tracking.py:539`); the other writers
(`paper_monitor.py:231` stop, `paper_settlement.py:178` settle) only reduce; `INSERT INTO public.paper_orders` appears
only in `paper_store.py:44`. No bypass found. Open: A-23 "Delta-neutral helper" is in EXIT_REDUCE (`offered.py:22`);
whether it places add orders was not confirmed.

`tests_app/test_adjustment_history_why.py:141`: the code is right and the expectation is wrong (ADR-318 point 5). The
basket at line 140 is the third non-entry basket and sends one order of kind "add" at the plan maximum.

Covers the class: no (finding 1 on the offer path; finding 2 silent no-limit paths).

## A4 review 3 (2026-11-24): D-60 round 2, commits 1a81d59e, e1b210d8 and gate move aa6ea9fb

Reviewer: fresh-context helper, read-only. Class: every way a leg is added or moved in the builder, and Add to Paper
with a kept duplicate (ADR-319). Verdict: REVISE (the door is sound; the class is not closed).

Findings:
1. MAJOR `frontend/src/lib/paperDrafts.js:63-71` (signedByContract), `:90-121` (paperOrdersFor): a paper strategy
   opened in the builder (Drafts Mode) merges a kept duplicate silently: both rows sum per contract_id into one `add`
   order (held 1 lot + Keep separate 1 lot = one order of 1 lot), so the server's duplicate check
   (`routes/paper.py:1021`), which sees only the posted batch, never fires. ADR-319 (3) "never merged silently" fails on
   this paper entry path. Add to Paper is hidden in Drafts Mode (`StrategyBuilderPage.vue:989`). Class: yes.
2. MAJOR `StrategyBuilderPage.vue:723-750` (editLeg, moveLeg) with `backend/ofo_app/routes/leg_edit.py`: the strike
   stepper is the known gap, and the same `/strategies/leg-edit` call also carries Shift, Width and Hedge
   (RELATIVE_CONTROLS `legEdit.js:50`; MOVES `leg_edit.py:118`). Each can land a leg on a held contract with the same
   action; no browser door call and no server duplicate check (`_check_landing` checks tradability only). Class: yes.
3. MINOR `StrategyBuilderPage.vue:130-153` (prepareApproach): adjustment apply sets the server's after-legs with no
   door; a duplicate in a plan-only draft is refused later by the server; in Drafts Mode it merges as finding 1.
   ADR-319 (1) does not list adjustment apply. Class: yes.
4. MINOR `StrategyBuilderPage.vue:100-118, 616`: a draft link, saved strategy or ready-made template replaces the list
   without asking; old duplicates show the LegList row warning (`LegList.vue:253`) and are refused at Add to Paper.
   Chain Add Selected cannot create a same-action duplicate. Class: no.
5. MINOR `LegList.vue:85`: the row warning is hand-copied text, not the served sentence (the server names the contract
   and numbers legs over posted non-exit orders). Class: no.
6. MINOR `legDoor.js:20-28`: incoming legs are not compared with each other; the picker does not produce that today.

Holds: through the door: picker and edit-form save (`LegPicker.vue:529`, strike and expiry change in the form), Done
(`resolveDuplicates`, :586), the Buy/Sell button (:652). One server entry for paper orders, POST
/paper/strategies/{id}/orders (`paper.py:1036`, check at 1056); every frontend caller uses it; the refusal carries the
gate's sentence. aa6ea9fb: behaviour unchanged.

Runs: `npx vitest run tests/leg-duplicate-d60.test.js` 14 passed; `pytest tests -k "closure or order_path or
duplicate_leg"` 15 passed; `pytest tests/execution/test_validation.py tests/errors/test_template_pins.py -k duplicate`
2 passed; probe of `paper_duplicate_leg`: same-side repeat refused, buy and sell not, futures repeat refused.

Covers the class: no (the leg-edit family and the Drafts Mode merge).

## A4 review 4 (2026-11-24): gate commits 8b3b21d7, aa6ea9fb, ef1b1093

Reviewer: fresh-context helper, read-only. Required: behaviour unchanged; the approved line still reads exactly as
ADR-317 gives it. Verdict: PASS (no CRITICAL, no MAJOR).

ADR-317 sentence (`spec/decisions/ADR-317.md:15`): "Not saved: the live price is already at or beyond this level, so
this exit would close the trade straight away. To close now, use Exit." Shipped copies: "Not saved: " +
`render("paper_trigger_already_crossed").what_happened` (`templates.py:1043`, `PaperStops.vue:44`), compared with `==`
in Python: match; `frontend/tests/paper-stops.test.js:130`: match; `tests_app/test_paper_triggers_routes.py:509`
`CE_SENTENCE`: match (read by eye); `template_pins.json`: hash only. No broker name in either crossed-level sentence.
The lower-case pin of ef1b1093 matches the ADR, where the sentence follows "Not saved: ".

aa6ea9fb: `safety._key is duplicate_leg.contract_key`; `duplicate_leg_failure` builds the same CheckFailure as before;
`paper_duplicate_leg` is identical; no importer of the old `safety.paper_duplicate_leg` remains. No check lost.

Findings:
1. MINOR `PaperStops.vue:44`, `frontend/tests/paper-stops.test.js:100,201`: 8b3b21d7 removed the lower-casing regex, so
   every other refusal after "Not saved: " now keeps its capital ("Not saved: That stop already fired.", also
   paper_trigger_nothing_open and paper_trigger_level_invalid). Compatible with ADR-317 (5) ("Not saved: <that
   reason>"); the tests were flipped to match and the commit message does not say so.
2. MINOR `backend/ofo/errors/templates.py:1043,1049`: the two crossed-level templates are lower-case in the API
   `what_happened`, correct only behind "Not saved: ". Only emitter: `routes/paper.py:1420`, called with saving=true.
3. MINOR `tests/errors/template_pins.json:4286-4293`: the "owner read 2026-11-23" label sits on a new hash; the leg
   sentence ("... this stop would close the leg straight away ...") is still `pending owner read` and is not in ADR-317.

Attacks run and passed: `pytest -k "template or pin"` over tests; tests/errors, tests/execution,
tests/strategy/test_builder_history.py; test_door_names_private, test_kite_http_guard, test_gates_import_no_flags;
vitest paper-stops (21 tests).

Behaviour unchanged: yes for the approved line and the duplicate-leg check; no for the first letter of other refusals
(finding 1, MINOR).

## A5 review (2026-11-24): D-60 strike stepper and leg-edit family, commits ee18a64 and e62bb43

Reviewer: fresh-context helper, read-only, code read; the four named test files 44 of 44. Class: every way a leg is
added or moved in the builder, and every paper entry with a kept duplicate (ADR-319).

Findings:
1. MINOR `StrategyBuilderPage.vue` `askMovedDuplicates` (~740): moved legs are checked against held legs only, not
   against each other; Width or Shift moving two same-action legs onto one contract (Width collapsed to zero) makes a
   silent duplicate row. Class: moved against moved.
2. MAJOR `StrategyBuilderPage.vue` `askDuplicate` / `dupAsk` (~729-736): a newer edit while the question is open
   leaves the old question on screen (or overwrites it); the old promise never settles, so the first `sendEdit` hangs
   and its `finally` (`endMove`, `guard.settle`) never runs; answering the stale dialog is silently dropped
   (`isNewest` false), so Increase does nothing. Fix: settle a pending ask as Cancel when a new edit starts.
3. MINOR same function: moved-leg detection compares `landed[i]` with `baseLegs[i]` by index; a Hedge inserting a leg
   mid-list would raise a false question (not a missed one). Check where Hedge places its leg.
4. MINOR Increase after a move updates `lots` only, not `base_lots`; a later relative control may undo it. Not checked.

Holds: opposite action on one contract asks nothing; Cancel leaves legs, controls and shift total untouched; Increase
uses the picker's lots limit and wording; the page dialog reuses `DUP_QUESTION` and `admitLegs` from `legDoor.js` (only
button labels repeated); Drafts Mode skips zero-lot rows, nets buy and sell pairs by action, sends a same-action
duplicate as separate adds; `_refuse_duplicate_legs` in `paper.py` refuses them with the gate sentence.

Covers the class: mostly yes (gaps: findings 1 and 2).

## A6 item 3 review (2026-11-24): D-05 Not saved line and empty-level hint, commits 6b257fd and d0569fe

Reviewer: fresh-context helper, read-only. `paper-stops.test.js` + `paper-strategies.test.js` 44/44. Verdict: REVISE.

Findings:
1. MAJOR `PaperStops.vue:72`, `PaperStrategies.vue:237`: `goodReads` moves when a refresh reply lands, with no link to
   when that refresh started. A refresh starts, Save fails ("Not saved"), the earlier refresh then succeeds: the line is
   cleared although no refresh began after the failure. Fix: clear only on a good refresh that STARTED after the
   failure (a "refresh started" counter stamped at the failure). Class: a clear signal not ordered against the event
   it clears.
2. MAJOR `PaperStops.vue:125`: `v-if="ceReason && !saved"` hides every reason beside "Saved", not only "Enter at least
   one level": after "Saved: exit above 24500", typing 24500.03 hides "price must be a multiple of 0.05" and Save is
   disabled with nothing saying why. Fix: hide only the at-least-one-level case; the price reason always shows.
3. MINOR same line: a leg-stop "Saved"/"Kept" line also hides the exit hint (intended; covered by finding 2's fix).

Clean: the disabled Save rule is unchanged; leg stops, mixed saves and Already set untouched; no clearing mid-call; the
refresh error banner and `stale` do not unmount PaperStops; a failed or unreadable refresh does not move `goodReads`.

Covers the class: no (findings 1 and 2).

## A5 round 2 review (2026-11-24): D-60 commits 27c60cf and 2acaf77

Reviewer: fresh-context helper, read-only; `leg-step-duplicate-d60.test.js` + `leg-duplicate-d60.test.js` 27/27.
Verdict: covers the class: no. D-60 PARKED after two rounds (common rules, section 3 step 8).

Findings:
1. MAJOR `StrategyBuilderPage.vue:~801` with `legDoor.js:25`: after "Increase quantity" the folded leg gets
   `lots = a + b` but `base_lots` is unchanged; `backend/ofo/strategy/leg_edit.py:253` `apply_multiplier` computes
   `lots = base_lots * multiplier`, so a later Lots/Multiplier edit drops the increase (BUY 1 + moved BUY 1, Increase:
   lots 2, base 1; multiplier x1: lots 1). Shift, Width and Hedge pass lots through and are safe. The fold is in the
   shared door, so the picker's Increase has the same gap. Class: a derived field not updated with its source.
2. MAJOR `StrategyBuilderPage.vue:718`: when clicks net to zero (+1 then -1), `moveLeg` calls
   `guard.cancel('leg-edit')` and `endMove` but not `answerDuplicate('cancel')`; the open question stays on screen and
   answers nothing (`isNewest` false). Same class as the round-2 target (one live question per newest move).
3. MINOR: `landed` is computed before the await on the question; after the answer, `legs.value = landed` overwrites any
   change made while the dialog was open (not confirmed that anything can change legs then).

Holds: rapid triple step (the old question is cancelled, the old `finally` runs); step, Cancel, step; Escape and
backdrop map to Cancel; Width collapse checked moved against moved; a numbers reload never touches the question.

Next step for D-60 (parked): (a) in `moveLeg`'s net-zero branch settle the open question as Cancel (one helper shared
with `sendEdit`); (b) in `legDoor.js` Increase, raise `base_lots` with `lots` (test: Increase then multiplier x1 keeps
the total); (c) recheck `landed` against the current legs after the await.

## A6 item 3 round 2 review (2026-11-24): D-05 commits 3f66dc5 and e40a6c2

Reviewer: fresh-context helper, read-only; paper-stops 27 + paper-strategies 19 = 46/46. Covers the class: yes.

"Reads never overlap" holds: `usePaperRefresh.js:19` refresh() returns while `reading` is set; the timer, the Refresh
button, mount and refreshNow() all pass through it; a queued read starts in `finally` after show(). So
`goodReadStart = readsStarted` inside show() is that read's own number.

Findings:
1. MINOR `PaperStrategies.vue:240,255`: the no-overlap guarantee lives in another file and is stated only in a comment;
   structural option: capture `const n = ++readsStarted.value` in read() and hand it to show(). Not a current defect.
2. MINOR `PaperStops.vue:60-68,77`: a cancel() failure stamps the read count but its error does not start "Not saved",
   so a good refresh never clears it (as before this change; not a Save, outside the owner decision).

Checked: a failure while a read is in flight keeps the line (only the next read clears it); a failed or unreadable
refresh never moves `goodReadStart`; leg-stop and keep failures stamp the same way; typed levels survive a failed
save; a remount resets error and stamp; beside Saved only the at-least-one-level reason hides.

## D-04 round 2 review (2026-11-24): commits cea53cf, f135690, and test changes 0802084, 38debbf

Reviewer: fresh-context helper, read-only. `pytest -q tests -k "guard or entry_type or adjustment"` 1918 passed.
Verdict: covers the class: no. D-04 PARKED after two rounds (common rules, section 3 step 8).

Findings:
1. MAJOR `backend/ofo_app/background.py:1882`, `routes/adjustment_check.py:442`, `routes/adjustment_plan.py:348`,
   `routes/playbooks.py:482`: these four callers still pass the live spot to `check.entry_type`, while the server limit
   (`paper_limit.py:42`) and now the offer path (`routes/adjustment.py:591`) pass None. `strategy_type` uses spot as the
   reference level and falls back to the middle of the strikes only without it, so a shape near a type boundary can
   read playbook A on the check route and the worker and playbook B (or the current-shape fallback) on the server.
   Same class as the A4 finding. Next step: one shared spot-free entry-type call used by all six callers, plus a test
   that offer, check, worker and server agree for a basket at the plan maximum.
2. No regression for other guards: spot is used only to classify; guards are read from the playbook body.
3. All `read_guards`/`guards_of` call sites are on the new path.
4. Fallback verified on the offer path (same function and arguments as the server). MINOR: the offer's `listed` comes
   from `check.listed_of(ctx)`, the server's from its own argument; same source not confirmed.
5. 0802084 OK: ADR-318 (5); the test's purpose (why text naming both records) is unchanged. The add-refused case must
   be covered elsewhere (it is: `tests_app/test_d04_*` and the paper limit tests).
6. 38debbf OK: REQ-159 AC-6 buys first. MINOR: the expectation copies the production sort; a fixed expected price list
   would be stronger.

## A6 items 1 and 2 and the D-05 token review (2026-11-24): c88b8aa, 18158ae + 2a2532f, 7aac4d5 + 23b07db

Reviewer: fresh-context helper, read-only. vitest paper-stops, paper-strategies, paper-armed-exits 49 passed;
`pytest -k "paper_monitor or buys_first"` (non-DB) 1 passed. No CRITICAL, no MAJOR.

Findings:
1. MINOR `PaperConfirmDialog.vue` (askArmedExits): "Could not check" is set only when the request throws or `lines` is
   not an array; an array with non-string or empty entries is filtered silently (partial read treated as complete).
2. MINOR `PaperStops.vue` (watch on `goodReadToken`): a save failed while read R1 is in flight is kept when R1
   succeeds (stamp equals R1): conservative and intended.

c88b8aa: each read creates a fresh token that travels with its own answer; a failed refresh never sets the good
token; a remount starts clean; no reader of the old counter props remains. Covers the class: yes.
D-03: "Could not check" and an empty readable list are distinct; Confirm gating unchanged; another user's or a missing
strategy is refused 404 by `/armed-exits` (`_load_strategy`), asserted by the new DB test. Covers the class: mostly
(finding 1).
D-02: the alert reads the stored book filtered by trigger id; `claim_fire` fires a trigger once, each in its own
transaction, so two stop-outs list only their own legs; closed legs are not targets; sibling places (Orderbook, Alerts
History) read stored rows in id order. Covers the class: yes.

## D-60 rounds 3 and 4 (2026-11-24): commits 48bd943 + aa23745, 02fa66d + d886506

Owner direction 24 Nov ("take your call"): the two-round park rule clashed with the Part A Definition of Done ("nothing
else open" on the seven), so two further narrow rounds were run, each reviewed by a fresh-context helper.

Round 3 review (aa23745): (a) a net-zero step closes the question through one shared `cancelDuplicate`: yes. (b)
Increase raises `base_lots` with `lots` (`legDoor.js:27-30`; held base 1 at x2 + incoming base 1 at x2 = lots 4, base 2;
apply_multiplier 2 x 2 = 4): yes; MINOR: one side without `base_lots` at a multiplier other than 1 mixes units (no path
found that makes such a leg). Two MAJOR: an identity check dropped a real answer on an equal-content reassignment;
route watches, Undo and discardPending replaced legs without closing the question.

Round 4 review (d886506): `cancelDuplicate()` is the first line of `setLegs`, which every replacement except
`nameLegsFrom` (278) and the reply itself passes; `onBeforeUnmount` cancels; the answer check compares content
(`sameLegs`: id, instrument_id, action, lots). The apply path never calls `setLegs`, so an answer cannot cancel itself.
Tests 36/36.
1. Deferred (outside D-60, older than Part A): a `setLegs` while a leg-edit request is still in flight (no question yet)
   does not cancel that request, so its reply lands on the new legs. The code before Part A (01055d4, `sendEdit`
   `legs.value = applyEditReply(legs.value, reply)`) had the same behaviour. One-line fix: `guard.cancel('leg-edit')` in
   `setLegs`. Class: stale reply applied after a legs replacement.
2. MINOR: after `nameLegsFrom` fills names while the question is open, the move writes back legs built before the
   names (the names are re-filled on the next reply).
3. MINOR: an equal-content `setLegs` emit still closes the question (a replacement is treated as a replacement).

Covers the D-60 class (one live duplicate question per move; legs never merged silently): yes.

## D-04 round 3 review (2026-11-24): commits 50d875b, 619dfd9, ba2c825

Owner direction 24 Nov ("take your call"): one more round beyond the two-round rule (see review 11 header). Reviewer:
fresh-context helper, read-only. `tests/test_spot_clock_scan.py` 19 passed; `pytest tests -k "guard or entry_type or
adjustment"` 1918 passed. All 8 `entry_type` call sites now pass exactly (tracked, listed); no spot-taking caller
remains in backend/.

Findings and the orchestrator's classification:
1. `routes/tracking.py:437-447` `_playbook_type` and `routes/outcome.py:974` call `type_of(legs, live_spot, gap)`.
   Classified NOT the D-04 class: tracking's call only decides whether the strategy has a playbook, so the generic
   0.5% detection is hidden (F-71 / GC-ADJ2 1C); it sets no plan maximum and no rules (ADR-318 point 4). outcome's call
   classifies a planned, not yet entered trade, where the current shape is the entry shape. Deferred MINOR: after a
   reduce, tracking reads the current shape for that hide decision.
2. MINOR `adjustment_plan.py:344-348`: the `judge_spot` read is now unused as data and kept only for the spot-clock
   gate (gate edits are out of scope in this run); it was read there before this round too, so the route's failure
   modes are unchanged. Deferred: drop the scan's plan-route entry and then the read (owner decision).
3. MINOR `adjustment_check.py:157-166`: classification without spot uses the strike midpoint, with a gap probe when that
   fails; this is the stated D-04 intent and is pinned by tests.
4. MINOR tests: the check route and the worker are covered by an AST arity test, not behaviourally.

Covers the D-04 class (every path reads the plan maximum and rules from the entry shape the same way): yes.
