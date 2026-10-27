# Runbook: build, test, brief, merge

Moved out of `CLAUDE.md` by ADR-189 (kit 1.14.0, 8 KB always-loaded cap). Process decisions live in the ADRs; this page
says how to run them. Kit commands and kit-owned files: `.claude/kit/GUIDE.md`.

## How the repo fits together
- Traceability chain, checked by `tools/` and CI: `spec/decisions/ADR-###.md` -> `spec/requirements/REQ-###.md`
  (acceptance criteria) -> `work/W-###.md` (`tests_required` covers the ACs) -> code + tests ->
  `evidence/<W-id>/<AC-id>.md` (written by the orchestrator from the checker's reply, never by the builder) ->
  `releases/R-###.md` (rollback written before any deploy). Every artifact is Markdown + YAML frontmatter validated by
  `factory_lint.py`; `trace_check.py` refuses a broken chain or evidence whose `verified_by` is the builder.
- Two code layers. `backend/ofo/` is the domain (engine, scenario, strategy, orders, execution, reconciliation, ...):
  standard library only, tested in `tests/` against fakes. `backend/ofo_app/` is the FastAPI app (routes, PostgreSQL
  stores, Alembic migrations in `backend/ofo_app/alembic/`, Kite clients), tested in `tests_app/` with `pytest-app.ini`.
  `frontend/` is Vue 3 + Vite + Pinia + Tailwind: Vitest unit tests, Playwright e2e against `vite preview` proxying
  `/api` to the real API. The app job is `.github/workflows/app-tests.yml` (project-owned).
- Database tests run as the limited `ofo_app` role (ADR-048); migrations as the owner role. Money stays `Decimal`,
  `NUMERIC` in the DB and a string in API output (`.claude/rules/project/decimal-money-boundaries.md`).
- Real Kite data reaches tests only as recorded fixtures (`tests/fixtures/kite_ws/`, `tests/fixtures/kite_history/`);
  `APP_ENV=test` + `OUTCOME_REPLAY=1` serves recorded frames to the outcome route for e2e.
- Repo-wide guard tests sit at the top of `tests/`; `views/` is generated output, never hand-edited.
- `knowledge/findings/*.json`: one file per failure class; index by `build_findings_index.py`; each `spec_ref` must
  resolve (`check_spec_refs.py`).
- The Claude settings file is GENERATED: edit `.claude/project/hooks.json` or `.claude/project/optouts.json`, then run
  `python tools/kit_settings.py .`. Project rules go in `.claude/rules/project/`, with `paths:` frontmatter.
- The production seatbelt lives in the project's hidden Factory folder and is owner-edited only; a hook blocks any tool
  call naming its paths, so describe it, don't path it.

## Delivery (kit `deliver` skill, ADR-189)
- Tier by the changed files. Tier A = ADR-106's safety set (order building/sending/state, reconciliation, money maths,
  live-data liveness, migrations, auth/tokens/secrets, hooks, and any module the Execute/return routes import; the
  machine list is `SAFETY_SET` in `scripts/orchestrator/safety_set.py`): builder + one Opus checker. Tier B (other
  code): builder + one Sonnet checker. Tier C (docs, records, test-only): CI only. A change takes its riskiest file's tier.
- At most 2 rounds; round 2 re-checks only round 1's findings and the fix's files (15 min / 20 calls). After round 2:
  a CRITICAL or MAJOR on Tier A parks the item unmerged; anything else ships with the findings listed (deferred
  issues). Red CI or a failed core proof is never deferred. No automatic independent review.
- Draft PR first (ADR-191 (2)): a diff that touches a migration, an API reply model or a strategy-socket message is
  pushed as a draft PR; the checker starts only after that head's App tests run is green. Everything else keeps
  ADR-189 (CI after review).
- Mutation tests: Tier A guards only, at most 5 mutants, run by the builder on a scratch copy
  (`scripts/orchestrator/mutation_gate.py`); not a gate.
- After each item (deliver step 10): record minutes, rounds and the cause of each extra round in
  `docs/process/row-review.md`, and apply the fix that removes the cause the same turn.
- Token and time measuring: `python tools/measure_tokens.py --since <YYYY-MM-DD>`.
- No requirement or code before the ADRs it rests on exist. Nothing pending is closed until it is implemented and
  checked. New owner questions are numbered Q204+ in `spec/open-questions.md`; never decide one silently.
- Before any new round on a parked branch, merge main into it and run the guard tests. Checker briefs are narrow and
  say "check against the REQ/ADR text, not this brief; hands-on attacks first". Commit an issue's tracker row the turn
  it is filed. Run independent work in parallel; never wait idle on CI.

## Briefs and dispatch
- Briefs use `docs/process/builder-brief.md` for the constant parts. Every builder/checker brief goes through
  `python scripts/orchestrator/dispatch.py <row> <measure.json> --kind build|fix|verify-r2 --out <brief>
  --worktree <wt> (--in-flight <wt>=<ref> | --no-in-flight)`: it renders with `make_brief.py`, then runs
  `check_brief.py` (spec quotes verbatim, finding brief-rule-from-memory) and `copy_from_check.py` (every
  legacy-reuse map row for the brief's requirements, ADR-047) and `overlap_gate.py`, and refuses a third fix round.
  A hand-written brief runs the two checks itself:
  `python scripts/orchestrator/check_brief.py <brief> && python scripts/orchestrator/copy_from_check.py . <brief>`.
- Every brief carries `Copy from:` (legacy-reuse map rows, ADR-047), `Sensibull:` (screen numbers, ADR-173),
  `Budget:`, `Report: evidence-table`, and: "no new duplicated literal; reuse the existing helper; ruff/mypy baselines
  must not rise; targeted tests only; no regenerated files in the PR".
- Builder worktrees live under the `.claude` folder; reach them through the helpers: `agit.py <agent-id> <git args>`,
  `atool.py <agent-id>`, `agentwt.py <agent-id> status|release`, `aregen.py <agent-id>` (regenerate the findings index
  in a worktree and continue a paused rebase), `regen.py [dir]` (findings index, spec digest, build order),
  `dev_run.py <cwd> <command>` (DATABASE_URL = ofo_dev only, ADR-078).
- Evidence: `python scripts/orchestrator/ev_agent.py <agent-id | worktree> <reply.json>` (refuses while a checker is in
  flight, then runs the kit's `tools/record_evidence.py --root <worktree>`).
- Issues: `python scripts/orchestrator/gh_issue.py kit|app ... --stage <stage>` (a bare `gh issue create` breaks the
  coverage check).

## Before a push
One command, the whole list on a committed, clean tree: `python scripts/orchestrator/prepush.py` (`--full` after a
large merge). It runs ci_local, the ruff ratchet, the coverage check and the alembic guard, plus, when the change
touches `frontend/`, `npm run lint`, vitest (the changed files' tests; all with `--full`) and `npm run build` in
`frontend/` (needs `frontend/node_modules`: a missing one is a FAIL). It writes the marker that `git push` and
`land.py` require for that exact HEAD only when every step passed, the tree was clean from start to end, HEAD did not
move and no untracked file sits under backend/, tests*/, scripts/ or frontend/src/ (an amend needs a new run). A push
whose folder the gate cannot find is refused. Bypass, with a reason:
`PREPUSH_GATE_ALLOW=<reason> git push ...` or `land.py --skip-prepush <reason>`.
Underneath, `python tools/ci_local.py` (`--full` after a large
merge) mirrors the kit's `ci.yml` only; `app-tests.yml` (tests_app, frontend lint/unit/e2e, ruff ratchet) runs in
CI. Add, when relevant: `python scripts/ruff_ratchet.py`; `python scripts/orchestrator/pr_close_check.py --pr N`;
`python scripts/orchestrator/coverage.py . --check`; a migration or DB store runs its own test file (below); a
regenerated file its `--check`. Red CI: read `gh run view <id> --log-failed`, fix, push again.

## Merge
- Only `python scripts/orchestrator/merge.py <pr> --reviewed-sha <full 40-char sha>` (or `land.py <worktree> --title T
  --body-file F --reviewed-sha <sha>`, which also pushes, opens the PR and updates a BEHIND branch). Never
  `gh pr checks --watch && gh pr merge`. The gate answers `RE-REVIEW NEEDED` when a later push touches the PR's files
  or a Tier A path.
- Before merging a branch: merge `main` into it, run the changed files' tests, then
  `python scripts/orchestrator/merge_audit.py`.
- PR body: the Spec-deviation block (`Class: none` is valid). Never put fix/close/resolve before `#N` except a whole
  `Fixes #N` line when ALL of the issue is done; for part of one write "addresses item 1 of #N" (`pr-close-check`).
- Batch: one docs PR per batch; dependent items as stacked PRs (Tier A ~1,000 product lines; a migration its own PR).

## Spec and records
- Before any new spec line: `python tools/spec_similar.py . "<text>"`.
- Kit commands (lint, trace, findings index, spec refs, selftest, drift, PR spec block): `.claude/kit/GUIDE.md`.

## App layer and database
- Test database `ofo_test` on the Windows VPS PostgreSQL at 127.0.0.1:5432 (SSH tunnel from another PC). That
  PostgreSQL also serves IPODhan production: targeted test files only, full suites in CI. Secrets from the project
  `.env` and `GLOBAL.env` (`OFO_GLOBAL_ENV` overrides `D:\Abhay\GLOBAL.env`); run DB commands through
  `scripts/orchestrator/db_run.py`, which never prints them:
  `python scripts/orchestrator/db_run.py . python -m alembic -c backend/ofo_app/alembic.ini upgrade head`
  `python scripts/orchestrator/db_run.py . python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/<file>.py`
- Which `tests_app` files a backend change can break: `python scripts/orchestrator/select_app_tests.py <worktree>`
  (exit 3 = diff not parsed; fails closed). Tests marked `network` hit Zerodha's public instrument list.
- `python scripts/alembic_migration_guard.py` (no empty migrations); `python scripts/generate_openapi.py --out <file>`.
- Frontend, in `frontend/`: `npm run lint`, `npm run format:check`, `npm run test:run`, `npm run build`,
  `npx playwright test` (needs the API and preview servers `app-tests.yml` starts). Stop every server you start.

## Live Kite
Before any live Kite action (API orders need a static IP, ADR-100) plan entry AND exit through the product path, and
validate a probe on a known-good state first. Kite API facts: the user-level `zerodha-expert` skill. Engine-math
reviews: the project skill `options-math-review`.

## Reference
- `docs/reference/chatgpt/`: the two chat transcripts (primary) and handoff files; reference only, never edited;
  `spec/` wins (ADR-031). Map: `spec/traceability/source-map.md`.
- Legacy repos (`abhayla/algochanakya` main source; `OFO`, `NewOFO`, `OptionsForOptions` reference) are never edited;
  copied code names its source repo, commit and path, meets every hard rule and gets its own tests
  (`spec/technical-design/legacy-reuse.md`, pinned to `bf9faf7`). The engine and order execution are built new.
- Coding standards (REQ-075, ADR-093): a standard is an automatic check or marked review-only; real-world values have
  one home module; per-technology rules load by path from `.claude/rules/project/`.
