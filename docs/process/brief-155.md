# Builder brief: #155 - a failing step must stop commit / push / merge (project PreToolUse hook)

Core: a PreToolUse hook on Bash (and PowerShell) refuses a command that runs `git commit`, `git push` or
`merge_when_green` after an earlier step whose failure would not stop it; every other command passes untouched.
Proof (step 1, red first): the decision function, run over the example table below, gives today (no hook) "allow" for
every refused example; after: exactly the table's verdicts.

Tier: A (a hook that runs on every shell command of every session; a false positive blocks real work).
Model: sonnet/medium. Budget: 40 min wall-clock, 55 tool calls. Commit after each step; at budget stop after a commit
and report. Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~250 words.
Copy from: none - mirrors this repo's `scripts/hooks/secret_scan.py` (stdin JSON, exit 0 allow / 2 block, message on
stderr, module-level decision function the tests import).

## RCA and Class (finding pipe-masks-gate-exit-code, 2 occurrences)
- RCA: a gate piped into a filter (`gate | tail`) takes the filter's exit status, and a command on the next line or
  after `;` runs whatever the step before returned, so a following commit/push/merge goes ahead after a failed gate.
- Class: every shell command text containing a commit, push or merge step.
- Rule (an ALLOW-list, finding guard-as-forbidden-list): a commit/push/merge step is allowed only when (a) it is the
  first step of the command, or (b) every step before it is joined to the next by `&&` and none of those earlier steps
  contains an unquoted pipe `|`, or (c) the command starts with `set -e` / `set -euo pipefail` (bash) or sets
  `$ErrorActionPreference = 'Stop'` (PowerShell) AND no earlier step is piped. The commit/push step itself may pipe
  its own output (`git push ... 2>&1 | tail -1` is fine). Anything after the commit/push step is not judged.
- Quoting: text inside quotes (commit messages, heredoc bodies) is not split on `;`, `|`, `&&` or newlines - a commit
  message containing "a | b" or a newline must not trip the hook. Heredoc bodies (`<<'EOF' ... EOF`) are data.

## Spec basis
- Finding pipe-masks-gate-exit-code (knowledge/findings/pipe-masks-gate-exit-code.json) and issue #155; learning L2
  (second occurrence = a mechanism). No product requirement - this is process tooling.

## Example table (the tests assert exactly these; add more)
ALLOW:
- `git commit -m "x"`
- `git add -A && git commit -q -m "a | b; c" && git log --oneline -1`
- `cd /c/x && git add -A && git commit -m "multi\nline"` (the message holds a newline inside quotes)
- `git push -q origin b 2>&1 | tail -1; git log --oneline -1`
- `python tools/merge_when_green.py 12`
- `set -euo pipefail; python check.py; git commit -m x`
- `pytest -q | tail -1` (no commit/push/merge at all)
- a heredoc: `cat > f <<'EOF'\nfoo | bar\nEOF\ngit status` (no commit)
REFUSE (message names the earlier step and says: run the gate as its own call, read its result, then commit):
- `python tools/ci_local.py | tail -3 && git push`
- `python check.py; git commit -m x`
- `python check.py\ngit add -A && git commit -m x`
- `pytest -q 2>&1 | tail -1 && git commit -m x`
- `make test || true && git push`
- `set -e; pytest | tail -1; git commit -m x` (set -e but the earlier step is piped)
- PowerShell: `python check.py; git push`

## Do
1. `scripts/hooks/gate_before_commit.py`: stdin JSON (tool_name, tool_input.command), a module-level
   `decide(command: str) -> tuple[bool, str]` (allowed, reason) that tokenises with quote and heredoc awareness (use
   `shlex` with punctuation_chars where it works; a small scanner where it does not), exit 0 / 2. Any parse failure or
   unexpected input -> ALLOW (fail open, never block on the hook's own bug) and print nothing.
2. `tests/hooks/test_gate_before_commit.py`: the table above (parametrized), the fail-open path, and a stdin round
   trip (subprocess) for one allow and one refuse.
3. Wire it: add a `Bash|PowerShell` PreToolUse entry to `.claude/project/hooks.json` in the same shape as the
   secret-scan entry (`f="$CLAUDE_PROJECT_DIR/scripts/hooks/gate_before_commit.py"; [ -f "$f" ] || exit 0; python "$f"`),
   then regenerate the settings with `python tools/kit_settings.py .` (plain command from the worktree root) and
   check `python tools/kit_settings.py . --check`. Read/edit `.claude/project/hooks.json` with the Read/Edit tools only.
4. Update the finding `knowledge/findings/pipe-masks-gate-exit-code.json`: detection status `guarded`, checks naming
   the hook and its test; regenerate with `python C:\Abhay\Ventures\OptionsForOptions2\scripts\orchestrator\regen.py C:\Abhay\Ventures\OptionsForOptions2-155`.

## Reviewer checklist (each must turn a test red)
- Treat a quoted `|` or newline as a separator; allow `;` before a commit; allow a piped earlier step under `set -e`;
  block when the hook itself crashes (must fail open).

## Rules
- Targeted tests: `python -m pytest -q -p no:cacheprovider tests/hooks` from the worktree; CI mirror
  `python C:\Abhay\Ventures\OptionsForOptions2\scripts\orchestrator\atool.py C:\Abhay\Ventures\OptionsForOptions2-155 155 --no-tests`.
- Kit guard: shell text must not name .claude, tools/, spec/requirements, .github or views except plain kit-tool runs
  from the worktree root. Do not edit kit files (`.claude/hooks/`, `.claude/rules/kit/`, `tools/`). Never write
  `evidence/`. Push `fix/155-gate-before-commit`; no PR.
