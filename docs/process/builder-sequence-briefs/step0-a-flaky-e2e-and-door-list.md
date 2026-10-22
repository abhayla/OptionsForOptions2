# Step 0 part A: two flaky e2e tests + response-door model list (builder sequence, Tier B)

Common brief: docs/process/builder-brief.md (this brief overrides it where they differ: see the section Where you work).

Core: the two named e2e tests fail intermittently on main for a mechanism you can name from the failed CI logs.
Proof: the failed CI run logs on main (`gh run list --branch main --workflow app-tests.yml --status failure`, then
`gh run view <id> --log-failed`) show each failure's assertion and timing; you quote them before changing code.

Spec basis: goal contract `docs/process/goal-contract-builder-sequence-2026-10-22.md`, "Step 0": "Fix the two flaky
end-to-end tests that turned main red 4 of 43 pushes (`create-strategy.spec.ts:31` 5 s timeout,
`strategy-live.spec.ts:136` "AC-4 two holders"), each under the defect-fix contract (RCA, class, failing run first,
proof)." and "Replace the response-door exact model COUNT with a checked-in sorted list of model names asserted exactly
(stricter, and a line merge no longer needs a hand recount; the count changed 33 times since 10-15)."
Copy from: none - test-infrastructure fixes, no legacy module covers them.
Tier: B. No product behaviour changes.
Threat model: in scope - a model added or removed without the list changing (both directions fail); out of scope - a forged class object injected at runtime (ADR-098).

## Where you work
- Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `docs/builder-feature-reqs` (already checked
  out). Do NOT create a branch, do NOT commit, do NOT push: another agent edits `work/` and
  `docs/process/coverage-stages.yaml` in the same worktree at the same time; never touch those paths, never run
  `git add`, `git stash`, `git checkout` or `git reset`. The orchestrator commits your files.
- Your scratch folder: `C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\cdc8b776-da99-4858-844d-ba9899512551\scratchpad\step0a`.

## Item 1 and 2: the flaky e2e tests (defect-fix contract, each)
For each test write, in your report: RCA (mechanism, one sentence, from the log), Class (every e2e test with the same
shape: grep `frontend/e2e/` for the same pattern, e.g. a fixed 5 s default `expect` timeout on a first paint that
waits for the API, or a second socket's first message raced against the page's own; list the files and lines), the
fix at class level (every member of the class, not only the named line), and `No detection change: <reason>` or the
detection added. Never raise a timeout as the only fix without naming why the wait is legitimately longer (a slow
first API answer on a 1-pool-connection CI API is a legitimate reason; a race is not - fix the race). Do not weaken
an assertion. You cannot run Playwright here (it needs CI's servers): the proof is the RCA from the real log plus the
class sweep; say unverified locally (CI proves it) in the evidence row.

## Item 3: response door
`tests_app/test_response_door.py` asserts `len(_app_models()) == 60`. Replace the count with a checked-in sorted list
of model names (a module-level tuple or a small text/JSON file next to the test) asserted EXACTLY equal to the sorted
discovered names, with a failure message that prints the added and the missing names. Keep every other assertion.
Run this file: `python scripts/orchestrator/db_run.py . python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_response_door.py`
(if the DB tunnel is down, say so; the list itself can be checked with a no-DB import - report which).

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step changes (workflows are kit files); (c) the door
list is an allow-list asserted exactly both ways (missing and extra both fail), discovered from the real subclasses;
(d) n/a: no other system's answer is read.
Reviewer checklist: exact list equality both directions; the two e2e RCAs quote real log lines; every class member
fixed; no assertion weakened; no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise;
targeted tests only; no regenerated files in the PR.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Also run: `python scripts/ruff_ratchet.py`; in `frontend/`: `npm run lint` and `npx tsc --noEmit -p .` if a tsconfig
covers e2e (else say so).
Budget: 45 min wall-clock, 60 tool calls
Report: evidence-table (under 300 words: files changed, RCA + class per test, the door change, each command and its
result line; uncommitted by design).
