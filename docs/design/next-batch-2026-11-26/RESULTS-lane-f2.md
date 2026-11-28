STATUS 19:10 | items 1, 2, 3: Fixed, not tested in a browser (batch 1 check pending) | item 4 waits for Lane F1's add lock (not on origin at 19:00) | item 5: no frontend text to change (server wording) | next push batch 1 after the check | blocker: link to coordinator refused (elevated_session_untrusted_device), so this STATUS line is the report

# RESULTS Lane F2 (frontend plan screens, Review wording, Execute page), branch fix/r3-frontend-f2-1128

Base: origin/integration/weekend-r3-1129 + Lane FJ2 push 68a46dd62 merged (its version wins on a clash in its files).

| Item | State | Red line (first) | Green |
|---|---|---|---|
| 2 I-208 Stop / Stop (Rs) clash | Fixed, not tested in a browser | plan-sheet-levels-differ-f2-1128: 2 of 4 red (Stop 9 + Stop (Rs) 500 sent only `stop_rupees`; Target 30 + Target (Rs) 900 sent only the last box) | 4/4; adjust-plan 30, plan-rupee-levels green |
| 1 I-197 stop / target figure in the Plan block | Fixed, not tested in a browser; raw body of strategy 209 not seen (Lane W1 / TG2 body not on origin): built on the server's PlanOut shape | plan-entry-levels-f2-1128: 6 of 6 red | 6/6; 20 files / 206 tests that touch PlanEntry or adjustPlan green |
| 3 I-41 builder money figures | Tests only (pins, green at once), no code changed | builder-money-figures-f2-1128 | 7/7; re-buy rows stay pinned by panel-rows-closed-b6 (8/8) |
| 4 I-182 Execute page lock | NOT STARTED: waits for Lane F1's add lock (decideLock through the one lock rule) on origin/fix/r3-frontend-2-1128 (head still 68a46dd62 at 19:00) | | |
| 5 I-195 one stop wording | No frontend change possible, see For the owner lane | | |

## Causes
- I-208: `saveBody` sends only the box last edited of a pair. When the server's levels read cannot fill the other box (no base to judge: returns null, the sheet leaves the other box as typed), the user sees two independent figures but the server never receives both, so its refusal "Stop and Stop (Rs) show different values." (templates 710/711, routes/adjustment_plan.py:481) never fires. Fix: the form now remembers which boxes the user typed (`targetTyped`, `stopTyped`; a box the server filled in is not "typed"); Save sends both when both were typed and the server names the clash. Unchanged: a box the server filled is never sent beside the typed one (the stored rupee-versus-percent source stays as before, F4).
- I-197: the Plan block printed only the check's `limits` rows. With the check paused (market closed), failed, or without a row for a level, no stop or target figure showed. Now the plan's own levels (percent and rupees, the server's strings) print for any level the check's lines do not carry, or the reason none is set.

## For the owner lane
- I-195 (backend): the stop sentence "If this stop fires, max loss becomes Rs X (now Rs Y)." is server text (backend/ofo/errors/explanations.py:2126 `paper_leg_stop_widens_loss`, chosen in backend/ofo_app/routes/paper.py:1728 `_stop_line(before, after)` for a stop that is not a bare-leg case). Real case 28 Nov TG W-29: a stop on the sold 24300 CE at 170 printed it beside the three decision-55 lines for bare legs. The frontend (PaperStops.vue) prints the server's lines as sent (test paper-stops-one-wording-r3-fj), so one wording needs the server to build the decision-55 three lines for this case too. Not editable here.
- Plan read: `plan.target_rupees` / `plan.stop_rupees` are used for I-197 (already in PlanOut); nothing needed.

## Decided for the owner
- I-208: both boxes are sent only when BOTH were typed by the user and the server filled neither; otherwise the old "last edited box only" rule stands. Fail closed: the server judges, nothing is saved silently.
- I-197: a level with no value prints "No stop is set for this trade." / "No target is set for this trade." rather than nothing. The plan's levels show even when the check is failed or paused (they are saved facts, not live readings); while the check is still loading nothing extra shows.

## Question for the owner
- (b) Does the table total follow the "Add booked P&L" switch? TD O-4 real case ADJ-13 strategy 3, booked +962: tiles change (ON +4,823.72, OFF +3,967) while the table total reads -2,332.79 in both states. Recommendation: leave the total always including booked (the P&L table is the trade's truth), and say so in one line under the switch. Not built.
- (a) Execute page after an unknown outcome beyond fail-closed (release wording, "I checked the Orderbook"): item 4 not started.

## New wording for the owner to read
- "No stop is set for this trade." (PlanEntry)
- "No target is set for this trade." (PlanEntry)
- Plan block lines: "Stop: 15.38 % (Rs 400.00)", "Target: 50 % (Rs 1950.00)", "Stop (Rs): Rs 400.00" (the labels are the server's plan-sheet labels; the figures the server's)

## Not done
- Item 4 (waits for F1). Item 5 (server wording). I-113 is Lane F3's.

## Tasks
| task | model | minutes |
|---|---|---|
| items 1, 2, 3 | Sonnet (main session, no helper used) | 50 |
