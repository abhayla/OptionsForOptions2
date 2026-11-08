# Iron condor test results and fix plan, saved 7 Nov 2026 ~01:1x IST (owner: "save the plan in detail; we will revisit it and get it reviewed again")

STATUS: plan NOT approved. Development stays ON HOLD (owner rule: until the owner says "start development").
Next step when resumed: independent reviewers review plan-v4.md, then the owner approves or changes it.

## Files here
- `plan-v4.md` - the code-verified plan: every issue (~65) in 4 parallel lanes, one screen test at the end, ~42 h
  builder time, ~16 h elapsed; what was merged/removed and why; speed-up options (5 builders ~12 h; 68 later ~12 h).
- `code-checks.md` - the four read-only code checks behind v4 (file:line per issue, what exists, smallest fix,
  overlaps, minutes) + the 5 gate failures with causes; lead spot-checks listed at the top.
- `plan-v3-superseded.md` - the earlier plan (estimated from issue text, not code: too high, wrongly called 3 small
  changes "new features").
- `ic-test-issues-snapshot.md` - snapshot of D:\Abhay\scratch\ic-uitest\ISSUES.md (issues 1-91 + every verified test
  result, owner answers, corrections).
- `rerun-checklist-superseded.md` - the Monday live checklist, dropped (owner: test data only).

## How the owner shaped the plan (7 Nov 00:5x-01:1x, question tool)
1. "Test data only" - no live-market day; PC web only (no phone width).
2. Implementation = code changes + unit tests for the changed code and files it touches + test what changed +
   on-screen testing; NO PRs, NO CI.
3. Estimates must come from the code, not the issue text: the owner challenged the "new features" label - correct:
   the settings layers (layers.resolve + 99-key registry), the next-expiry roll (A-04/A-05) and the unmapped-shape
   detection already exist; only small changes remain.
4. Remove duplicates and reduce time (v4 merges listed in plan-v4.md).
5. Issue 80 decided: one combined order per contract and side (ADR-274).

## State of the code and branch at save time
- feature/adjustments (settings tree) local commits NOT pushed: 920feada, f70ceda9, 9a8ffd09 (ADR-272/273), acef7664
  (finding), b94c2484 (ADR-274), plus this save. Never main without the owner's OK.
- Full prepush gate 7 Nov 00:31-00:58 on b94c2484: TOTAL FAIL, 5 steps (causes + ~1 h of fixes in code-checks.md
  section 4; lane D's first item). Nothing pushed.
- Test verdict: ready for the owner's manual PAPER test, not for real orders. Highest open: issue 65 class
  (knowledge/findings/rule-entry-baseline-taken-at-first-check.json) and stale prices on Compare (ADR-272).
- Never tested on test data: paper stops firing (stop monitor only with the live market), Pause after 15:30 (real clock).
- Open owner questions: docs/process/owner-questions-2026-11-07.md (Q1 answered -> ADR-274; Q2 plan approval: not approved, to revisit).
