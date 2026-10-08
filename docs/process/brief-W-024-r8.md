# Builder brief: W-024 round 8 - error messages with the allowlist guard (ADR-056 item 1)

Core: every one of the 12 REQ-065 error classes renders a message with four filled parts through the one builder
function, and no code in backend/ofo can change the wording checker without the CI scan or the runtime identity check
refusing it.
Proof (step 1, before anything else): on the rebased branch, run `python -m pytest -q -p no:cacheprovider tests/errors
tests/test_wording.py` and show it green; then show the two round-7 escapes from issue 30 (`from .. import wording;
wording.find_advice_wording = f` and `importlib.import_module("ofo.wording").x = f`) each FLAGGED by the new scan.

Why Opus: Tier A guard meant to be hard to bypass; seven earlier rounds failed on unlisted code shapes.
Budget: 60 min wall-clock, 120 tool calls. At budget stop after a commit and report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`).
Tier: A (the deliver tier table: "any check meant to be hard to bypass"); the work item's tier is raised to A in this PR.
Class: wording-guard bypass - any route by which code in backend/ofo changes, replaces or skips the advice-wording
checker, or puts forbidden wording into a platform message.
Copy from: none - algochanakya has no error catalogue or wording checker (W-024 rounds 1-7 built it new).

## Spec basis
- REQ-065 AC-1: "Errors are classified at least as: user input, strategy validation, market data, broker authentication,
  broker eligibility, margin, order rejection, partial execution, reconciliation mismatch, notification, entitlement/access,
  internal system."
- REQ-065 AC-2: "Every user-facing error states what happened, the impact, what is blocked and the next action."
- ADR-056 decision (1): "W-024 (error messages, GitHub issue 30) is unparked and built in Stage 4a with the allowlist design - no
  attribute assignment on any imported module in backend/ofo plus a runtime identity check of the wording checker."
- ADR-003 Q226, Q230, Q231 (bare-word ban on "best", "sure", "safe", "guarantee*", "recommend*" in every word form;
  exceptions exactly "best bid", "best ask", "best-case", "make sure", "safety", "safety check", "safety checks",
  "safety gate"; "must", "have to", "ought to" allowed).
- ADR-003 Q235: the checks "stop accidental misuse by the platform's own code" and "are flagged in CI when code reaches into
  their internals"; deliberate runtime replacement is out of scope beyond the CI flag and the ADR-056 identity check.
- ADR-003 Forbidden list includes "any promise of returns or of reduced losses".

## Start
1. Your worktree starts from main. Check out `origin/build/W-024-error-catalogue` (a3ef79a, round 7) as a new local branch
   `build/W-024-r8` and rebase it onto `origin/main` (main is 249 commits ahead). Resolve conflicts keeping main's
   behaviour everywhere outside W-024's files; re-run the full domain suite after the rebase and report the count.
2. Read issue 30's last two comments (`gh issue view 30 --comments`) - they list every round-7 escape you must close.

## What to build
1. **Allowlist scan (replaces the round-7 denylist of shapes).** A test over every `.py` file in backend/ofo (AST):
   - an attribute assignment, augmented assignment or `del` is allowed ONLY when the target is `self.<name>` or
     `cls.<name>` (any depth below that: `self.a.b = x` is allowed only if `self.a` is not a module - keep it simple:
     allow `self`/`cls` roots only). Every other attribute target (`x.y = ...` with any other root) fails, whatever the
     import form (absolute, relative, aliased, `importlib`, a variable holding a module).
   - calls to `setattr`, `delattr`, `vars`, `globals`, `importlib.import_module`, `__import__`, `exec`, `eval`, and any
     `.__dict__` or `__setattr__` access fail, except `object.__setattr__(self, ...)` inside a frozen dataclass
     `__post_init__` (name the exact allowed shape).
   - Existing backend/ofo code that breaks this rule: list each hit in the report; change the code to fit (e.g. a
     dataclass field instead of a module attribute) or add it to a NAMED allowlist entry (file, line pattern, reason).
     The allowlist entries are the only exceptions and the test prints them.
   - Keep the round-7 test-tree checks (`monkeypatch.setattr` on `ofo.wording` / `ofo.errors*` in tests/ is flagged).
2. **Runtime identity check.** At import, the builder function captures the checker function objects AND their
   `__code__` objects; on every message build it refuses (raises, fail closed) when either differs from the captured
   one. A test rebinds `ofo.wording.find_advice_wording` (via monkeypatch, in the test only) and asserts the next build
   raises.
3. **Promise phrases:** add the round-7 residuals to the shared check, every word form: "returns are assured",
   "losses are minimised/minimized", "riskless", "won't lose", "will not lose", "loss-free", "profit is certain" (spec:
   "any promise of returns or of reduced losses"). Near-miss tests stay clean ("risk", "loss" alone are allowed).
4. **Work item correction (class 1):** `tests_required` names `tests/errors/test_catalogue.py`; the file is
   `test_error_catalogue.py`. Correct work/W-024.md in this PR; set `status: in_progress`, `tier: A`,
   `next_action: "round 8 (ADR-056 item 1): allowlist scan + runtime identity check"`.

## Standing items (run-discipline B4) and reviewer checklist
- Mutation tests FIRST for each guard: removing the self/cls allowlist, removing one banned call name, removing the
  `__code__` comparison, removing one promise phrase - each must turn a test red. List each mutant and its red test.
- Fail closed: an AST node the scan cannot classify fails the scan with the file and line.
- The scan names its guard by the AST shape, never by identifier text alone.
- Expected values from the spec text above, never from running the code.
- Kit CI stays green: tests/ imports no app packages; no wall-clock asserts.

## Rules
- Do not edit kit files or spec/. Never write `evidence/`. No secrets. Never mark anything verified or reviewed.
- Run `python -m pytest -q -p no:cacheprovider` once at the end (full domain suite, output to a log file, tail only).
- Commit; do not push. Report worktree path, branch, commits, the allowlist entries and the mutant table.
