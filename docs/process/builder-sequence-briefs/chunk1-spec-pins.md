# Chunk 1 spec pins: re-read requirements against the decisions that amend what they cite (spec_dupes amends rule)

Core: every requirement that cites a decision amended by ADR-170..ADR-178 is re-read against the amending decision, and either pinned (it agrees) or reported (it conflicts) - never pinned unread.
Proof: `python C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\5db71e90-61e3-4f1b-8a6c-a0ee38c54e11\scratchpad\dupes_summary.py D:\Abhay\Ventures\OptionsForOptions2-builder-reqs <your out file>` shows no PIN line left for your requirement range, except the ones you report as conflicts.
Class: amending-decision-not-pinned - 116 PIN failures on the chunk branch (8 decisions: ADR-170 x24, ADR-171 x3, ADR-172 x25, ADR-173 x29, ADR-175 x1, ADR-176 x29, ADR-177 x2, ADR-178 x3), 0 after except reported conflicts.
Budget: 30 min wall-clock, 40 tool calls
Report: evidence-table
Copy from: none - spec bookkeeping
Reference: none - spec bookkeeping, no screen
Tier: C

## Your range
Part 1: REQ-001 .. REQ-089. Part 2: REQ-090 .. REQ-140. Touch ONLY requirement files in your range. Never edit a decision (ADR) file, never run git, never commit: the orchestrator commits.

## What a pin means and how to do it
The current failure list is in `C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\5db71e90-61e3-4f1b-8a6c-a0ee38c54e11\scratchpad\dupes.txt` (lines starting `PIN`). Each says: REQ-x cites ADR-y, which ADR-z amends/refines -> re-read ADR-z, cite it and pin it with `"ADR-z #<fp>"`, or mark REQ-x Superseded.
1. Read each amending decision ONCE (in `spec/decisions/`): ADR-170, 171, 172, 173, 175, 176, 177, 178. Note in one line what it changes (example: ADR-172 - implied volatility comes from the bid-ask mid when two-sided, else LTP).
2. For each PIN line in your range: read the requirement's statement and acceptance criteria. Does any line CONTRADICT the amending decision (example: an AC saying "IV computed from LTP" against ADR-172)? 
   - No contradiction: add `spec/decisions/ADR-z.md` to the requirement's `spec_refs` list (if not there), and add `"ADR-z #<fp>"` (exact fp from the PIN line) to its `confirmed_against:` list (create the field as a one-line JSON-style list, like `REQ-001.md:32`, if missing; keep existing entries).
   - Contradiction: do NOT pin and do NOT change any statement or AC text. Report it: requirement id, the line quoted, the decision line quoted.
   - Never set a requirement Superseded.
3. Use the Edit tool for every change (frontmatter only). The kit guard blocks shell commands naming spec/, so use Read/Grep/Glob/Edit, and run the checker only through the scratch `dupes_summary.py` command above (it takes the worktree and an out file; use `dupes-part1.txt` / `dupes-part2.txt` in the same scratch folder).
4. Run the checker at the end once; your range must show no PIN lines except your reported conflicts.

## Report (under 250 words)
Evidence table: | Claim | Evidence | - pins added (count per decision), conflicts (each quoted), the checker's PIN count for your range before and after (from your out file).
