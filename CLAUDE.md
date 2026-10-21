# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# OptionsForOptions2 (working name) — Indian index options strategy platform

A public SaaS web platform where beginner and intermediate traders plan NIFTY/SENSEX options and futures
strategies, see the outcome at every market level, then execute through their own Zerodha account and have the
strategy monitored against their rules (`spec/vision/vision.md`). Built on the Startup-Factory kit (version in
`KIT_VERSION`); the kit's rules in `.claude/rules/kit/` always apply.

**Where the work stands:** read the newest `docs/process/session-handover-<date>.md` first (it names what merged,
what is PARKED, NEXT, and the per-PC setup that is not in git), then `docs/HANDOVER.md` (done/parked/blocked/deferred
lists) and the active plan `docs/process/master-plan-2026-10-07.md`. Nothing pending is closed until it is implemented
and independently verified. Open items: `spec/open-questions.md`. Do not write requirements or code before the ADRs
they rest on exist.
Orchestration: briefs in `docs/process/`, helpers in `scripts/orchestrator/`. Builder worktrees live under the
`.claude` folder, a path the kit guard blocks in Bash, so reach them through the helpers: `agit.py <agent-id> <git
args>` (git), `atool.py <agent-id>` (CI mirror), `agentwt.py <agent-id> status|release`, `ev_agent.py` /
`record_evidence.py` (verifier JSON → evidence files), `gh_issue.py kit|app` (issues, incl. `harvest`),
`aregen.py <agent-id>` (regenerate the findings index in a worktree and continue a paused rebase), `regen.py [dir]`
(regenerate findings index, spec digest and build order in a checkout), `dev_run.py <cwd>
<command>` (run with DATABASE_URL = ofo_dev for live runs and dev e2e; refuses any other database, ADR-078). Run
`check_brief.py <brief>` on every builder brief before dispatch: it fails when a spec quote in the brief is not verbatim
in the ADR/REQ/Q it cites (finding brief-rule-from-memory).

## Read first
1. `spec/decisions/ADR-*.md` — the owner's decisions. They win over everything else. Each carries the Q-numbers and
   `provenance:` (owner answer vs ChatGPT answer under the owner's delegation), with chat message numbers.
2. `docs/HANDOVER.md` — where the work stands and the next step.
3. `spec/open-questions.md` — undecided items; never decide one silently. New questions are numbered Q204+.
4. `knowledge/findings/` — proven failure classes; check before designing a mechanism.
5. Sensibull study (private, outside this public repo; `D:\Abhay\GLOBAL.md` §7): before designing or briefing any
   feature, open `D:\Abhay\Ventures\competitors\sensibull\2026-10-21\INDEX.md`, find the feature, cite screen numbers.
   Never copy its screenshots or account data into this repo. Broker layer, order path or market data: first read
   `D:\Abhay\Ventures\competitors\multi-broker-architecture\2026-10-21\INDEX.md` (10 apps, common stack, traps).
- `docs/reference/chatgpt/` holds the two full chat transcripts (primary) and the handoff files (lossy summaries).
  Reference only: never edit or delete them; `spec/` wins on any conflict (ADR-031). Map: `spec/traceability/source-map.md`.

## How the repo fits together
The repo is a traceability chain, checked by `tools/` and CI, not a code layout:
- `spec/decisions/ADR-###.md` (owner decisions) → `spec/requirements/REQ-###.md` (acceptance criteria)
  → `work/W-###.md` (one work item; `tests_required` covers the ACs) → code + tests
  → `evidence/<W-id>/<AC-id>.md` (written by the orchestrator from the verifier's output, never by the builder)
  → `releases/R-###.md` (rollback written before any deploy).
- Every artifact is Markdown + YAML frontmatter validated against `factory/schemas/*.schema.json`
  (`factory_lint.py`); `trace_check.py` refuses a requirement marked Verified with a broken chain, or
  evidence whose `verified_by` is the builder.
- Delivery of a work item runs through the `deliver` skill: `builder` agent (own worktree) → `verifier`
  agent (fresh context, read-only; Tier B/A) → evidence → trace check → PR → `merge_when_green.py`.
  The Tier C/B/A table is in `.claude/skills/deliver/SKILL.md`.
- Two code layers, two test suites. `backend/ofo/` is the domain (engine, scenario, strategy, orders, execution,
  reconciliation, …): standard library only, tested in `tests/` against fakes by the kit CI. `backend/ofo_app/` is
  the FastAPI app on top of it (routes, PostgreSQL stores, Alembic migrations in `backend/ofo_app/alembic/`, Kite
  login/token store/websocket/history clients), tested in `tests_app/` with `pytest-app.ini`. `frontend/` is Vue 3 +
  Vite + Pinia + Tailwind, unit tests in Vitest, Playwright e2e against `vite preview` proxying `/api` to the real
  API. The app job is `.github/workflows/app-tests.yml` (project-owned, separate from the kit's `ci.yml`).
- Database tests run as the limited `ofo_app` role (ADR-048); migrations run as the owner role. Money stays
  `Decimal`, `NUMERIC` in the DB and a string in API output (`.claude/rules/project/decimal-money-boundaries.md`).
- Real Kite data reaches tests only as recorded fixtures (`tests/fixtures/kite_ws/`, `tests/fixtures/kite_history/`);
  `APP_ENV=test` + `OUTCOME_REPLAY=1` serves recorded frames to the outcome route for e2e.
- Repo-wide guard tests sit at the top of `tests/` (`test_spec_integrity.py`, `test_no_wall_clock_asserts.py`,
  `test_fixture_symbols.py`); a change can fail them without touching any package. `views/` is generated output, never
  hand-edited.
- `knowledge/findings/*.json`: one file per failure class; the index is generated by
  `build_findings_index.py` and each `spec_ref` must resolve (`check_spec_refs.py`).
- The production seatbelt lives in the project's hidden Factory folder and is owner-edited only. A
  PreToolUse hook blocks any tool call — or file content — that names its paths, so describe it, don't
  path it. It declares no deploy patterns yet, so deploy commands are not gated.
- The Claude settings file is GENERATED: edit `.claude/project/hooks.json` or `.claude/project/optouts.json`,
  then run `python tools/kit_settings.py .`. Project rules go in `.claude/rules/project/` (the
  always-loaded rule budget is 5 files, shared with the kit).

## Hard rules
- Every order belongs to a strategy; no standalone order entry anywhere, at any UX level (ADR-002).
- One calculation engine owns every P&L/payoff number; formulas in `spec/business-rules/scenario-calculations.md`
  are locked; money in exact decimal, never float (ADR-008).
- Zerodha is the authority on positions, orders, margin and execution; submitted ≠ executed; no automatic order
  retry; no silent contract substitution or strategy rewrite; an unresolved reconciliation mismatch blocks execution
  (ADR-016–ADR-019). The invariants list is `spec/testing/core-invariants.md`.
- Wording is decision-support, never advice: "Strategies you could consider", "Suggested setup"; never "you
  should", "best trade", "guaranteed" (ADR-003).
- Browsers never talk to a market-data vendor or hold its credentials; providers, broker and payments sit behind
  adapters (ADR-012, ADR-029).
- Kit files (`.claude/rules/kit/`, `.claude/kit/`, `.claude/README.md`, `.claude/hooks/`,
  `.claude/agents/`, `.claude/skills/deliver/`, `.claude/skills/intake/`, `tools/`,
  `factory/schemas/`, `.github/workflows/ci.yml`, `.github/pull_request_template.md`,
  `KIT_VERSION`) are never edited here; a kit defect or a lesson every project should get
  is filed as a GitHub issue labelled `harvest` in `abhayla/Startup-Factory` — never edit kit files
  here.
- The kit guard hook (`kit_file_guard.py`) blocks any Bash command whose text names a kit path, even a
  read-only `grep`/`cat`, and a `tools/*.py` run with a redirect or pipe (`2>&1 | tail`). Read kit files
  with the Read/Grep/Glob tools; run each tool as its own plain command.
- Stack (ADR-043): Python 3.12+ / FastAPI, PostgreSQL, Redis; Vue 3 + Vite. Legacy repos (`abhayla/algochanakya`
  main source; `OFO`, `NewOFO`, `OptionsForOptions` reference) are never edited from here. Code may be copied or
  adapted per `spec/technical-design/legacy-reuse.md`: the file names its source repo, commit and path, is changed
  to meet every hard rule, and gets this project's own tests. The calculation engine and order execution are built new.
- Copy first (ADR-047): before writing any module, check the algochanakya map in
  `spec/technical-design/legacy-reuse.md` (every module, verdict, change, conflict; pinned to `bf9faf7`). Every builder
  brief carries `Copy from: <map rows>` or `Copy from: none - <reason>`. Never search algochanakya ad hoc; if the map
  lacks a row, add it there first. Kite API facts: the user-level `zerodha-expert` skill. Engine-math reviews: the
  project skill `options-math-review`.
- Every PR body carries the Spec-deviation block (`Class: none` is valid); CI fails without it.
- Never put fix/close/resolve (any form, even with a colon) directly before `#N` in a PR body or commit message,
  except as a whole body line `Fixes #N` when ALL of the issue is done. For part of an issue, write "addresses item 1 of
  #N". GitHub closes the whole issue otherwise. Enforced by the `pr-close-check` workflow
  (`scripts/orchestrator/pr_close_check.py --pr N` to check before pushing).
- Coding standards (REQ-075, ADR-093): a standard is an automatic check or marked review-only; real-world values have
  one home module (a repo test fails on a retyped literal); reuse helpers, never copy them. Per-technology rules load
  by path from `.claude/rules/project/`; the edit hook lints each file as it is written. Every builder brief carries:
  "no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no
  regenerated files in the PR".
- Merge only with `python scripts/orchestrator/merge.py <pr> --reviewed-sha <full sha>` (or `land.py`), which runs
  the kit gate `tools/merge_when_green.py <pr> --reviewed-sha <full sha>` in the foreground — never
  `gh pr checks --watch && gh pr merge`, which merges before CI has started. On Windows prefix `merge.py`/`land.py`
  with `PYTHONUTF8=1`: without it the gate cannot decode a large diff and times out ("staleness unreadable", kit #154). The sha is the full 40-character sha of
  the commit the reviewer/verifier passed (kit 1.8.0); the gate refuses without it and answers `RE-REVIEW NEEDED`
  when a later push or base update touches the PR's files or a Tier A path.
- Fast delivery (owner 2026-10-16, revised by ADR-106; reasons there and in `docs/process/goal-chain.md`):
  1. Before a push: the fast checks (spec tools below, `scripts/ruff_ratchet.py`, `pr_close_check.py`, `coverage.py . --check`), the guard tests
     + `pytest -m repo_scan tests` (~75 s) and the changed files' tests. Full suites and DB tests run in CI; exceptions:
     a migration or DB store runs its own test file, a regenerated file its `--check`. Overrides kit run-discipline C3.
  2. Red CI: read the failed job log (`gh run view <id> --log-failed`), fix, push again - no local full-suite re-run.
  3. Tier by DATA FLOW. Tier A (fresh Opus, adversarial, per-PR verifier): order building/sending/state,
     reconciliation, money maths, live-data liveness, migrations, auth/tokens/secrets, hooks, and any read feeding a
     price, quantity, band, margin, fill, position or tag (any module the Execute/return routes import). Tier B (Sonnet,
     diff only; verified at requirement close): display that computes no money, history/timeline/table/catalogue/
     admin/wording. Tier C: docs. A change takes its highest-risk file's tier.
  4. Aim the first round: briefs use `docs/process/builder-brief.md` and add only the item part - reviewer checklist,
     attack cases, `Findings checked:` ids (grep the registry first), a `Threat model:` for any guard.
  5. At most 2 review rounds per item. Red CI or a failed core proof is never deferred; after round 2 a CRITICAL or
     MAJOR on Tier A code -> independent redesign or park unmerged; only MINOR/Tier B findings become deferred issues.
     Before any live run: open Tier A deferred issues triaged per ADR-107; a verifier passes on main per money/order AC.
  6. Batch: one docs PR per contract; a decision a build needs rides in that build's PR. Dependent items are stacked PRs
     (Tier A ~1,000 product lines, a migration its own PR); main merged in once, before the gate.
  7. Run independent work in parallel (builders, reviews, docs) and never wait idle on CI. Land a committed branch with
     `python scripts/orchestrator/land.py <worktree> --title T --body-file F --reviewed-sha <full sha>` (close check, push, PR, merge gate, updates
     a BEHIND branch; `--dry-run` shows the commands); `gh_issue.py app ... --stage <stage>` also stages the new issue.
  8. Merge main into a parked branch before any new round; reviewer briefs are narrow and say "hands-on attacks
     first"; commit an issue's tracker row the same turn it is filed. Before any live Kite action (API orders need a
     static IP, ADR-100) plan entry AND exit through the product path, and validate a probe on a known-good state first
     (the REST outcome is "not live" without a subscribed screen; the first live push precedes the quotes).

## Commands (fast checks before a push; full suites run in CI)
CI installs `pyyaml jsonschema pytest` on Python 3.12.
- `python tools/kit_settings.py . --check`
- `python tools/factory_lint.py .`
- `python tools/trace_check.py .` (never `--strict` in CI — it fails on any legitimately unfinished item)
- `python tools/build_findings_index.py . --check` (drop `--check` to regenerate `knowledge/findings/INDEX.md`)
- `python tools/check_spec_refs.py .`
- `python -m pytest -q -p no:cacheprovider` — `pytest.ini` sets `testpaths = tests` and `pythonpath = backend`, so
  tests import `ofo.<package>` directly; `tests/<package>/` mirrors `backend/ofo/<package>/`. One test:
  `python -m pytest -q -p no:cacheprovider tests/<package>/<file>.py::<test_name>`
- `python tools/kit_selftest.py .`
- `python tools/kit_drift.py . --ci` (add `--base <sha>` when checking a pull request against its base)
- `python tools/check_pr_spec_block.py` (pull requests only — needs the PR body)
- Merge a PR: `python scripts/orchestrator/merge.py <pr> --reviewed-sha <full sha of the reviewed commit>`
- Before merging a branch: merge `main` into it, run the changed files' tests, then
  `python scripts/orchestrator/merge_audit.py` (checks nothing was lost);
  CI re-runs both full suites on the merged result.

App layer (only when `backend/ofo_app`, `tests_app`, `frontend` or the domain changes; install `requirements-app.txt`):
- The test database is `ofo_test` on the Windows VPS PostgreSQL at 127.0.0.1:5432 (an SSH tunnel from another PC;
  local when working on the VPS itself - that PostgreSQL also serves IPODhan production, so run targeted test files
  only there and leave full suites to CI). Secrets come from the project `.env` and `GLOBAL.env` (`OFO_GLOBAL_ENV`
  overrides its default `D:\Abhay\GLOBAL.env`). Run DB commands through `scripts/orchestrator/db_run.py`, which sets the
  variables without printing them:
  `python scripts/orchestrator/db_run.py . python -m alembic -c backend/ofo_app/alembic.ini upgrade head`
  `python scripts/orchestrator/db_run.py . python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/<file>.py`
  The full app suite takes ~15 min over the tunnel: never run it locally; run a DB test file only for a migration or a
  store you changed (CI runs every DB test on its own PostgreSQL). Tests marked `network` hit Zerodha's public
  instrument list. To find which `tests_app` files a backend change can break:
  `python scripts/orchestrator/select_app_tests.py <worktree>` (exit 3 = diff not parsed; fails closed).
- `python scripts/alembic_migration_guard.py` (no empty migrations); `python scripts/generate_openapi.py --out <file>`.
- Frontend, in `frontend/`: `npm run lint`, `npm run format:check`, `npm run test:run`, `npm run build`, `npx playwright test` (needs the
  API and preview servers that `app-tests.yml` starts). Stop every server you start.

- Before pushing or touching process files, read `.claude/kit/GUIDE.md` (kit commands and kit-owned files).
