# Meta review after row 9 (builder sequence) - review the reviews, rows 7-9

You are a fresh reviewer (you built and verified nothing in this sequence). Read-only: edit no file. Report back; the
orchestrator applies the changes.

Read: `docs/process/row-review.md` (standing rules R1-R17, effect check, expected-vs-actual table, the log - rows 7, 8
and 9 and the meta review after row 6 are new since the last meta review); `docs/process/builder-brief.md`; the row
briefs in `docs/process/builder-sequence-briefs/` for rows 8 and 9 (`row-08-*`, `row-09*`, `verify-row-08*`,
`verify-row-09*`); `git log --format='%h %ad %s' --date=format:'%d %H:%M' 1f76a640..HEAD` in the worktree
`D:\Abhay\Ventures\OptionsForOptions2-builder-reqs` for the real times.

Answer, with numbers:
1. Is waste shrinking? Rounds per row, follow-up dispatches per row, minutes and tokens vs expected (rows 4-9).
2. Which standing rules were broken AFTER they were written, how often, and by whom (orchestrator / builder /
   verifier)? In particular the Budget hard stop (builders over their call budget), R1 (attack list), R2/R13 (stale or
   unrun tests), R14 (keys from the call), "step 1 is the core proof failing first", and lost mutation evidence.
3. The pattern in row 9: four parts, and EVERY part needed at least one follow-up for tests the builder did not finish
   (unkilled mutants, lost mutation output, unproven guards). What is the smallest change that makes a builder finish
   its own proof - a machine check, a brief change, a different split, or a different model for the mutation step?
   Name one and say how it would be measured.
4. The overnight stall (R17): is the rule enough as written? Is there a cheaper machine check?
5. Did any review record a number or time that does not match the commits (as the meta review after row 6 found)?

Keep it under 450 words. No code. Each proposed change says: what, where it lands, whether it adds a check or loosens
one (a loosening goes to an independent reviewer and the owner, never applied directly).
Budget: 15 min wall-clock, 25 tool calls
Report: evidence-table
