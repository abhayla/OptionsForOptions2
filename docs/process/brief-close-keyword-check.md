# Builder brief: PR close-keyword check (Tier B, mechanism for a repeated class)

Core: a checker that, given a PR's body and commit messages, finds every GitHub closing reference (close/closes/closed,
fix/fixes/fixed, resolve/resolves/resolved, any case, optional colon, then `#N` or `owner/repo#N`) and FAILS unless
each one is a whole line of the exact form `Fixes #N` / `Closes #N` / `Resolves #N` (optional trailing period) in the
PR body.
Proof: run it on the three real merged PR bodies that closed issues by mistake tonight - #283 (body starts
"**Fix #263 items 1-3 ...**"), #284 ("**Fix #279 items 2-3 ...**" and "The code clash with #275 is resolved: #275
moved to 223") - it must fail on each and name the line; on #282 (body has a line "Fixes #237.") it must pass.
Fetch them with `gh pr view <n> --json body,commits`.

Model: sonnet.
Budget: 30 min wall-clock, 50 tool calls. At budget STOP and report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under 250 words.
Copy from: none - small project script; algochanakya has no PR tooling.

## Class (defect-fix contract)
- RCA: GitHub closes an issue on any closing keyword followed by `#N` in a PR body or in a commit message that reaches
  the default branch, including qualified forms ("Fix #263 items 1-3") and prose ("is resolved: #275"); nothing checked
  PR bodies, so partial fixes closed whole issues.
- Class: every PR body and every commit message in a PR. Before: unchecked (3 wrong closes on 2026-10-16, 1 on
  2026-09-29, memory `pr-body-close-keywords`). After: a red check on the PR.
- Proof: the real-PR run above, plus unit tests.
- Detection: this check is the detection.

## What to build
1. `scripts/orchestrator/pr_close_check.py`: `python scripts/orchestrator/pr_close_check.py --pr N` (reads body +
   commit messages with `gh pr view N --json body,commits`) and `--body-file F [--commits-file G]` (offline mode for
   tests and CI). Exit 1 with one line per offending reference (`body line 1: "Fix #263 items 1-3" - qualified or
   prose closing reference; write "addresses items 1-3 of #263", or a whole line "Fixes #263" if all of it is done`).
   - Allowed only in the BODY, as a whole line: `^(Fixes|Closes|Resolves) #\d+\.?$` (case-insensitive keyword).
   - Any closing reference in a COMMIT MESSAGE fails (merge commits too) unless its line is the same whole-line form -
     commit messages like "Fix #275 items 1-5" close issues when the branch merges.
   - Ignore references inside backticks or fenced code blocks? NO - GitHub does not ignore them reliably; flag them.
   - "Addresses items 1-3 of #263", "#263 item 4 stays open", "see #271" must pass (no keyword directly before `#N`).
     GitHub matches keyword + optional colon + whitespace + reference; mirror exactly that.
2. Tests in `tests/test_pr_close_check.py` (domain test tree, standard library only): each real body above (store the
   three bodies as small fixture text files under `tests/fixtures/pr_bodies/`, copied verbatim from `gh pr view`), the
   allowed forms, the colon form, `owner/repo#N`, case variants, commit-message failure.
3. CI: add a job to `.github/workflows/app-tests.yml` (project-owned; NEVER edit `ci.yml`), on `pull_request` only
   (add `edited` to the PR event types if the workflow's `on:` allows it without changing other jobs' triggers - if it
   would change them, put the job in a NEW workflow file `.github/workflows/pr-close-check.yml` instead, which is the
   preferred, safer option). The job writes the PR body from `github.event.pull_request.body` to a file via an env var
   (never interpolate the body into the shell script - injection), fetches commit messages with `gh api` using
   `GITHUB_TOKEN`, and runs the script in offline mode.

## Rules
- Fail closed: if the body or commits cannot be read, exit 2 with a message (the job fails).
- Targeted tests only: `python -m pytest -q -p no:cacheprovider tests/test_pr_close_check.py tests/test_fixture_symbols.py`.
- Your own worktree, branch `fix/pr-close-check` from `origin/main`; commit + push; do not open the PR; never write
  `evidence/`, `work/` or the spec. Your own commit messages must pass your checker.
