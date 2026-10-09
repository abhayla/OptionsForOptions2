# Common builder brief (OptionsForOptions2)

Template for every builder dispatch (first used overnight 2026-09-29). Each quality-bar line cites the failure that
added it; keep adding lines when a verifier finds a new class (knowledge/findings/).

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

## Quality bar (the reviewer will check exactly this)
- Step 1 is the work item's **Core/Proof**: make that one test pass on the real input first, then build the rest.
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
- Type hints on public functions; small modules; no dead code; no print statements.

## Before you finish
Run from your worktree root, each as its own command:
`python -m pytest -q -p no:cacheprovider` · `python tools/factory_lint.py .` · `python tools/trace_check.py .`
On the Windows VPS (its PostgreSQL also serves IPODhan production; owner decision 2026-10-09) run only the targeted
test files your brief names plus `python scripts/orchestrator/atool.py <worktree> <W-id> --no-tests` (every ci.yml
lint step); CI runs the full suites.
Commit (WIP commits are fine as you go) and `git push -u origin <your-branch>`. Do NOT open a PR — the orchestrator
does that after independent verification.

## Report (under 300 words)
Branch name and head SHA; files changed; the exact test command and its result line; which AC each test file covers;
anything not done and why; an evidence table `| Claim | Evidence (tool call this run) |`.
Report: evidence-table
