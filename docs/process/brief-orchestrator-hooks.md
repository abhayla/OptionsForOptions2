# Builder brief: three orchestrator hooks that turn 2026-10-16's repeated misses into blocks (Tier A: hooks)

Core: three PreToolUse hooks in `scripts/hooks/`, wired through `.claude/project/hooks.json` (then
`python tools/kit_settings.py .` regenerates the settings), each fail-open (exit 0 when its own script or input is
unreadable) and each with a test that dies without it:
1. `agent_brief_gate.py` (matcher: Agent): when the dispatch prompt names a file `docs/process/brief-*.md` (absolute
   or relative path), run `scripts/orchestrator/check_brief.py <that file>`; refuse the dispatch when it exits non-zero,
   printing its MISSING/FAIL lines. A prompt naming no brief file passes.
2. `merge_route_gate.py` (matchers: Bash, PowerShell): refuse a command that runs `tools/merge_when_green.py` directly
   unless the same command is `scripts/orchestrator/merge.py` or `scripts/orchestrator/land.py`; add
   `scripts/orchestrator/merge.py <pr>` = `pr_close_check.py --pr N`, then `gh pr update-branch N` (ignore "already
   up-to-date"), then `tools/merge_when_green.py N`, each step stopping the chain on failure.
3. `issue_route_gate.py` (matchers: Bash, PowerShell): refuse `gh issue create` (any spelling: `gh  issue create`,
   `gh.exe issue create`) and point to `scripts/orchestrator/gh_issue.py app <label> <title> <body-file> --stage <s>`;
   `gh issue comment/close/view` pass.
Proof: a test per hook feeding the real hook-input JSON shape (read an existing project hook in `scripts/hooks/` and
its test for the shape) - the 2026-10-16 cases: the W-080 r9 brief (`docs/process/brief-W-080-r9.md`, fails
check_brief) is refused; `python tools/merge_when_green.py 308` is refused, `python scripts/orchestrator/merge.py 308`
passes; `gh issue create --title x --body-file y` is refused.

Model: sonnet.
Budget: 40 min wall-clock, 75 tool calls. At budget STOP and report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under 250 words, branch + head sha.
Copy from: none - this repo's existing project hooks in `scripts/hooks/` (edit_lint.py, gate_before_commit.py) are the
pattern for input parsing, fail-open and tests.
Findings checked: targeted-tests-miss-dependent-files, guard-by-banned-shapes, pr-text-closes-issue-unintended
Tests: `python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py` and the new hook test files; `python tools/kit_settings.py . --check` after regenerating.

## Spec basis
CLAUDE.md fast delivery rules 4, 7 and 8 (orchestrator lessons 2026-10-16); run-discipline E1 (project hooks live in
this repo, no-op when their script is missing); kit learning L2 (a second occurrence becomes a mechanism).

## Must hold (reviewer checklist)
1. Fail-open: missing script, malformed stdin, unknown tool name -> exit 0, no output.
2. No false refusals: `gh issue comment`, `gh pr merge` inside merge_when_green (it runs as a subprocess, not a tool
   call), `land.py` (which calls the gate itself), and Agent prompts without a brief path all pass.
3. The merge regex cannot be dodged by `python  tools\merge_when_green.py`, `py tools/merge_when_green.py`, a
   `cd tools && python merge_when_green.py` chain - test these spellings.
4. `merge.py` stops on a failed close check and never merges a red PR (it only calls the kit gate).
5. Each hook has a test that goes red when the hook's check is removed (mutation).
6. Wiring only through `.claude/project/hooks.json` + `tools/kit_settings.py .`; never edit the generated settings
   file or any kit file.

## Rules
Your own worktree, branch `orch/hooks-2026-10-16` from `origin/main`; commit messages must not name the spec folder;
commit and push; no PR; never write `evidence/`, `work/` or the spec.
