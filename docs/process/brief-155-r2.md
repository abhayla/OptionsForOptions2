# Builder brief: #155 round 2 - Tier A review findings (2026-10-10)

Core: the hook refuses every commit/push/merge that follows an earlier step whose failure would not stop it -
including behind wrappers and in PowerShell - and refuses no harmless setup line; it stays fail-open and fast.
Proof (step 1, red first against 6fcf51e): each REFUSE line below is allowed today and each ALLOW line below is
refused today (review probes); tests for every line, then green.

Tier: A. Model: sonnet/medium. Budget: 40 min wall-clock, 55 tool calls. Commit after each item; at budget stop after a
commit and report. Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~250 words.
Copy from: none.

## RCA (the orchestrator's round-1 brief caused finding 1 - brief-rule-from-memory)
1. CRITICAL: rule (c) let `$ErrorActionPreference = 'Stop'` stand in for `set -e`. Measured by the reviewer on this
   PC's pwsh 7.5.2: a failing native program does NOT stop the script under that setting
   (`PSNativeCommandUseErrorActionPreference=False`). REMOVE that allowance entirely. PowerShell commands are allowed
   only through `&&` chaining (PowerShell 7 supports it) or the setup-line allow-list below.
2. MAJOR: the step finder only sees `git commit|push` / `merge_when_green` as a plain step. It must also find them
   inside: `if ...; then ...; fi`, `( ... )`, `{ ...; }`, `env VAR=x <cmd>`, `time <cmd>`, `git --git-dir X push` /
   `git -c k=v commit` (git global options before the subcommand), `uv run`/`python -m` wrappers around
   merge_when_green, and `bash -c "..."` / `sh -c '...'` (judge the inner string recursively).
3. MAJOR: `gh pr merge` is a merge step; add it to the steps.
4. MAJOR: no test puts a commit/push/merge AFTER a quoted `|` - the mutation "quoted | is a separator" survived. Add.

## Also fix (MINOR)
5. Setup lines are not "gates": a preceding step that is ONLY one of these is harmless and does not refuse, whatever
   separator follows it (an ALLOW-list, finding guard-as-forbidden-list): `cd <path>`, `pushd`/`popd`, a bare
   variable assignment `NAME=value` / `export NAME=value` / `$name = value` (PowerShell), `set -x`/`set +x`/`set -e`/
   `set -o pipefail`, comment lines, empty lines, and `<step> || exit N` / `|| return N` (an explicit stop). Anything
   else before a commit still needs `&&`.
6. The refusal message names the earlier step's command word only (e.g. `pytest`, `python`), never echoes the command
   text (it may hold a token), and says: run that step as its own call, read its result, then commit/push.
7. Performance: bound the work - commands longer than 100 KB are allowed without parsing (fail-open), and the word
   splitter must be linear (the review measured 33.4 s for 1 MB, 0.35 s for 100 KB).
8. PowerShell `\"`: a trailing backslash before a closing double quote is not an escape in PowerShell
   (`git add "C:\a\" && git commit -m "fix; git push"` must be allowed).

## Example lines to add (tests assert exactly these)
REFUSE: `$ErrorActionPreference = 'Stop'; python check.py; git commit -m x`; `if pytest | tail -1; then git push; fi`;
`pytest | tail; (git push)`; `pytest | tail; { git push; }`; `pytest | tail; env X=1 git push`;
`pytest | tail; time git push`; `pytest | tail; git --git-dir .git push`;
`pytest | tail; uv run python tools/merge_when_green.py 5`; `bash -c "gate | tail; git push"`;
`pytest | tail -1; gh pr merge 5 --squash`; `echo "a | b" ; pytest | tail; git commit -m x`.
ALLOW: `cd /c/x\ngit commit -m x`; `MSG="x"\ngit commit -m "$MSG"`; `set -x\ngit add -A && git commit -m x`;
`pytest || exit 1\ngit push`; `git add "C:\a\" && git commit -m "fix; git push"`;
`git commit -m "a | b" && git push` (quoted pipe before nothing); every ALLOW line of round 1.

## Rules
- Targeted: `python -m pytest -q -p no:cacheprovider tests/hooks` from the worktree; CI mirror
  `python C:\Abhay\Ventures\OptionsForOptions2\scripts\orchestrator\atool.py C:\Abhay\Ventures\OptionsForOptions2-155 155 --no-tests`.
  Mutations to show red: quoted `|` as a separator; drop the bash -c recursion; re-add the PowerShell EAP allowance.
- Kit guard: shell text must not name .claude, tools/, spec/requirements, .github or views. Do not edit kit files.
  Never write `evidence/`. Push `fix/155-gate-before-commit`; no PR.
