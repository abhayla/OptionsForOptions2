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
