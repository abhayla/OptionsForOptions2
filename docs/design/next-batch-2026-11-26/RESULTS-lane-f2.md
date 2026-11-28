STATUS 19:50 | KEEP F2's version of AdjustPlanSheet.vue and PlanEntry.vue at the build wave (not FJ2's handoff 4297f7065 for those two files) | batch 1 pushed 28c0e7be6; local for batch 2: D-TG2-1, W-29 step 57, W-30 front half, FJ2's stale-box case | item 4 waits for F1's add lock | W-30 Positions row needs Lane RA2 (see For the owner lane) | next push batch 2 | blocker: coordinator link refused (elevated_session_untrusted_device), this line is the report

# RESULTS Lane F2 (frontend plan screens, Review wording, Execute page), branch fix/r3-frontend-f2-1128

Base: origin/integration/weekend-r3-1129 + Lane FJ2 push 68a46dd62 merged (its version wins on a clash in its files).

| Item | State | Red line (first) | Green |
|---|---|---|---|
| 2 I-208 Stop / Stop (Rs) clash | Fixed, not tested in a browser | plan-sheet-levels-differ-f2-1128: 2 of 4 red (Stop 9 + Stop (Rs) 500 sent only `stop_rupees`; Target 30 + Target (Rs) 900 sent only the last box) | 4/4; adjust-plan 30, plan-rupee-levels green |
| 1 I-197 stop / target figure in the Plan block | Fixed, not tested in a browser; raw body of strategy 209 not seen (Lane W1 / TG2 body not on origin): built on the server's PlanOut shape | plan-entry-levels-f2-1128: 6 of 6 red | 6/6; 20 files / 206 tests that touch PlanEntry or adjustPlan green |
| 3 I-41 builder money figures | Tests only (pins, green at once), no code changed | builder-money-figures-f2-1128 | 7/7; re-buy rows stay pinned by panel-rows-closed-b6 (8/8) |
| 4 I-182 Execute page lock | NOT STARTED: waits for Lane F1's add lock (decideLock through the one lock rule) on origin/fix/r3-frontend-2-1128 (head still 68a46dd62 at 18:50) | | |
| 5 I-195 one stop wording | No frontend change possible, see For the owner lane | | |
| D-TG2-1 (T2-19) reset markers | Fixed, not tested in a browser (batch 2) | plan-reset-markers-f2-1128: 4 of 5 red (the line read "Switched on again: triggers.T-01") | 5/5; plan-reset-p8 updated (it pinned the raw key) 7/7 |
| W-29 step 57 closed trade: no Plan watch box | Fixed, not tested in a browser (batch 2) | plan-watch-closed-f2-1128: 2 of 3 red on the old component | 3/3; four older tests that pinned the "closed; nothing is watched" sentence now pin no box |
| W-30 stop figure with the reason | Plan block done (batch 2); Positions Plan watch row needs the server | plan-entry-levels-f2-1128 W-30 case red | 8/8 |

## Handoff branch (FJ2, 4297f7065) compared
- plan-pair-stale-fj2-1128 (stop and target, % then Rs with no figure): FJ2 clears the % box and Save sends only Rs, with no message. Mine sends both when the user typed both (the server's "show different values" sentence, the walker's expectation). I added FJ2's case to plan-sheet-levels-differ-f2-1128 (a box the SERVER filled earlier is cleared when the next typed box gets no figure): 2 red, then green with a "pair agreed" reset of the typed flags. Both fixes pass together in my version.
- plan-card-levels-fj2-1128 (PlanEntry): FJ2 prints the server's words ("Target: 50.00 % of max profit", "Target: not set"); mine prints "Target: 50 % (Rs 1950.00)" and "No target is set for this trade." The coordinator chose mine: its wording is in "New wording for the owner to read". FJ2's words-first form is the alternative if the owner prefers the server's own sentence.

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
- (a) Execute page after an unknown outcome beyond fail-closed (release wording, "I checked the Orderbook"): item 4 not started.

## New wording for the owner to read
- "a condition of the playbook" (the reset marker fallback, AdjustPlanSheet)
- "No stop is set for this trade." (PlanEntry)
- "No target is set for this trade." (PlanEntry)
- Plan block lines: "Stop: 15.38 % (Rs 400.00)", "Target: 50 % (Rs 1950.00)", "Stop (Rs): Rs 400.00" (the labels are the server's plan-sheet labels; the figures the server's)

## Not done
- Item 4 (waits for F1). Item 5 (server wording). I-113 is Lane F3's.

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
