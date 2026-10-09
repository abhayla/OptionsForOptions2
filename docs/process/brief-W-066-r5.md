# Builder brief: W-066 round 5 - loss regions from the payoff (independent review, ADR-072)

Core: the engine exposes the strategy's expiry LOSS REGIONS (where the P&L is below zero), computed from the payoff it
already builds, and the "Where do I start losing?" sentence is rendered from those regions only - never from the
breakevens.
Proof (step 1, red first against c53aef0): the five verifier counterexamples as literal tests (expected sentences
below), plus a seeded property test comparing `loss_regions` with a brute-force scan - red where the sentence is
concerned, then green.

Tier: A. Model: sonnet/medium (kit routing: builder, always).
Budget: 60 min wall-clock, 75 tool calls. Commit after each numbered step; at budget stop after a commit and report.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~300 words.
Copy from: none - engine work is built new (CLAUDE.md hard rule).

## RCA, Class, review (learning R1-R2; finding loss-region-inferred-from-breakevens)
- RCA (independent review, Fable, 2026-10-09, accepted in full): both earlier rounds derived the sentence from the
  breakeven set plus point samples, assuming every breakeven separates a loss region from a profit region and that
  there are at most two loss regions. The engine (`backend/ofo/engine/metrics.py:17-20`) reports as breakevens every
  level where P&L = 0, including touch-zeros and the ends of flat-zero plateaus; the question asks where P&L < 0.
- Class: every strategy shape (any legs, any breakeven count). Before: 5 of 5 verifier shapes wrong. After: the
  rendered regions equal a brute-force scan for 400+ random strategies and all literal cases.
- Detection: the generated property test below.

## Spec basis
- REQ-034 AC-7: "Outcome numbers appear in plain language first"
- ADR-072 decision: "names every region of the underlying
  at expiry where the strategy's expiry P&L is below zero"
- ADR-008: one calculation engine owns every P&L number (no maths in the route or the summary).

## What to build
1. **Engine** (`backend/ofo/engine/metrics.py`, stdlib): add `loss_regions` to `StrategyMetrics`, computed from the
   same `points/values/upper_slope` it already has: knots = {0, every strike, every exact zero (as Fraction)}; the
   payoff is linear on each knot interval, so the sign of the P&L at an interval's midpoint is its sign on the whole
   open interval; the upper tail's sign is the P&L at `last_knot + 1`. Merge adjacent loss intervals across a knot whose
   own P&L < 0. Work in Fractions before any 0.01 rounding (a sub-0.01 sliver must not flip a sign). Each region is
   (lower or None, upper or None); None = open end. A P&L of exactly 0 is not a loss (ADR-072).
2. **Slot + templates** (`backend/ofo/errors/explanations.py`): a closed slot type for a list of level intervals
   (each bound a Points value or None), and templates replacing summary_start_outside/between/below/above with one
   list sentence: parts "below X" / "between X and Y" / "above X", joined by ", " and "or", e.g. "If NIFTY ends below
   22,326.85 or above 22,873.15 at expiry."; keep `summary_start_never` ("at no level"); `summary_start_everywhere`
   drops any claim about breakevens; add the touch-point sentence "At every level except exactly {level} at expiry."
   when the only gaps between loss regions are single zero points. Pins in `tests/errors/template_pins.json`
   ("pending owner read"); list changes in `docs/process/w024-templates-for-owner.md` citing ADR-072. The slot
   allow-list test must include the new slot type.
3. **Summary** (`backend/ofo/outcome/service.py` `_summary`): render from `metrics.loss_regions` only; delete
   `_loses_outside` and the breakeven branches for this sentence. Do NOT change `scenario/levels.py` `_lower_upper` or
   the table's breakeven labels (ADR-072 consequence: a separate question).
4. **Tests**
   - `tests/engine/test_loss_regions.py`: a SEEDED property test, N >= 400 random strategies of 1-4 legs from the
     fixture catalogue's NIFTY 13-Oct strikes (21,500-23,500), BUY/SELL, 1-2 lots, entries in {0,25,50,100,150,200};
     compare `loss_regions` with a brute-force scan at a 2.5-point step up to the highest strike + 10,000 plus the
     far-tail sign (a scan ceiling clips far breakevens - the review saw 6 false mismatches at +1,000).
   - `tests/outcome/test_summary_start_losing.py` literal cases (expected strings written literally, from the review):
     zero-cost bull put spread (sell NSE_FO:44604 22400PE @100, buy NSE_FO:44595 22200PE @100) -> loss below 22,400
     only; 1x2 put ratio (buy 1x22400PE @100, sell 2x22200PE @50) -> one region, below its lower zero, nothing above
     22,400; two call butterflies 22200/22300/22400 + 22800/22900/23000 -> every loss region named; zero-cost bull
     call spread (buy 22800CE @100, sell 23000CE @100), max loss 0.00 -> the at-no-level sentence; a butterfly costing
     its width -> "At every level except exactly 22,300 at expiry."; plus the W-063 condor, the zero-premium condor,
     both strangles and the zero-premium strangle (already there), a no-breakeven strategy losing everywhere, and a
     2-lot ratio whose interior strike sits inside a loss (merge path).
   Use `_start(provider, legs)` and the replay fixture as the existing tests do; derive the exact zero levels by hand.

## Reviewer checklist (each must turn a test red)
- Compute the regions from breakevens again; treat P&L = 0 as a loss; skip the merge across an inside strike; round
  before the sign test; drop the upper-tail sign; render from `lower_be/upper_be`.
- Engine-math review: the property test is the gate; the reviewer uses the project skill `options-math-review`.

## Rules (this PC also serves IPODhan production's database - owner decision 2026-10-09)
- Targeted tests only: from the worktree, ONE directory per pytest call (conftests collide): tests/engine,
  tests/outcome, tests/errors, tests/table, tests/scenario; from `C:\Abhay\Ventures\OptionsForOptions2`:
  `python scripts/orchestrator/db_run.py C:\Abhay\Ventures\OptionsForOptions2-W-066 python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_outcome_catalogue.py tests_app/test_outcome_route.py tests_app/test_api_models.py tests_app/test_error_boundary_scan.py`;
  CI mirror `python C:\Abhay\Ventures\OptionsForOptions2\scripts\orchestrator\atool.py C:\Abhay\Ventures\OptionsForOptions2-W-066 W-066 --no-tests` (every step rc 0);
  regen `python C:\Abhay\Ventures\OptionsForOptions2\scripts\orchestrator\regen.py C:\Abhay\Ventures\OptionsForOptions2-W-066`.
- Kit guard: shell text must not name .claude, tools/, spec/requirements, .github or views; read them with Read/Grep.
- Do not edit kit files or `spec/` (the orchestrator wrote ADR-072). Never write `evidence/`. Never mark anything
  verified. No servers, no full suites, no alembic. Push `build/W-066-on-main`.
