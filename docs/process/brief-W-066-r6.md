# Builder brief: W-066 round 6 - FINAL bounded round (owner decision 2026-10-09): two reproduced defects only

Core: the outcome never crashes on a loss region narrower than a paisa, and the `LevelRegions` slot accepts only a
well-formed region list.
Proof (step 1, red first against 437f747): (1) BUY 3 lots NSE_FO:44602 (22400CE) @0, BUY 3 lots NSE_FO:44604
(22400PE) @0, BUY 1 lot NSE_FO:44595 (22200PE) @0.01 through `build_outcome` raises `ValueError: a level region needs
lower < upper` today (reproduced by the orchestrator); (2) `LevelRegions` accepts unordered ((5,10),(1,3)), overlapping
((1,10),(5,20)), duplicate, an open lower end that is not first, an open upper end that is not last, and
`Decimal("2.24E+4")` today (verifier). A test for each, red, then green.

Tier: A. Model: sonnet/medium (kit routing: builder, always).
Budget: 20 min wall-clock, 30 tool calls. Commit; at budget stop after a commit and report.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~200 words.
Copy from: none.

## Scope (owner: one final round; any red after it parks W-066)
Fix ONLY these two. Do not refactor, rename or touch anything else.

1. **Sub-paisa region** (`backend/ofo/engine/metrics.py` `_loss_regions` or where regions are rounded for display):
   after rounding the edges to 0.01, a region whose two rounded edges are equal is kept and rendered as a single
   level ("If NIFTY ends at 22,400.00 at expiry." - one new list part "at X" inside the existing regions sentence, or
   joined with the other parts as usual), never dropped and never a crash (ADR-072 on this branch: every loss region is
   named). Adjacent rounded regions that touch or overlap after rounding are merged. The slot accepts a point part.
   Test: the reproduced strategy returns a COMPUTED outcome with that sentence; the property test still passes.
2. **`LevelRegions` slot** (`backend/ofo/errors/explanations.py`): refuses unordered, overlapping, duplicate or
   touching-but-unmerged intervals; an open lower end (None) only on the first interval, an open upper end only on the
   last; every bound a Decimal in plain notation (refuse exponent form) within the existing Points bounds. Tests for
   each case, plus the accepted forms (the five counterexample sentences still render).

## Spec basis
- REQ-034 AC-7: "Outcome numbers appear in plain language first"

## Rules (this PC also serves IPODhan production's database)
- Targeted tests only, one directory per pytest call: from the worktree `python -m pytest -q -p no:cacheprovider
  tests/engine`, then tests/outcome, tests/errors; from `C:\Abhay\Ventures\OptionsForOptions2`:
  `python scripts/orchestrator/db_run.py C:\Abhay\Ventures\OptionsForOptions2-W-066 python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_outcome_catalogue.py tests_app/test_outcome_route.py`;
  CI mirror `python C:\Abhay\Ventures\OptionsForOptions2\scripts\orchestrator\atool.py C:\Abhay\Ventures\OptionsForOptions2-W-066 W-066 --no-tests` (every step rc 0).
- Kit guard: shell text must not name .claude, tools/, spec/requirements, .github or views. Do not edit kit files or
  `spec/`. Never write `evidence/`. Never mark anything verified. Push `build/W-066-on-main`.
