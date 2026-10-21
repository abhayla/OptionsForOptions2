# Builder brief: tracker_check.py - the build-ahead tracker agrees with GitHub and loses no row - GC-2h item 4, Tier B

Common brief: docs/process/builder-brief.md
Core: `python scripts/orchestrator/tracker_check.py .` exits 0 on today's tracker and GitHub state, and exits 1 naming the
row when a row is deleted, a status contradicts GitHub, an open issue has no row, or an open row has no contract.
Proof: run it against the real `docs/process/build-ahead-tracker.md` and live `gh` state -> exit 0; then the planted
cases in tests (offline fixture) each exit 1 with the row named.
Spec basis: ADR-112 (2); goal-chain.md chain rules 8-9.

ADR-112: "a row leaves only as closed, parked (with an issue) or deferred"
Copy from: none - new tooling; scripts/orchestrator/coverage.py is the closest pattern (it parses a docs file and calls gh): reuse its gh helper if one exists.
Findings checked: guard-as-forbidden-list, guard-without-killing-test
Threat model: in scope - an honest close-out that forgets a row, mistypes a status, or leaves a row open with no contract; out of scope - someone editing the tracker and its base copy together on purpose.
Tier: B (tooling). Branch: build/tracker-check from origin/main.
Budget: 45 min wall-clock, 45 tool calls
Report: evidence-table

## What to build
`scripts/orchestrator/tracker_check.py` (stdlib only):
- parse the markdown table in docs/process/build-ahead-tracker.md (columns Id | Item | P | Contract | Tier | Status |
  Evidence); status must match the closed list `todo`, `building`, `held #N`, `merged #N`, `verified`, `closed`,
  `parked #N`, `deferred #N`, `blocked-owner`, `blocked-live`;
- deleted rows: compare Ids with the tracker at `origin/main` (git show) - an Id present there and missing now fails;
- GitHub (one `gh issue list --state all` + `gh pr list --state all` call each, JSON): `held #N` -> PR N open; `merged
  #N` -> PR N merged; an issue-id row (`#N`) `closed` -> issue N closed; an open status on an issue-id row -> issue open;
  every OPEN issue has a row;
- every row not `closed`/`parked`/`deferred` has a contract (any `GC-*`, `owner`, `stage-5`);
- `--offline FIXTURE.json` replaces both gh calls and the git base; output: one line per failure, `OK` otherwise.
Tests in tests/orchestrator/test_tracker_check.py using `--offline` fixtures: each failure kind planted -> exit 1 naming
the Id; the clean fixture -> exit 0. Add the command to builder-brief.md? No - the close-out step of each contract runs it
(goal-chain chain rule 8 already says so).

## B4 standing items
(a) none; (b) stdlib only - CI installs pyyaml jsonschema pytest; (c) the status check is an allow-list; unknown column
counts or a missing table fail closed; (d) gh answer states: OK / gh missing / gh error / empty list -> each a clear exit.

Rules: no new duplicated literal; ruff baseline must not rise; targeted tests only. Do not open a PR. Windows: `-p no:metadata`.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
