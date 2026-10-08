# Builder brief: W-060 round 3 - the type makes an ungated price impossible (after an independent review)

Core: no product code can turn an index level into an IV, Greek, estimate, table value or payoff value without a
SpotReading and each expiry's forward, and every such output carries its label and the spot's time.
Proof (step 1, before refactoring): a class test over every product entry point (scenario_values, scenario_table,
payoff_graph, build_table, the Estimated Now path, IV/Greeks on the forward) x spot {missing, unavailable, stale,
delayed, available} x forward {parity, unavailable, mismatched spot or time} -> refused or labelled exactly as below.
It is red on c8e09c6 (build_table computes DELTA -19.2029 with an UNAVAILABLE spot and no label; estimate_now runs with
spot=None and returns 913.50), and green after.

Why Opus: a type-level redesign across engine, table and scenario, written around an independent review after two
red rounds of the same class.
Budget: 60 min wall-clock, 80 tool calls. Commit after each step; at budget stop after a commit and report done / not
done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), the entry-point table (path, gated how), mutants.
Tier: B (engine maths - the options-math-review checklist applies at review).
Class: a stale or missing index value used silently in a calculation (REQ-072 AC-2), and IV/Greeks not using the
parity forward with its label and timestamp (AC-3).

## Spec basis
- REQ-072 AC-2: "a stale or
    missing index value is shown as such and is never used silently in a calculation."
- ADR-061 (the forward and the fallback label) and ADR-063 (the engine owns q and every Greek).
- Independent review of 2026-10-08 (cited in the PR body): the defect is the type - StrategyInput keeps a bare
  `underlying_level` and an optional `spot`, so every ungated consumer leaks; table/model.py never passes q (breaks
  ADR-063); iv_on_forward/greeks_on_forward have no product caller; the scenario outcome never passes forwards; the two
  stale policies disagree.

## What to build (the review's approach, accepted)
1. Remove `underlying_level` from StrategyInput; `spot: SpotReading` is required. Fix every caller and fixture (tests
   pass an AVAILABLE reading; no expected value changes).
2. One function, e.g. `model_inputs(strategy_input, forwards) -> ModelInputs`: refuses a missing/unavailable/unhealthy
   spot (fixed code); for each expiry gives level S, q, source ("parity" / "spot fallback") and a label; checks each
   ExpiryForward's spot and valuation time match the reading (refuse a mismatch); combined label when both apply:
   "stale since HH:MM IST; estimated from spot" (stale or delayed spot computes with the label; the forward is read from
   option quotes of the same snapshot).
3. Every product IV/Greek/estimate/table/outcome entry takes ModelInputs (never a Decimal level), passes S and q to the
   engine, and returns `spot_level`, `spot_at` and the label. `forwards` stops being optional; the table's Greeks use q
   and the forward; IV on the forward is the product path. `estimate_now` and the low-level engine functions become
   engine-private for product code.
4. Pure and unchanged: the black_scholes functions, scenario_grid and strategy_metrics with their q = 0 golden tests.
5. Second layer: a repo scan - outside backend/ofo/engine and the one model_inputs function, no import or call of the
   pricing functions (bs_price, implied_volatility, bs_greeks, bs_greeks_unrounded, forward_price, estimate_now); fails
   closed on aliases, `import *` and getattr.

## Standing items (run-discipline B4) and reviewer checklist
- Mutants first: re-add a bare-level path in the table; drop q in the table; drop the combined label; accept a
  mismatched forward; import bs_greeks in table/model.py. Each must turn a test red.
- Expected values from the fixture replay, Hull's formulas and work/W-060.md, never from running the new code.
- Kit CI stays green: tests/ imports no app packages; no wall-clock asserts.

## Rules
- Fresh branch work on origin/build/W-060-forward (head c8e09c6): `git fetch origin && git checkout -b w060-r3
  origin/build/W-060-forward && git merge origin/main`; push with `git push origin w060-r3:build/W-060-forward`.
- Do not edit kit files or spec/. Never write `evidence/`. Never mark anything verified.
- Full domain suite once at the end (summary line). Commit and push.
