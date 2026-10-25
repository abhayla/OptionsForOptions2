# Common builder brief (OptionsForOptions2)

Template for every builder dispatch (first used overnight 2026-09-29). Each quality-bar line cites the failure that
added it; keep adding lines when a verifier finds a new class (knowledge/findings/).
Process lessons live in `docs/process/row-review.md` (L1-L19; per-item log per the kit deliver skill's step 10, ADR-189).
Size every brief by the files the fix must touch (L3): <= 5 files S (30 min / 40 calls), 6-15 M (60 / 80), more or
backend + frontend L (split backend then frontend). The orchestrator copies the start check's or Measure's attack list
into the brief as `Attack list:` (L1).
A specific brief carries only the item part (Core/Proof, quoted Spec basis, Copy from, ACs, attack cases, threat model,
tier, the `Standing items:` line (section below), and the literal `Budget:` / `Report:` / `Tests:` lines, which the
dispatch hooks read from the prompt text) and
says "Common brief: docs/process/builder-brief.md". A fix-round brief is the review's findings plus the original
attack list, not a rewrite (ADR-106 item 9).

## Tiers, safety set and round 2 (ADR-189, ADR-106 (1), ADR-178 (1))
**Tiers** - Tier A (a safety-set file changed): builder + one Opus checker; Tier B (other code): builder + one Sonnet
checker; Tier C (docs, records, test-only): CI only. One checker replaces verifier plus reviewer. At most 2 rounds;
after round 2 a CRITICAL or MAJOR on Tier A parks the item unmerged, anything else ships with its findings listed. No
automatic independent review. Mutation tests: Tier A guards only, at most 5 mutants, run by the builder on a scratch
copy; not a gate.
**Safety set** - a changed file under any of these makes the item Tier A, whatever the row's Tier column says (the
list is `SAFETY_SET` in `scripts/orchestrator/safety_set.py`; change both together): `backend/ofo/engine/`, `backend/ofo/scenario/`,
`backend/ofo/table/`, `backend/ofo/outcome/`, `backend/ofo/marketdata/`, `backend/ofo/feed*`, `backend/ofo_app/kite_ws*`,
`backend/ofo_app/feed*`, `backend/ofo/broker/`, `backend/ofo_app/kite_*`, `backend/ofo_app/routes/auth*`,
`backend/ofo_app/broker_sessions*`, `backend/ofo/orders/`, `backend/ofo/execution/`, `backend/ofo/reconciliation/`,
`backend/ofo_app/alembic/`, `scripts/hooks/`. An Opus dispatch names the safety-set file in its `Why Opus:` line.
**Round-2 checker brief** (findings-only, ADR-178 (1)): `Round 2 findings:` with round 1's numbered findings, `Changed
files:` with the fix commit's files, the attack items those findings touch, `Budget: 15 min wall-clock, 20 tool calls`.
A full re-check only when the fix touched a safety-set file round 1 did not see - the brief says which.

You build ONE work item in your own git worktree of github.com/abhayla/OptionsForOptions2 (branch from origin/main).
Read first, in order: your `work/W-###.md`; its requirement `spec/requirements/REQ-###.md` (acceptance criteria);
every ADR that requirement cites; `CLAUDE.md` (hard rules); for engine work `spec/business-rules/scenario-calculations.md`.

## Hard constraints
- **Stack (ADR-043):** Python 3.12+. Code under `backend/ofo/<area>/`, tests under `tests/<area>/`. `pytest.ini` already
  sets `pythonpath = backend`, so tests import `ofo....`.
- **Dependencies:** standard library only (+ PyYAML if needed). CI installs only `pyyaml jsonschema pytest` and its
  workflow is a kit file we cannot change. No numpy, no scipy, no FastAPI in this item.
- **Money = `decimal.Decimal`** end to end; never float for any rupee or price value. Quantities are integers (units =
  lots x lot size). Construct Decimals from strings, never from floats. Floats are allowed only inside a numeric model
  (e.g. Black-Scholes math) and converted to Decimal at the boundary with explicit rounding.
- **Hard rules (CLAUDE.md):** every order belongs to a strategy; one engine owns every P&L number; decision-support
  wording only; Zerodha is the authority; no automatic retry.
- **Kit files are read-only**: `.claude/`, `tools/`, `factory/`, `.github/`, `KIT_VERSION`. A hook blocks any shell
  command whose text names them — read them with Read/Grep/Glob only, and run `python tools/<x>.py .` as a bare command
  from the repo root, no pipes or redirects.
- **Legacy copy (ADR-043, spec/technical-design/legacy-reuse.md):** if you copy or adapt legacy code, the file starts
  with a comment naming source repo, commit and path, e.g. `# Adapted from abhayla/algochanakya@2a868db
  backend/app/services/instrument_master.py`. The local checkout is the `algochanakya` folder next to this repo's
  checkout (READ ONLY: never edit, commit or run anything there).
- Never write under `evidence/`; never set a work item/requirement status to done/verified.

## Rules in your brief
Every product rule in your specific brief should quote the spec text it rests on. A rule marked "orchestrator default"
or given without a spec quote is NOT settled: check it against the spec and the owner-reviewed transcripts, and if
the source says otherwise, build to the source and report the conflict (finding brief-rule-from-memory: 5 brief
rules were wrong tonight).
The orchestrator runs `python scripts/orchestrator/check_brief.py <brief-file>` on every brief before dispatch; a quote
that is not verbatim in the spec text it cites fails the brief (work item W-040).

## Two lines every brief carries (check_brief.py fails the brief without them)
- A test-commands line naming the repo-wide guard tests, all four literals on one line (the fourth runs every
  `repo_scan`-marked scan test, finding `repo-wide-scan-outside-targeted-tests`):
  `Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests` (GC-2c: W-091, W-092 and W-098 each hit the producer scan in CI only.) (PR #310 and
  #316 skipped them.)
- A Tier A brief about a guard/door/gate/scan (one of those words in its first 10 lines) carries
  `Findings checked: <id>, <id>` where each id is a file `knowledge/findings/<id>.json` (W-080 round 10 was designed
  without reading `guard-by-banned-shapes`). Grep the registry first; "grep findings" is not a list.
- A brief that adds or changes a guard carries `Threat model: in scope <...>; out of scope <...>` BEFORE round 1
  (ADR-106 item 2; W-080 ran 10 rounds until ADR-098 put forged code objects out of scope). The reviewer attacks only
  what is in scope; a finding outside it is recorded, not a new round.

- A brief naming any `REQ-###` (builder or verifier) carries a `Reference:` line right after `Copy from:` (ADR-173,
  label per ADR-176 (4); check_brief.py refuses the brief without it; a brief naming no requirement is exempt). New
  text says "reference product", never its name. Two accepted forms:
  `Reference: screens 209-211 - copy the price-changed marker` (study screen numbers, three digits, plus a word
  saying what is copied: copy / copies / copied / same as), or
  `Reference: none - searched reconnect, stale feed` (at least two search terms) when the study has no such screen.
  `none`, `n/a` or an empty line is refused.
  Open-record rule (ADR-176 (2)): every open record that `python scripts/orchestrator/reference_register.py --open
  REQ-###` returns for a requirement the brief names is written on the `Reference:` line, e.g.
  `Reference: catalogue 100, 134 - copy the days-left label; open RD-001`. A brief that drops one is refused, and so
  is any brief naming a requirement while the register is invalid. The records live one per file in
  `spec/reference-diffs/`; the owner's page is `docs/process/reference-differences.md` (`--render`; CI fails a stale
  page). A row does not close while `--close-check REQ-###` exits 1.

## Standing items (kit run-discipline C4 (a)-(d), #444): every build brief carries these four
Each came from a real "revise" verdict. The SPECIFIC brief carries one line `Standing items: (a) ... (b) ... (c) ...
(d) ...`, each item either applied to this work or `n/a: <reason>` (e.g. "(a) n/a: no time-budgeted job"); a bare
"n/a" is a brief defect, and the reviewer confirms every n/a reason against the diff.
- **(a) Time budget:** a new pass inside a time-budgeted job reuses the job's existing small reservation, never the
  whole remaining budget, and a test shows the higher-priority work still runs.
- **(b) CI install order:** a CI step that gains a non-builtin import runs after the dependency install step.
- **(c) Static detectors fail closed:** a detector fails closed on shapes it cannot resolve (re-exports, renamed
  imports, same-named local functions) and names its guard by import source, not by identifier text.
- **(d) Every answer state of another system:** when a feature decides on another system's answer (Kite, NSE, the
  database), the brief lists every answer state - stated, absent, not found, failed, empty, ambiguous - and what each
  does. Example: GC-3L met Kite's `InputException` "tag should be max 8 characters", a state no brief had listed.

## Quality bar (the reviewer will check exactly this)
- **Database tests outside your files** (finding db-tests-outside-the-row-red-only-in-ci, 2 occurrences): if your diff
  touches `backend/ofo_app/alembic/`, a `*_store.py` or a route's reply, run EVERY database test
  `select_app_tests.py` selects plus every `tests_app/test_migration_*.py` and `tests_app/test_strategy_shape_matrix.py`
  through `scripts/orchestrator/db_run_fresh.py <worktree> python -m pytest -q -p no:cacheprovider -c pytest-app.ini
  <files>` (a throwaway database; never the shared ofo_test) before reporting. A migration that re-creates a validator
  publishes `NEW_PINS`.
- **Local checks before PASS (ADR-189):** run `python tools/ci_local.py` on your clean worktree after your last
  commit and paste its last 5 lines; a report or a checker PASS without them is not a pass. CI runs the full suites.
- **Test doubles from the real thing** (finding test-double-encodes-old-assumption, #532 C1): every stand-in model,
  fake server or socket fake is built from the real class (same base, e.g. ApiModel) or checked against the real
  server's behaviour; a Playwright spec that answers `**/api/strategies/live` itself stamps every push with
  `frontend/e2e/support/echoSeq.ts` (repo test `tests/test_e2e_live_socket_fakes.py`).
- Step 1 is the work item's **Core/Proof**: make that one test pass on the real input first, then build the rest.
- **Run the brief's `Attack list:` yourself before reporting** (row-review.md L1, 2026-10-22: row 2's round 1 failed on
  an attack nobody listed, "a heartbeat alone must not count as a price"). Each item gets a test or a scratch run
  and a line in the report.
- **Run every changed test file in full, never a `-k` subset** (row-review.md L2: two stale tests reached the verifier).
  DB-backed `tests_app` files run through the MAIN checkout's `scripts/orchestrator/db_run.py <your worktree> python
  -m pytest ...` (a worktree has no `.env`); a skipped DB test is NOT run and is reported as skipped. Grep every test
  tree for the old value or answer of anything you changed.
- **Mutation checks (Tier A guards only) use scratch copies only**, never an in-place edit of a checked-out file
  (L4). Run `python scripts/orchestrator/mutation_gate.py` on at most 5 mutants of each guard you add or move and quote
  its results file (L18). Not a merge gate.
- **Run the app tests your change can break** (row-review.md L13; row 7 found a row-5 stale test in a file nobody ran):
  for every backend file you change, list the `tests_app` files that import it or call its routes
  (`scripts/orchestrator/select_app_tests.py` does this for a whole branch; for your own commits grep the importers),
  run them all through the throwaway-database runner, and list them in your report.
- **A cache or memo key is built from the call it guards** (row-review.md L14; row 8, 2026-10-22: 30 of 40 key parts had
  no killing test, so a later edit dropping one would serve stale figures with every test green): one helper takes the
  computation's exact arguments and returns key + result; a test changes one input at a time and asserts a recompute.
- **Every caller of a changed entry point** is named in the brief and tested (row-review.md L15; row 8 missed two routes).
- **DB-backed app runs start first**, in the background, with `-o faulthandler_timeout=60`, and the report gives their
  timing (row-review.md L16; ~23 s per DB test over the tunnel).
- **The `Budget:` is a hard stop** (row 4, 2026-10-22: a builder used 152 tool calls on an 80-call budget, hit the
  100-turn hard limit and stopped mid-rename with uncommitted files). At 80% of the calls (64 of 80, 32 of 40):
  start no new change; finish or revert the one in hand so the tree is consistent; commit; report done / not done /
  next command. Never leave a rename or a refactor half applied.
- One test per AC in `tests_required`; each test's docstring starts with the AC id (e.g. `"""AC-3: ..."""`).
- Assert exact values (Decimal equality), not "is not None" or ranges, wherever the spec gives a number.
- **Expected values come from the spec or an independent hand computation, never from running your own code and
  pasting its output into the assertion** (W-004 and W-016 tests locked in wrong behaviour this way: leg Greeks in
  different units from the total; history labels attached to the wrong snapshot). For every assertion, be able to say
  where the expected value comes from; add a consistency test where one exists (e.g. leg rows sum to the total row).
- Include at least one negative / red case per rule (input that must be rejected or must produce the other branch).
- Fail closed: invalid input raises a clear `ValueError` (or a domain exception), never silently defaults.
- **Input-domain checklist** (added after W-007's adversarial review found 4 MAJOR holes here): for every public
  constructor/append/import, test and reject: duplicates of the same logical item (same reference twice), absurd sizes
  (huge counts/durations — cap them), timestamps too far in the future or backdated effects, unknown keys in data files
  (never ignore a misspelled key), timezone-naive datetimes, and a raw state change that bypasses the proper method.
  Also: one-by-one append of 1,000 items must stay fast (no re-validating the whole history each time).
- **Never trust a caller-supplied verdict or identity** (finding `caller-supplied-verdict-trusted`: W-014 accepted a
  self-computed legs hash, W-020 a caller-passed "active" version, W-027 a hand-built passing SafetyResult). If a step
  depends on a check having run (gate, reconciliation, version state), your code CALLS that check or reads the owning
  object itself; a public API never accepts the check's result object from outside. Test it: a forged passing result
  must be impossible to inject.
- **Every guard has a test that dies without it** (W-021 M3/M5, W-023 M2/M3, W-027 grounding all survived with the
  suite green): list every safety guard you wrote (each `if ...: raise/refuse/block`), delete it in a scratch copy,
  and name the test that goes red. A guard with no killing test is unfinished work; report the list.
- **"Pre-existing" is proven on origin/main, never on your branch** (W-024 blamed its own regression on old code by
  loading its own HEAD): run the failing test on a clean checkout of origin/main and paste that result, or fix it.
- **A guard is an allow-list, never a list of forbidden things** (finding `guard-as-forbidden-list`, 2026-10-09:
  W-061 round 2's jsonpath CHECK refused 13 named bad shapes and accepted arrays and prices in leg slots; W-066's slot
  detection test forbade 4 named slot types and let `Quoted` through): a check states what IS allowed (exact key sets,
  a closed type per slot, a closed name list) and refuses everything else; its test enumerates the allowed shape and
  every other type, generated, not hand-listed. A guard written as "refuse X, Y, Z" fails review.
- **Grid values come from the grid** (W-025: pick-list steps offset from an unaligned level missed every strike):
  any value a user can pick that must be a strike/level is snapped to, and asserted against, the real catalogue.
- **A changed shown value is searched in every test tree** (W-075, 2026-10-16: two CI rounds on e2e lines nobody
  named): before editing, grep `tests/`, `tests_app/`, `frontend/tests/` and `frontend/e2e/` for the OLD value and
  update every hit; money leaving the API is a 2-decimal string (W-075 sent "4539.65173942700").
- **Money and order checks are tested with closing shapes too** (finding `margin-gate-blocks-closing-basket`, #321:
  Kite gives an exit basket a negative margin and the gate blocked every exit): every check that reads a broker figure
  gets an entry case AND a closing/position-reducing case from a real reply.
- **A change to any API request/response model regenerates `docs/api/openapi.json`** (`python
  scripts/generate_openapi.py`) in the same PR: `test_committed_openapi_matches_the_app` fails otherwise. This is the
  one exception to "no regenerated files" (GC-2e: W-105 and W-102 both went red on it). A NEW `ApiModel` class is
  also registered in `tests_app/test_response_door.py` (the pinned set and its count) and that file is run (GC-2g:
  W-111's four Positions models turned CI's `api` job red).
- **A migration's `upgrade()`/`downgrade()` call `op.*` directly** (`scripts/alembic_migration_guard.py`), and a
  migration that changes a pinned function body publishes its own `PINNED_BODIES` (GC-2e W-103: two CI reds).
- **After merging main into your branch, re-run `python scripts/ruff_ratchet.py`** (E501 rose twice on 2026-10-16 only
  after the merge).
- Type hints on public functions; small modules; no dead code; no print statements.

## Before you finish
Run from your worktree root, each as its own command (the fast pre-push set, ADR-106 item 11; CI runs the full
suites): your brief's `Tests:` line (guard tests + `-m repo_scan` + your changed files' tests) ·
`python scripts/ruff_ratchet.py` · `python tools/factory_lint.py .` · `python tools/trace_check.py .` ·
`python scripts/orchestrator/coverage.py . --check` (~5 s; a NEW work item or issue needs its row in
`docs/process/coverage-stages.yaml`, else CI's coverage job goes red - W-112, 2026-10-18)
On the Windows VPS (its PostgreSQL also serves IPODhan production; owner decision 2026-10-09) run only the targeted
test files your brief names plus `python scripts/orchestrator/atool.py <worktree> <W-id> --no-tests` (every ci.yml
lint step); CI runs the full suites. Before the targeted run, grep `tests/` and `tests_app/` for every route, status,
code and message your change touches and add every file that names one (finding `targeted-tests-miss-dependent-files`:
#163 broke a test in a file nobody ran).
Commit (WIP commits are fine as you go) and `git push -u origin <your-branch>`. Do NOT open a PR — the orchestrator
does that after independent verification.

## Report (under 300 words)
Branch name and the PUSHED head SHA; `git status --short` output (must be empty: finding
`builder-report-describes-uncommitted-work`); files changed; the exact test command and its result line; which AC each test file covers;
anything not done and why; an evidence table `| Claim | Evidence (tool call this run) |`.
Report: evidence-table
