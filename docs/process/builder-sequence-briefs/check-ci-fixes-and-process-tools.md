# Two findings-only checks (ADR-178 (1)): chunk-1 CI fixes 1-3, and the process tools

Independent reviewer; you wrote none of it. READ-ONLY: never edit, create, commit or delete a tracked file in any
checkout. Scratch only in
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\5db71e90-61e3-4f1b-8a6c-a0ee38c54e11\scratchpad\<your part>`.
Code: worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`, current head.
BINDING: never stop a process by name. Kit guard: a shell command naming spec/, tools/, .claude, factory, views or
.github is blocked; use Read/Grep/Glob. No DB tests; no Kite.

## Part 1: CI fixes (Opus) - commits 5d5534d0 (fix 1), 6097acf8 (fix 2), and the CI fix 3 commit (`git log --grep "CI fix 3"`)
Question: did any fix make a test pass by weakening it, hide a real product defect, or widen a guard?
Attack: `backend/ofo_app/kite_ws.py` (the `_SILENT_AFTER` rename: is the 60 s silence still enforced and still
tested?), `scripts/hooks/brief_path.py` (fail-open on a missing file: what does a hook do when the brief path is
wrong - does it silently pass a brief it should refuse?), the two wall-clock tests pinned to an open-market moment
(do they still test the closed-market branch somewhere?), the `importorskip asyncpg` (does the kit job now skip a test
that should run?), the OFO_REQUIRE_BUNDLE_SCAN toggle, and CI fix 3's test-fake change for `GET /strategies/{id}`
(does the golden test still prove the old bytes for a strategy with no versions?). Diffs: `git show <sha> --stat`
then targeted `git show <sha> -- <file>`.
Why Opus: kite_ws.py is the live-feed liveness file (safety set).

## Part 2: process tools (Sonnet) - commit f441b87d: `scripts/orchestrator/make_brief.py`, `scripts/orchestrator/row_actuals.py`
Spec of what was asked: `docs/process/builder-sequence-briefs/process-make-brief.md`.
Question: does each tool do what the brief asked, fail closed on bad input, and are its tests real? Run its tests
(find them with `git show f441b87d --stat`). Known unproven: row_actuals' token column on real transcripts - try it
on one real transcript: the newest `*.jsonl` under `C:\Users\itsab\.claude\projects\D--Abhay-Ventures-OptionsForOptions2\`
(read only; print the tool's output, never the transcript).

Return, per part: findings `{"part": 1|2, "severity": "CRITICAL|MAJOR|MINOR", "file": "path:line", "finding": "...",
"evidence": "command + result line", "fix": "smallest fix"}`, then under 200 words per part: verdict PASS / FAIL.
Budget: 15 min wall-clock, 20 tool calls (per part)
Report: evidence-table
