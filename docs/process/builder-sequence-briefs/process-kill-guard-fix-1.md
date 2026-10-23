# Process item fix 1 (the last round): kill_by_name_guard - commands after shell keywords, PowerShell sinks as an allow-list

Common brief: docs/process/builder-brief.md (Budget hard stop: at 32 calls start nothing new, commit, report). Run
`python scripts/orchestrator/mutation_gate.py` on the checker's mutants plus your own before reporting; quote its file.
Size: S, 2 files, 4 items
CI: kit tests job (`tests/hooks/test_kill_by_name_guard.py`; vars: none). No database.
Expected (orchestrator, before dispatch, clock 10:1x): 30 min / ~120k. A failed check after this round PARKS the hook
(the PID rule stays prose in every brief).

Core: an honest agent's accidental kill-by-name, in the forms it actually writes, is refused before it runs.
Proof: step 1 - the checker's CRITICAL cases fail first: `for p in $(pgrep python); do kill $p; done`,
`for /f "tokens=2" %i in ('tasklist ^| findstr python') do taskkill /PID %i /F`, `if true; then pkill python; fi`,
`! pkill python` are each ALLOWED by the hook at b5e18906 (red), and refused after the fix.

Spec basis: none - the spec says nothing about delivery tooling (searched: kill, process, hook); finding
process-kill-by-name-hits-others; the Tier A check of b5e18906 (verify-killguard: FAIL, 1 CRITICAL, 1 MAJOR).
Copy from: none.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-process`, branch `build/seq-process`, head ac062f28 - its OWN worktree.
Commit with `git commit -F <msg> -- <your paths>`; do NOT push. NEVER stop a process by name; stop only PIDs you
recorded. Scratch: `...\b9b5cb32-ea0c-400f-80e1-fbd7045cbf2a\scratchpad\proc-kill-fix1`; the checker's probe, mutants
and results: `...\scratchpad\verify-killguard\` (probe.py, results.jsonl).

## What to do
1. CRITICAL: a word after a shell keyword (`do then else elif ! if while until`, and after `for /f ... do`) starts a
   command and is checked like any other.
2. MAJOR, as an ALLOW-LIST: a PowerShell pipeline whose source selects processes (`Get-Process`, `Get-CimInstance` /
   `Get-WmiObject` on Win32_Process, `[System.Diagnostics.Process]::GetProcesses*`, `ps`, `gps`) may flow only into
   read-only sinks (`Select-Object`, `Where-Object`, `Sort-Object`, `Format-*`, `Out-*`, `Measure-Object`,
   `ConvertTo-*`, `Group-Object`); any other sink (`Stop-Process`, `Remove-CimInstance`, `Remove-WmiObject`,
   `Invoke-CimMethod`, `Invoke-WmiMethod`, `ForEach-Object`/`%` with any body, method calls like `.Kill()`) is refused.
3. MINOR false refusals: allow the PID forms the refusal text recommends - `Stop-Process -Id $p.Id` / `-Id $var` and
   `kill $pid` / `kill $!` (a variable PID is allowed: the rule is "by PID", and a variable holding a recorded PID is
   that); a here-string with an apostrophe; quoted text like `echo ".Kill()"` is not a call.
4. MINOR: `kill 0` and `kill -<sig> 0` refused (stops the whole process group); a test for R09 (unterminated quote
   fails closed); `fuser -k` and `kill-port` refused.
Out of scope (written into the hook's docstring and the threat model): deliberate disguise - backtick or caret inside
a word (``Stop-Pro`cess``, `t^askkill`), a kill inside `python -c` / `node -e` / a script file, `Start-Process
-ArgumentList` building a kill; the PID rule in every brief covers those.

Attack list: (each names its test file)
1. The four CRITICAL loop/keyword forms refused (`tests/hooks/test_kill_by_name_guard.py`).
2. The six PowerShell object-kill forms from the check refused; a read-only pipeline (`Get-Process python | Select-Object Id`) allowed (same file).
3. `Stop-Process -Id $p.Id`, `kill $pid`, `kill $!` allowed; `kill 0` refused (same file).
4. Every earlier case still holds: the 156 existing tests pass (same file).
5. The checker's mutants (R09 included) all killed through the gate (results file quoted).

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step changes; (c) the hook is an allow-list of PID stop forms and of read-only pipeline sinks, fails closed on a stop command it cannot parse, open on its own crash; (d) the hook input states - Bash command, PowerShell command, empty, another tool, malformed - each tested.
Threat model: in scope - an honest agent's accidental kill by name or pattern, in loops, conditionals and pipelines; out of scope - deliberate disguise (backtick/caret inside a word, a kill inside python -c / node -e / a script, Start-Process -ArgumentList).
Findings checked: guard-as-forbidden-list, process-kill-by-name-hits-others
Reviewer checklist: keyword-start commands checked; PowerShell sinks an allow-list; PID-variable forms allowed; out of
scope written down; all earlier tests pass; gate results quoted; no new duplicated literal; reuse the existing helper;
ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 30 min wall-clock, 40 tool calls
Report: evidence-table
