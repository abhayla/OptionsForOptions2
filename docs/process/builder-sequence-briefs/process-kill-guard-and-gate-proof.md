# Process item: prove the mutation gate fix, and a hook that refuses killing processes by name

Common brief: docs/process/builder-brief.md (Budget hard stop: at 32 calls start nothing new, commit, report). Run
`python scripts/orchestrator/mutation_gate.py` on this item's own hook mutants before reporting; quote its results file.
Size: S, 4 files, 2 items
CI: kit tests job (`tests/hooks/test_kill_by_name_guard.py`, `tests/orchestrator/test_mutation_gate.py`; vars: none).
No database. Expected (orchestrator, before dispatch, clock 09:50): 30 min / ~120k.

Core: a shell command that would stop processes by NAME is refused before it runs.
Proof: step 1 is `tests/hooks/test_kill_by_name_guard.py` failing first: `taskkill //F //IM python.exe` (the exact
command that killed the owner's live API at 09:47 on 2026-10-23, finding process-kill-by-name-hits-others) is refused;
`taskkill /PID 1234 /F` is allowed.

Spec basis: none - the spec says nothing about delivery tooling (searched: kill, process, hook); finding
process-kill-by-name-hits-others (third occurrence); user standing rule "a process-stop command never matches its own
command line ... kill by PID"; best practice.
Copy from: none - mirror an existing project hook's shape in `scripts/hooks/` (fail open, input reading).

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-process`, branch `build/seq-process`, head 56ae0041 - its OWN worktree.
Never write elsewhere. Commit with `git commit -F <msg> -- <your paths>`; do NOT push. NEVER stop a process by name:
record the PID of anything you start and stop only that PID. Scratch: `...\b9b5cb32-ea0c-400f-80e1-fbd7045cbf2a\scratchpad\proc-kill`.

## What to do
1. Gate proof: run `python scripts/orchestrator/mutation_gate.py` with the checker's adapted mutants
   (`...\scratchpad\proc-gate-fix1\mutants3.json`, 10 G mutants) against `tests/orchestrator/test_mutation_gate.py`;
   every one killed; quote the results file. A survivor: add its killing test (tests only).
2. `scripts/hooks/kill_by_name_guard.py`, a PreToolUse hook for Bash and PowerShell commands: an ALLOW-LIST of
   process-stop forms - `taskkill` only with `/PID <digits>` (any number of them) and no `/IM`; `Stop-Process` only with
   `-Id <digits>`; `kill <digits>`; everything else that stops processes is refused (`taskkill ... /IM`,
   `Stop-Process -Name`, `Get-Process ... | Stop-Process`, `pkill`, `killall`, `kill %name`, `wmic process ... delete`)
   with the text "stop only the PIDs you started (kill by PID; finding process-kill-by-name-hits-others)"; a crash,
   missing file or malformed input exits 0 (fail open). Wire it in `.claude/project/hooks.json` (Edit tool) for both
   Bash and PowerShell, regenerate with `python tools/kit_settings.py .` (bare, from the worktree root) and
   `python tools/kit_settings.py . --check`.

Attack list: (each names its test file)
1. `taskkill //F //IM python.exe` and `taskkill /IM node.exe /F` refused (`tests/hooks/test_kill_by_name_guard.py`).
2. `taskkill /PID 1234 /F` and `Stop-Process -Id 4956 -Force` allowed (same file).
3. `Stop-Process -Name python`, `Get-Process python | Stop-Process`, `pkill -f uvicorn`, `killall python` refused (same file).
4. A kill hidden after `;`, `&&` or inside a `$( )` / backticks refused (same file).
5. A crash, a missing script, malformed JSON input -> exit 0 (same file).
6. The gate's 10 mutants all killed (`tests/orchestrator/test_mutation_gate.py`, results file quoted).

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step changes; (c) the hook is an allow-list of PID-based stop forms and fails closed on a stop command it cannot parse (refuse), but open on its own crash; (d) the hook input's answer states - a Bash command, a PowerShell command, an empty command, another tool, malformed input - each in the test file with what it does.
Threat model: in scope - an agent killing another agent's or the owner's process by name, a kill hidden in a compound command; out of scope - a deliberate bypass by running a script file that kills by name (the rule still applies in prose).
Findings checked: guard-as-forbidden-list, wall-clock-assertion-flakes-under-load
Reviewer checklist: allow-list of PID forms; compound commands parsed; fail open on crash; settings regenerated and
--check green; gate results quoted; no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not
rise; targeted tests only; no regenerated files in the PR beyond the settings file.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 30 min wall-clock, 40 tool calls
Report: evidence-table
