# Builder brief: W-063 Outcome API

Core: on the real 2026-10-08 09:20 frames, the endpoint's response for a NIFTY 13-Oct iron condor gives every scenario
cell equal to REQ-033 AC-1's formula computed independently in Decimal, and the payoff points and the table come from
the same engine call.
Proof (step 1, before any route code): `tests/outcome/test_same_engine.py` replays
tests/fixtures/kite_ws/frames-2026-10-08-092000-10s.bin.gz through the merged W-059 `KiteProvider` (pattern:
tests/marketdata/_kite_fixture.py; valuation 2026-10-08 09:20:09 IST, rate 0.065), builds the outcome for SELL
NIFTY26O1322800CE / BUY 23000CE / SELL 22400PE / BUY 22200PE, 1 lot = 65, planned entries = each leg's LTP in the
replay, and asserts: each scenario cell equals the sum over legs of the REQ-033 AC-1 formula computed in the test in
Decimal (never by calling the engine); the current level 22,533.25 is a column and flagged current; the payoff points
equal the scenario P&L at the same levels; breakevens/max profit/max loss match the formula-derived values.

Budget: 60 min wall-clock, 75 tool calls. Commit step 1 green before steps 2-4; at budget stop after a commit and
report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), the condor's scenario row and summary as
returned, and the mutation tests with the test each turned red; under 300 words.
Tier: B.

## Spec basis
- REQ-034 AC-1: "Every user, including Guided beginners, sees the outcome view before execution: P&L, max profit/loss,
    breakevens, payoff, scenario behaviour, margin and risk (Q33; T1 #83-#98)."
- REQ-034 AC-8: "The payoff graph and the scenario table come from the same engine."
- REQ-033 AC-1 (the four leg formulas).
- REQ-033 AC-3: "Expiry scenarios use the entry price, never the current LTP."
- ADR-008 (one engine; money exact Decimal). ADR-061 (each expiry's forward for IV, Greeks and Estimated Now; spot for
  the CURRENT column and range). ADR-068 (planned entry with capture time; UX level a request parameter, Standard by
  default, presentation only; the not-live labels per its consequences: no session, stale/dropped per REQ-049 AC-5,
  sample prices).
- Copy from: none - legacy `routes/strategy.py` / `schemas/strategies.py` are REFERENCE/SKIP (float P&L).

## What to build
1. **Outcome service (backend/ofo/outcome/, stdlib, no app imports):** `build_outcome(definition, snapshot,
   ux_level, valuation)` -> a frozen `Outcome` holding the W-004/W-034 `Table` (one table, locked columns), the W-003
   scenario levels (At Expiry default; Estimated Now when asked, labelled an estimate), payoff points taken from the
   SAME computed scenario values (AC-8 - not a second engine call), the summary in plain language first ("What can I
   lose? What can I make? Where do I start losing?", REQ-034 AC-7) with detail, breakevens, max profit/loss, and a
   `margin` field whose state is `NOT_AVAILABLE_YET` (the margin item fills it later). Planned entry per leg comes in
   the definition with its capture time (ADR-068). Reuse the existing engine/scenario/table functions; add none.
2. **Snapshot from the provider:** a function that reads one consistent snapshot (leg quotes, index spot, the
   ExpiryForward per expiry, health) from a `MarketDataProvider`; a stale/unavailable input flows to the existing
   labels and refusals (W-059/W-060), never silently computed.
3. **Route (backend/ofo_app/routes/outcome.py):** `POST /api/strategies/outcome` with a pydantic request (underlying,
   legs: instrument id, action, lots, planned entry as string + captured_at, ux_level optional) and a response where
   every money/points value is a string from the Decimal (never a JSON float), with the OpenAPI schema committed as
   `docs/api/outcome.openapi.json` FIRST in this step (the screen item builds against it). The app gets the provider
   through a dependency so tests inject the replay provider; with no provider configured the route returns the
   "Draft - Live data not connected" state, not an error. Errors go through the existing app error handler.
4. **App test (AC-1):** `tests_app/test_outcome_route.py` - the condor through the HTTP route with the replay provider:
   every part AC-1 names is present (margin as NOT_AVAILABLE_YET), money fields are strings, and no-provider returns the
   not-connected state.

## Standing items (run-discipline B4) and reviewer checklist
- (d) every input state: all legs live; one leg stale; spot stale; forward fallback ("estimated from spot"); a leg
  with no quote; an expired leg; no provider. Each has a test naming the label or refusal it produces.
- Mutation tests first: payoff points computed by a second path; current LTP used for an expiry scenario instead of
  the planned entry; a money field serialised as a float; a stale leg computed without its label. Each must turn a
  test red.
- Exact assertions on written fields (the response keys and their types), not "is not None".
- Kit CI stays green: tests/ imports no ofo_app; app tests in tests_app/; no wall-clock asserts.

## Rules
- Branch `build/W-063-outcome-api` from origin/main. Do not edit kit files or spec/. Never write `evidence/`. Never
  mark anything verified. Targeted tests while building; the full domain and app suites once at the end (summary lines
  only, output to a log file). Run `python tools/ci_local.py` once before the push. Commit, push, do not open a PR.
