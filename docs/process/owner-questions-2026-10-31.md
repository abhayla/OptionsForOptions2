# Owner questions, 2026-10-31

## Q1: GC-ADJ1's "run tree removed with wt-rm.ps1" cannot be done while the work stays off main

Raised by GC-ADJ1 at ~01:50 IST (the question box was refused by the night guard; also asked in chat).
Business call: the contract's Definition of Done and the owner's branch rule conflict; only the owner can waive one.
Spec basis: none: the spec says nothing about worktree removal (searched: worktree, wt-rm, run tree); contract
GC-ADJ1 Definition of Done and its "Found during the run" row 11; global worktree rule R3.

What happened: `wt-rm.ps1` refuses to remove a worktree unless its branch, or the `-MergedSha` given, is on
origin/main ("REFUSED: -MergedSha ... is not on origin/main; nothing removed"). The owner rule keeps all adjustment work
off main, and R3 forbids removing trees any other way. Every other DoD item is met: prepush --full PASS (cb4a1b89),
merged into local feature/adjustments (17d0470f), F-74/75/76 fixed, POP class guarded, handover, memory note.

Options:
1. **Keep the trees; GC-ADJ1 counts as done with this one exception (recommended).** The 5 trees
   (OptionsForOptions2-gcadj1-run, -gcadj1-pop, -gcadj1-spot, -gcadj1-appr, -gcadj1-scen) are merged into
   feature/adjustments and clean; they are removed with wt-rm once the feature reaches main with the owner's approval.
2. Push feature/adjustments to origin (not main) as a backup. Backs the work up but does not let wt-rm remove the trees.
3. Keep GC-ADJ1 open until the feature reaches main.

Recommendation: 1, because nothing is lost by keeping the trees and the other two options either change nothing or
keep the run open for days.

**Answered 2026-10-31 ~02:00 (question tool): option 1, "Keep trees, GC-ADJ1 done".** Recorded as contract row 25.

## GC-ADJ3 scope questions (written 22:31 IST; the night guard blocks the question box after 22:00)

Decision 1 of 5 was answered in the question box at ~21:40: **T-19 uses the cheapest adjustment's cost** (ADR-221).
The rest wait for the owner. Each has a recommendation; nothing is built on them before an answer.

### Q-ADJ3-2: three playbook limits are saved but nothing applies them (finding F-78)
"Hide strikes with open interest below", "Hide strikes whose bid-ask spread is above this % of the mid price" and
"Most debit paid for one roll" are in the editor and in every system playbook, but no code reads them.
Business call: what these settings do for users. Spec basis: REQ-159 AC-6; F-78; catalogue F-12.
1. **Make them work (recommended):** flag a strike that breaks the OI or spread limit in the adjust drawer and Compare
   ("Below your liquidity limit"), and refuse a roll whose debit is above the limit, with the reason. Flag, not hide,
   so nothing disappears without a reason.
2. Tag them "Not applied yet" in the editor until a later contract builds them.
3. Make them work by removing the strikes from the choices entirely.

### Q-ADJ3-3: an adjustment alert on the Live Strategies cards
Today a flag shows only in the builder's tracking panel and the Adjustment opportunities inbox; the mockup shows it on
the strategy card too. Business call: product scope. Spec basis: REQ-162 (inbox), REQ-112, GC-ADJ2 known gaps.
1. **Add it in GC-ADJ3 (recommended):** a small "1 adjustment opportunity" mark on the card, linking to the inbox row.
   About half a day; it is where traders look during market hours.
2. Leave it for a later contract.

### Q-ADJ3-4: the rest of the cost line (catalogue F-04)
The Compare already shows "Charges plus bid-ask cost", credit/debit and premium left. Missing: the charge breakdown
(brokerage, STT, exchange, GST, stamp), the change in max profit, and cost as % of premium left.
Business call: what the Compare shows. Spec basis: REQ-155 AC-3, REQ-156 AC-2; catalogue F-04.
1. **Add "cost as % of premium left" and "change in max profit" as rows, and the charge breakdown as a tap-to-open
   detail under the cost row (recommended).** Keeps the table short; the breakdown is there for whoever wants it.
2. Add all three as full rows.
3. Add only "cost as % of premium left" (the number T-19 acts on).

### Q-ADJ3-5: a playbook with both stop values but no "whichever comes first" rule
The editor lets a user fill "Stop line (% of max loss)" AND "Stop line (% of margin)" and leave the rule empty. Today
the plan sheet and summary then show only the max-loss stop, while the T-06 / T-16 triggers each check their own value.
Business call: what the user's stop means. Spec basis: REQ-159 AC-6; REQ-161 (plan sheet).
1. **Treat both values as "whichever comes first" and show both (recommended):** a user who filled two stops expects
   both to count, and the triggers already behave that way (each fires on its own).
2. The editor refuses to save two stop values without a rule ("Pick how the two stops combine").
3. Keep today's display (max-loss stop only).
