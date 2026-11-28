STATUS 01:00 | SAFE TO CLOSE | wave 1 (8425feea) merged, prepush TOTAL PASS 1054.4s on this head (an earlier run failed 2 RA2 tests only for want of lupa in this container; installed, green) | all F2 items done at code level, none walked in a browser | KEEP F2's AdjustPlanSheet.vue and PlanEntry.vue | open for the owner: questions (a), (b) | blocker: none

# RESULTS Lane F2 (frontend plan screens, Review wording, Execute page), branch fix/r3-frontend-f2-1128

Base: origin/integration/weekend-r3-1129 + Lane FJ2 push 68a46dd62 merged (its version wins on a clash in its files).

| Item | State | Red line (first) | Green |
|---|---|---|---|
| 2 I-208 Stop / Stop (Rs) clash | Fixed, not tested in a browser | plan-sheet-levels-differ-f2-1128: 2 of 4 red (Stop 9 + Stop (Rs) 500 sent only `stop_rupees`; Target 30 + Target (Rs) 900 sent only the last box) | 4/4; adjust-plan 30, plan-rupee-levels green |
| 1 I-197 stop / target figure in the Plan block | Fixed, not tested in a browser; raw body of strategy 209 not seen (Lane W1 / TG2 body not on origin): built on the server's PlanOut shape | plan-entry-levels-f2-1128: 6 of 6 red | 6/6; 20 files / 206 tests that touch PlanEntry or adjustPlan green |
| 3 I-41 builder money figures | Tests only (pins, green at once), no code changed | builder-money-figures-f2-1128 | 7/7; re-buy rows stay pinned by panel-rows-closed-b6 (8/8) |
| 4 I-182 Execute page lock | Fixed, not tested in a browser (merged with FJ2's batch 1, 4201d3af2, for its lock) | execute-lock-f2-1128: 6 of 7 red on the old page (the 7th, a reply or a refusal frees the press, passes by design) | 8 + 5 review cases; two older tests (group-a-r3-one-key-r3-fj) re-expressed under the lock; 304 tests of 18 files that touch the page or unknownLocks green |
| 5 I-195 one stop wording | No frontend change possible, see For the owner lane | | |
| D-TG2-1 (T2-19) reset markers | Fixed, not tested in a browser (batch 2) | plan-reset-markers-f2-1128: 4 of 5 red (the line read "Switched on again: triggers.T-01") | 5/5; plan-reset-p8 updated (it pinned the raw key) 7/7 |
| W-29 step 57 closed trade: no Plan watch box | Fixed, not tested in a browser (batch 2) | plan-watch-closed-f2-1128: 2 of 3 red on the old component | 3/3; four older tests that pinned the "closed; nothing is watched" sentence now pin no box |
| W-30 stop figure with the reason | Plan block done (batch 2); Positions Plan watch row needs the server | plan-entry-levels-f2-1128 W-30 case red | 8/8 |

## Handoff branch (FJ2, 4297f7065) compared
- plan-pair-stale-fj2-1128 (stop and target, % then Rs with no figure): FJ2 clears the % box and Save sends only Rs, with no message. Mine sends both when the user typed both (the server's "show different values" sentence, the walker's expectation). I added FJ2's case to plan-sheet-levels-differ-f2-1128 (a box the SERVER filled earlier is cleared when the next typed box gets no figure): 2 red, then green with a "pair agreed" reset of the typed flags. Both fixes pass together in my version.
- plan-card-levels-fj2-1128 (PlanEntry): FJ2 prints the server's words ("Target: 50.00 % of max profit", "Target: not set"); mine prints "Target: 50 % (Rs 1950.00)" and "No target is set for this trade." The coordinator chose mine: its wording is in "New wording for the owner to read". FJ2's words-first form is the alternative if the owner prefers the server's own sentence.

## Item 4 (I-182): how and the Opus review
- The page keeps an add-lock entry `execute:<strategyId>` in the one lock store (lib/unknownLocks.js, FJ2's version): written before the request goes out (out:true), dropped by a usable reply or a 4xx refusal, re-written as unknown (the client gave up) for no answer, 5xx, 408/429, a cancelled request or a reply that is not a usable basket. While it stands both Prepare buttons are off and a press sends nothing (the store is read at press time); a reload and a second tab hold it. It is released only by a good read of the saved strategy SENT after the 130 s window by the monotonic rule (decideLock with an empty book: "not stored"), never by a failed read or a wall clock jump. The request key stays, so a repeat press after the release is the same request. The server also refuses a repeat (Lane B2's per-strategy block): this page lock is the second line.
- Opus review (reviewer, Opus, 22 min): REVISE, no money-path finding. Fixed: F1 (two older tests pinned the old repeat press), F2 (lock id read at answer time: fixed at the press), F3 (the unknown sentence showed during a normal request), F4 (unusable reply dropped the key), F5 (sentNow for the read time), F6 (store read at press time), F7 (timer after close). Not fixed, open: F8 SaveDraftBar.vue polls every id of the add-lock store including `execute:<id>` (a 422 per 5 s; it cannot release a lock early) - Lane F1's file: skip ids that are not numbers; F9 a 585 answer ("a basket was already prepared") is classed a refusal by tracking.js:95 so it frees the lock and the key (the server's open-plan refusal holds); F10 the sentence says "a usable answer" but the read cannot see a prepared basket; F11 without a monotonic clock the wall clock decides (documented fallback).
- Behaviour beyond "nothing is sent, with one plain sentence" is the owner's: (a) below.

## Mapping of the removed plan-card-levels-fj2-1128 cases (the build lane removed that file; none is lost)
The file held four `it` cases (the coordinator counted three): each is covered by a test of mine in `frontend/tests/plan-entry-levels-f2-1128.test.js`, against my implementation. One behaviour differs by design (the coordinator kept my wording): FJ2 printed the server's words ("Target: 50.00 % of max profit"); mine prints the figures with units ("Target: 50 % (Rs 1950.00)").
| FJ2 case | Behaviour | Covered by (my test) |
|---|---|---|
| plan with both: "Target: 50.00 % of max profit", "Stop: 25.00 % of max loss" | the plan's target and stop are shown with units | 'check paused (market closed): the plan's own stop and target with units' (figures in percent and Rs, not the server's words) |
| figure but no words: "Target: 50.00 %" | percent figure with its unit | 'a plan with a percent and no rupee figure ...' (added 28 Nov 23:30: "Target: 50.00 %", "Stop: 25.00 %") |
| no target and no stop: "not set" | the plain fact that none is set, never blank or 0 | 'no target set: the reason, not silence' and 'no stop at all: the reason' ("No target is set for this trade.", "No stop is set for this trade.") |
| no plan at all: no lines, the "No plan" line stands | nothing extra without a plan | 'check still loading or failed ...; no plan: nothing' (no `plan-entry-stop`, no `plan-entry-target`) |

## Causes
- I-208: `saveBody` sends only the box last edited of a pair. When the server's levels read cannot fill the other box (no base to judge: returns null, the sheet leaves the other box as typed), the user sees two independent figures but the server never receives both, so its refusal "Stop and Stop (Rs) show different values." (templates 710/711, routes/adjustment_plan.py:481) never fires. Fix: the form now remembers which boxes the user typed (`targetTyped`, `stopTyped`; a box the server filled in is not "typed"); Save sends both when both were typed and the server names the clash. Unchanged: a box the server filled is never sent beside the typed one (the stored rupee-versus-percent source stays as before, F4).
- I-197: the Plan block printed only the check's `limits` rows. With the check paused (market closed), failed, or without a row for a level, no stop or target figure showed. Now the plan's own levels (percent and rupees, the server's strings) print for any level the check's lines do not carry, or the reason none is set.

## For the owner lane
- I-195 (backend): the stop sentence "If this stop fires, max loss becomes Rs X (now Rs Y)." is server text (backend/ofo/errors/explanations.py:2126 `paper_leg_stop_widens_loss`, chosen in backend/ofo_app/routes/paper.py:1728 `_stop_line(before, after)` for a stop that is not a bare-leg case). Real case 28 Nov TG W-29: a stop on the sold 24300 CE at 170 printed it beside the three decision-55 lines for bare legs. The frontend (PaperStops.vue) prints the server's lines as sent (test paper-stops-one-wording-r3-fj), so one wording needs the server to build the decision-55 three lines for this case too. Not editable here.
- W-30 (Lane RA2), backend/ofo_app/routes/plan_watch.py lines 164-169: `if lim.state == "not_checked" or fires is None:` makes the row `not_computable` with NO `fires_at`, even when `_fires_at(kind, lim, state)` is known (the stored stop, Rs 731.25 on weekly trade #1, 45 %). Send `fires=fires` on that row (and `reason`), so the Positions and builder Plan watch rows print the stop's figure beside "not being checked". The Plan watch component already prints `fires_at` whatever the row's state is; no frontend change is needed once the server sends it.
- Plan read: `plan.target_rupees` / `plan.stop_rupees` are used for I-197 (already in PlanOut); nothing needed.

## Decided for the owner
- I-208: both boxes are sent only when BOTH were typed by the user and the server filled neither; otherwise the old "last edited box only" rule stands. Fail closed: the server judges, nothing is saved silently.
- I-197: a level with no value prints "No stop is set for this trade." / "No target is set for this trade." rather than nothing. The plan's levels show even when the check is failed or paused (they are saved facts, not live readings); while the check is still loading nothing extra shows.

- D-TG2-1: a reset marker reads the trigger's label from the trade's own rules (GET .../adjustment-plan/rules, one extra read after a reset that put something back); an unknown key or an unreadable read says "a condition of the playbook". No "changed" marker beyond the server's `put_back` list is added.
- W-29 step 57: ADR-330 (57) (no Plan watch box on a closed trade) is taken over the earlier UX-A06 calm sentence ("This trade is closed; nothing is watched."), which came from a note by another session. The box also goes from the settled rows on Positions (PaperStrategies.vue embeds PlanWatch; no edit there was needed). A trade that opens again shows the box again.
- W-30 (Plan block): the stored stop and target figures print beside a "not being checked" reason line (two lines: the server's reason, then "Stop: 45 % (Rs 731.25)").

## Question for the owner
- (b) Does the table total follow the "Add booked P&L" switch? TD O-4 real case ADJ-13 strategy 3, booked +962: tiles change (ON +4,823.72, OFF +3,967) while the table total reads -2,332.79 in both states. Recommendation: leave the total always including booked (the P&L table is the trade's truth), and say so in one line under the switch. Not built.
- (a) Execute page after an unknown outcome beyond fail-closed: the lock lifts by itself after a good read past 130 s. Should the user be able to say "I checked Kite's Orderbook" and lift it sooner, and what should the sentence promise? Real case: a prepare that times out on the Execute page of strategy 1. Recommendation: no early release by the user for a basket (nothing is ordered until the Kite click); the sentence as built.

## New wording for the owner to read
- Execute page: "The last request to prepare orders may have been prepared, but no usable answer came. Preparing again stays off until this page has waited and checked again."
- "a condition of the playbook" (the reset marker fallback, AdjustPlanSheet)
- "No stop is set for this trade." (PlanEntry)
- "No target is set for this trade." (PlanEntry)
- Plan block lines: "Stop: 15.38 % (Rs 400.00)", "Target: 50 % (Rs 1950.00)", "Stop (Rs): Rs 400.00" (the labels are the server's plan-sheet labels; the figures the server's)

## Found, not assigned (owner's order of 28 Nov 23:35: written here, not fixed, not handed on)
- frontend/src/components/strategy/SaveDraftBar.vue:379-387, 400-402 (Lane F1's file): the save bar's add-lock poll goes through EVERY id of the add-lock store, including `execute:<id>`, and reads `/paper/strategies/execute:1` every 5 s (a 422 each time; the timer never stops while any id exists). It cannot release a lock early. Evidence: Opus review finding 8 of item 4 (read from the code, not run).
- frontend/src/lib/tracking.js:95 `paperPostOutcome`: a 585 answer ("A basket was already prepared for this press", 409, templates.py:1097) is classed REFUSED, so the Execute page frees its lock and key on it; the server's open-plan refusal holds. Evidence: Opus review finding 9, run: unknown -> release -> repeat gets 585 -> third press sends a new key.
- backend/ofo_app/routes/plan_watch.py:164-169: `lim.state == "not_checked"` rows carry no `fires_at` though `_fires_at` is known (W-30, Positions Plan watch row). Routed by the coordinator to Lane B3 already.
- Without a monotonic clock (`performance.now` absent) the wall clock decides the 130 s rule (documented fallback, unknownLocks.js:19): Opus finding 11.

## Not done
- Item 5 (server wording). I-113 is Lane F3's.

## Tasks
| task | model | minutes |
|---|---|---|
| items 1, 2, 3 | Sonnet (main session, no helper used) | 50 |

## Friction (for the coordinator to enter in docs/process/friction-log.md; not in my May edit list)
| Date | Who | What happened | How often / long | Cost | Class |
|---|---|---|---|---|---|
| 2026-11-28 | lane F2 | send_message to "@parent" refused every time (elevated_session_untrusted_device) until the owner confirms trust; the STATUS line on the pushed branch was the only report channel, and the coordinator's later messages reached me but my replies could not reach it | 4 sends | 4 failed calls | missing tool |
| 2026-11-28 | lane F2 | prepush stopped at once: ruff, fastapi, sqlalchemy not installed in a fresh cloud container; fixed by pip install -r requirements-dev.txt -r requirements-app.txt (not in the lane brief or runbook) | 1 run | 3 min | missing tool |
| 2026-11-28 | lane F2 | The commit gate hook refused git commit/push chained after a pipe or a python heredoc in the same call, so every commit became two or three calls | 5 times | about 10 calls | unclear rule |
| 2026-11-28 | lane F2 | A hook asks to push 60+ unpushed commits while the brief allows two pushes; the count is mostly the merged integration branch | 3 times | 3 turns | unclear rule |

## Done / not done (final)
Done (Fixed, not tested in a browser): I-208 (+ FJ2's stale-box case), I-197 and its re-fix (W-30: figure first, reason on the same line), I-41 pins (tests only), D-TG2-1, W-29 step 57, W-30 Plan block, I-182 Execute page lock (Opus-reviewed), the four-case mapping of plan-card-levels-fj2-1128.
Not done: I-195 (server wording, backend), W-30 Positions Plan watch row (Lane B3 routed by the coordinator), the two questions for the owner, any browser walk of these screens, Opus findings F9 to F11 (listed under Found, not assigned).
Friction rows for the coordinator: see the Friction section.

SAFE TO CLOSE (head: the push of this commit; what is left: the Not done list above)

