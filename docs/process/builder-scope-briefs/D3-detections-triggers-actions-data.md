# W-1xx: The three platform detections, every trigger and action type, adjustment data (REQ-045, REQ-047, REQ-071)

Common brief: docs/process/builder-brief.md (read it first; this file is the item part only).

Core: with no rule defined, each of the three Q253 conditions fires 'Adjustment opportunity detected' on a real tracked strategy from live-feed numbers that equal a hand calculation, and none fires one tick before its threshold.
Proof: recorded replay of a NIFTY iron condor (the golden condor of the REQ-045 owner decision): drive spot to 0.49% / 0.50% / 0.51% from the short strike, loss to 49% / 50% / 51% of max loss, and DTE 2 with a short leg at 0.99% / 1.00% / 1.01%; assert the boundary on each, in Decimal, against a hand computation written in the test docstring. Live window: the same condition 1 on live prices (W-122 core proof) plus conditions 2 and 3 with the threshold lowered.

Tier: A (detection numbers: thresholds, distances, percent of max loss, DTE)

Spec basis:
REQ-045 AC-1: "User-rule triggers are labelled 'Your rule was triggered'"
REQ-045 AC-2: "Detection runs even when the user defined no adjustment rule (Q149)."
REQ-045 AC-5: "When no user rule exists, the platform shows a warning plus generic possible approaches only"
REQ-045 AC-6: "No adjustment is ever presented as universally correct or as always reducing risk."
REQ-045 AC-8: "Several rules triggering together are grouped into one message"
Q253: "0.5% from a short strike/breakeven, or 50% of max loss, or ≤2 DTE with a short leg within 1%; all"
REQ-047 AC-3: "A new metric can be added without redesigning the data layer (Q164)."
REQ-047 AC-4: "Adjustment-relevant data is collected even when the user has no adjustment rule (Q165)."
REQ-071 AC-1: "are listed and each is placed in the data catalogue"
REQ-071 AC-2: "Every listed value passes the Data Feasibility Test before it is built."
ADR-165 (6): "the three platform detections (Q253)"

Copy from: none - extends W-122 (branch build/W-122-track-detect): backend/ofo/adjustment/detection.py (Detection, detect_near_levels, check_threshold, short_strikes) is condition 1; add conditions 2 and 3 in the same module with the same shape. The metric registry exists: backend/ofo/adjustment/registry.py, metric_registry.json (30 rows).

Sensibull screens: no Sensibull equivalent in the study for adjustment detection. Visible numbers reused: summary strip Max Profit / Max Loss / Breakeven / Funds (catalogue-raw.md 042-045), 'Profit left / Loss left' for existing positions (lines 279-280), strategy P&L on Positions 050-053.

## What to build
Prerequisite: W-122 merged (condition 1 and the tracking store are there; do not rebuild).
1. Conditions 2 and 3 in backend/ofo/adjustment/detection.py: 2 = loss at or beyond 50% of max loss (max loss from the one engine, ADR-008; an unlimited-loss strategy has no percent: condition 2 reports 'not applicable', never a default); 3 = at most 2 DTE and a short leg within 1% of spot. Every threshold an admin setting with the Q253 default (admin pattern: backend/ofo/admin/, settings_value.py; one home for each number, the repo literal test must stay green).
2. Detection runs with no rule (AC-2) inside the worker pass (D1) and writes a trigger record with its data health (REQ-049 AC-3); label 'Adjustment opportunity detected' for platform detections, 'Your rule was triggered' for user rules; the two never share a code path for the label (AC-1). Default playbooks not adopted by the user are platform detection (Q252).
3. All AC-3 trigger inputs reachable by a rule: diff the list (underlying move/level, distance from short strike/breakeven, leg profit threshold, strategy max-profit/max-loss thresholds, Greek thresholds, IV change/percentile, DTE, premium, P&L, compound) against backend/ofo/rules/inputs.py InputName and add the missing ones, computed by the engine. IV percentile needs history: if the history tier cannot give it (REQ-051 AC-1: simulation disabled in V1), the input reads 'unavailable', never a default.
4. Candidate actions (AC-4): a closed enum of the twelve kinds (take profit, close leg, roll leg, roll spread, move strike, add/remove hedge or leg, change quantity, re-centre, convert strategy, exit, alert only, no-trade proposal) with a generic one-line explanation each from the catalogue (ADR-003 wording, no 'you should'); no specific configuration unprompted (AC-5); no claim of universal correctness (AC-6, wording scan). The Before/After build for a picked kind is D4.
5. Grouping (AC-8): several triggers at once = one message '3 adjustment conditions triggered' with each listed.
6. REQ-047: strategy-snapshot writer for tracked strategies collected even with no rule (AC-4), using the existing history tier (backend/ofo/history/); metric registry add path proven by adding a new row in a test without touching the data layer (AC-3). Data Feasibility Test fields (AC-5) are columns of the registry; do not invent others.
7. REQ-071: the registry exists (30 rows). Seven values are NOT yet usable and need the owner: row 12 Payoff curve slope / steepness (unclear), 13 Profit-zone edges on the payoff (unclear), 19 Broker auto square-off time on expiry day (unknown), 20 Overnight gap (unknown), 21 Underlying move over 1 day (unknown), 22 Underlying high-low range over a period (unknown), 30 Brokerage / charges and return on capital (unknown). Rows 24 and 25 are marked out of V1. Build NO code for these seven; write them to the owner-inputs list with the registry's own wording, and make the engine return 'unavailable' for any rule that names one. Rows 10, 26, 28 have owner readings (Q246) and are built.
8. Platform-view switch: suggestions shown as the platform's view stay OFF in production until Q211 clears (ADR-055 (1)): one configuration switch, default off when APP_ENV=production, with a test; user-rule triggers are not behind it.

## AC status (main plus open PRs, 2026-10-21)
| AC | Status | Where |
|---|---|---|
| 045 AC-1,2 | partial | detection.py condition 1 on W-122; label code path for rules missing |
| 045 AC-3 | partial | inputs.py InputName: diff needed |
| 045 AC-4 | missing | no action enum |
| 045 AC-5,6 | missing | wording scan |
| 045 AC-7 | deferred | ADR-165 (6): machinery in D2, content later |
| 045 AC-8 | missing | |
| 045 AC-9 | lane C8 / D4 | Positions area |
| Q253 cond 1 | W-122 in progress | |
| Q253 cond 2,3 | missing | |
| 047 AC-1..6 | partial | registry.py, metric_registry.json, history tiers |
| 071 AC-1 | exists (30 rows) | 7 values need the owner |
| 071 AC-2 | exists | feasibility column |

## Every answer state of each outside system
Live quotes: fresh (stated) = evaluate. Stale/missing leg price (absent/failed) = condition 'unavailable', no detection, strategy paused (REQ-049 AC-5), never fires on stale data. Strategy with no short leg (empty) = conditions 1 and 3 not applicable. Unlimited max loss = condition 2 not applicable. DTE 0 (expiry day, ambiguous) = condition 3 applies (<= 2). Settlement not yet known = leg open. Engine error (failed) = detection paused with the error class, not silent. Database: trigger record write fails = nothing is shown as detected (no orphan alert).

## Attack cases (reviewer: hands-on first)
- Boundary triplets for each condition (0.49/0.50/0.51 etc.) asserted with Decimal; 0.5 as float literal anywhere: red.
- Threshold changed by admin to 0 or 100: accepted range check; negative refused.
- A call spread with a defined max loss vs a naked short strangle (unlimited): condition 2 differs.
- Two strategies of one user, one stale: only that one is paused.
- Detection fires, price returns inside the threshold, fires again: no duplicate within the dedupe window (D1 key).
- Wording scan: 'best', 'should', 'guaranteed', 'always reduces risk' in any generated message: red.
- Platform-view switch left on in production config: test red.

Threat model: in scope: threshold boundaries, units, stale-data firing, duplicate triggers, advice wording; out of scope: choosing which approach is right (owner specifics, Step 8) and legal review (Q211).

Findings checked: loss-region-inferred-from-breakevens, money-value-computed-outside-engine, money-parsed-through-float, fallback-time-claims-missing-data, staleness-by-last-change-age, advice-wording-denylist-per-module, test-asserts-implementation-output, aggregate-across-mixed-instrument-kinds

Standing items: (a) applies: the detection pass inside the worker uses its own small slot; a test shows the higher-priority monitor pass still runs when many strategies are tracked. (b) n/a: no CI step added. (c) applies to the wording scan: names the catalogue by import source and fails closed. (d) applies: states above.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Targeted tests: tests/adjustment/, tests/rules/, tests/engine/ if a max-loss function is touched, tests_app/test_strategy_tracking.py (W-122), tests/test_repo_literals (find the REQ-075 test)
Rules: no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR (the one exception: a changed API model regenerates docs/api/openapi.json and is registered in tests_app/test_response_door.py, per builder-brief.md).
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Open
Open: business: the 7 unclear video values (registry rows 12, 13, 19, 20, 21, 22, 30 in backend/ofo/adjustment/metric_registry.json): the owner states what each means for his Iron Condor adjustment video. Ask once for all seven with the registry wording. Recommended default: leave all seven 'unavailable' until answered (Step 6 plan input).
Open: technical: condition 2 when max loss is unlimited. Proposal: 'not applicable' (no default percent), asserted by a test.
Live window needed: conditions 1 to 3 on live prices (owner Kite login, market day).
