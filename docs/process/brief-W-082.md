# Builder brief: W-082 breakeven labels from loss regions (Tier A)

Core: a zero-cost bull put spread (sell 22400 PE @100, buy 22200 PE @100) labels 22,400 as the Lower BE (its loss lies
below it), where `_lower_upper` today labels it Upper BE; a long call, short call, long put and short put keep their
current labels.
Proof: step 1 is `tests/scenario/test_breakeven_labels_loss_regions.py` on the real engine (expected labels derived by
hand: the spread's P&L is exactly 0 above 22,400 and negative below it). Write it FIRST, red on current main.

Tier: A (engine output). Model: sonnet (builder routing).
Budget: 30 min wall-clock, 34 tool calls. HARD: at call 31 stop, commit, push, report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~250 words.
Copy from: none - a fix to this project's own scenario code.

Read first: `docs/process/builder-brief.md`, `work/W-082.md`, `spec/decisions/ADR-089.md`, `spec/decisions/ADR-072.md`,
`spec/business-rules/scenario-calculations.md` §4, `backend/ofo/scenario/levels.py` (`_lower_upper` ~116),
`backend/ofo/engine/metrics.py` (`loss_regions`, `LossRegion`), issue #171 (`gh issue view 171`), the
`options-math-review` checklist (Read `.claude/skills/options-math-review/SKILL.md`).

## Spec basis
- ADR-089: "With exactly one breakeven, it is the Lower BE when the loss region lies below it and the Upper BE when the
  loss region lies above it, taken from the computed loss regions (ADR-072)"
- REQ-033 AC-6: "Breakevens, max profit and max loss are strategy-level and computed from the payoff"

## What to build
1. `_lower_upper` reads the strategy's loss regions (the engine's `StrategyMetrics.loss_regions`, one source; never a
   second payoff walk): one breakeven + a loss region whose upper edge is that breakeven (loss below) -> Lower BE; a loss
   region whose lower edge is that breakeven (loss above) -> Upper BE; two or more breakevens -> lowest and highest, as
   today. If the metrics cannot say (no loss region touches the breakeven, e.g. a payoff that only touches zero), show
   neither label (both missing) - never a guess, never an exception that would break the outcome answer; test it.
2. Everything downstream (table summary, `Summary.lower_be / upper_be`, serializer) follows from that one function.

## Reviewer checklist (write first; each red when mutated)
- The real case (bull put spread, zero cost) -> Lower BE 22,400, Upper BE shown as a dash; old rule (P&L one step above > 0)
  restored -> red.
- Long call, short call, long put, short put: labels unchanged (four tests, hand-derived).
- Two breakevens (iron condor) unchanged.
- Breakeven VALUES unchanged in every case (assert the numbers, not only labels).

## Rules
- Targeted tests: `python -m pytest -q -p no:cacheprovider tests/scenario`, then `tests/table`, `tests/outcome`,
  `tests/engine` separately. No database. Then your worktree's own atool `--no-tests`.
- No kit, `spec/`, `views/`, findings INDEX edits; never write `evidence/`. Commit, push `build/W-082-be-labels`. No PR.
