# W-1xx: Rule editor, global defaults with per-strategy overrides, and status colours (REQ-041, REQ-043, REQ-045 AC-7)

Common brief: docs/process/builder-brief.md (read it first; this file is the item part only).

Core: a user edits a global default adjustment rule for one strategy, the override (not the global) is what the engine evaluates for that strategy, and its status colour follows from the rule and the numbers.
Proof: on the recorded replay: store a global rule 'short strike distance below 0.8%', override it to 1.2% for one strategy, evaluate both strategies with the real rules engine (backend/ofo/rules/plan.py evaluate_plan), and read two different outcomes with the exact message of REQ-043 AC-6 (Watch - ...) and the colour Yellow.

Tier: A (thresholds and rule evaluation decide every detection and colour; PR 1 of 2 is the rule-storage migration)

Spec basis:
REQ-041 AC-1: "Entry, adjustment and exit conditions all use one rule-engine model (T1 #36)."
REQ-041 AC-5: "Exit and adjustment plans are optional; a strategy without them is still monitored"
REQ-041 AC-7: "Adjustment rules have global defaults with per-strategy overrides (Q57)."
REQ-041 AC-8: "The model can express compound AND/OR conditions"
REQ-041 AC-9: "After the legs are configured, the next Builder step is Entry, Adjustment and Exit rules"
REQ-041 AC-10: "a suggested rule is inactive until the user confirms it (Q142, Q143)"
REQ-043 AC-2: "Each strategy shows one status: Green = Healthy, Yellow = Watch, Orange = Adjustment opportunity, Red = Exit condition reached."
REQ-043 AC-4: "Monitoring statuses are separate from the strategy state machine and from entitlement."
REQ-043 AC-5: "Monitoring runs even when the user defined no rules (Q154)."
REQ-045 AC-7: "Default adjustment playbooks based on common practice ship with the product; every logged-in user can edit them"
ADR-165 (6): "It ships with no default playbooks until the owner gives the adjustment specifics"
ADR-165 (5): "which triggers, which adjustment types are allowed or forbidden, and the thresholds"

Copy from: none - the model exists: backend/ofo/rules/ (model.py evaluate, conditions.py decide with three-valued logic, defaults.py resolve_adjustment_rules, templates.py entry_* and exit_* templates, plan.py evaluate_plan, inputs.py Snapshot). Reuse; add storage, routes, UI.

Sensibull screens: no Sensibull equivalent in the study for adjustment rules (catalogue BUILDER PASS 3 lists 'analysing/adjusting a real open position' as not covered). Closest visible references: Conditional Exits 'set from Positions page, can click payoff graph to set exit level' and the Positions menu 'Stoploss Order' (catalogue-raw.md What's New and 050-053): copy only the idea of setting a level by clicking the payoff graph; the order half is out of scope.

## What to build
PR 1 of 2: migration for stored rules: rules (id, scope global|strategy, strategy_id nullable, kind entry|adjustment|exit, definition json validated by backend/ofo/rules/model.py, origin default|personal copy|suggested, active bool, created/changed by + time) and rule_overrides if the builder prefers separate rows. Own PR, next free migration number.
PR 2:
1. Storage + routes (backend/ofo_app/rule_store.py, routes/rules.py): create, edit, delete, activate; the closed schema is the existing model (allow-list of rule kinds, ops and input names, generated test over every InputName, not a hand list). New ApiModels: regenerate docs/api/openapi.json and register in tests_app/test_response_door.py.
2. Defaults and overrides (REQ-041 AC-7): resolve_adjustment_rules (backend/ofo/rules/defaults.py) gives the effective rule per strategy: strategy override > global default. Per Q252 (REQ-045 owner decision): a default the user has not adopted or edited counts as platform detection; adopting or editing makes a PERSONAL COPY and never changes the global for anyone else; test both.
3. Shipping no default playbooks: ADR-165 (6) overrides REQ-045 AC-7's 'ship with the product'. The default rule SET is empty in this PR (an editable empty list plus the existing templates entry_* / exit_* as pick-list); each future specific is content, not code. Record the SPEC CHANGE label in the PR body Spec-deviation block (Class 3 already decided by the owner in ADR-165).
4. Suggested rules (AC-10): the platform suggests profit target, max loss, level reached, short strike threatened, time exit from the existing templates; each is inactive until the user confirms; a no-exit-rule suggestion appears once, no nagging (AC-12).
5. Rule editor UI in the builder step 'Entry, Adjustment and Exit rules' (AC-9): missing rules are explained, not blocked; the UI adapts to the UX level (AC-11, reuse the existing level switch). Exit action offered: 'Alert me' only. 'Alert + prepare exit orders' (AC-3) is OUT of scope: ADR-165 removes order preparation; do not call rules/actions.py respond() (it builds a ProposedOrder).
6. Status colours (REQ-043): a pure function status_for(strategy, rule outcomes, data health) -> StrategyHealth (backend/ofo/table/model.py:105): Green Healthy, Yellow Watch, Orange Adjustment opportunity (platform detection or a personal-rule adjustment trigger), Red Exit condition reached; separate from the state machine (C7) and from entitlement (AC-4); runs with no rules (AC-5); calm specific messages like 'Watch - NIFTY moved closer to your upper short strike. Distance 1.2%, your trigger 0.8%. You don't need to act yet.' (AC-6) from the catalogue. Paused (no data) is NOT a colour (REQ-049 AC-6).

## AC status (main plus open PRs, 2026-10-21)
| AC | Status | Where |
|---|---|---|
| 041 AC-1 | exists | backend/ofo/rules/model.py, plan.py |
| 041 AC-2 | exists | templates.py entry_immediate, entry_level_reached, entry_premium_target, entry_volatility, entry_time_window |
| 041 AC-3 | partial | exit_profit_target, exit_max_loss, exit_time, exit_underlying_level exist; 'prepare orders' half out of scope |
| 041 AC-4 | partial | inputs.py InputName: compare to the list and add the missing |
| 041 AC-5,8 | exists | conditions.py (AllOf, AnyOf, Truth three-valued) |
| 041 AC-6,9,11 | missing | no UI |
| 041 AC-7 | partial | defaults.py:resolve_adjustment_rules, no storage, no overrides |
| 041 AC-10,12 | missing | |
| 043 AC-1..6 | partial | StrategyHealth enum (table/model.py:105), availability.py; no status function |
| 045 AC-7 | partial | see above; playbook content deferred by ADR-165 (6) |

## Every answer state of each outside system
Rule store (database): rule rows (stated) = evaluated. No rules (empty) = detections and colours still run (D3). A rule referencing an unknown input name (invalid) = refused at save, never ignored (input-domain checklist: unknown keys). A stored rule that fails to load (failed) = that rule is skipped, strategy shows 'Monitoring paused - a rule could not be read', never Green. Override and global both exist (ambiguous) = override wins, shown which applied. Inputs missing/stale (absent) = three-valued: AND is not true, OR true only on a proven branch (conditions.py decide). Kite: not called here.

## Attack cases (reviewer: hands-on first)
- Editing a default as user A leaves the global default byte-identical (personal copy).
- A rule with depth 50 or 10,000 leaves: refused by ComplexityLimits.
- Threshold 0, negative, 'NaN', 1e9, '0.5%' typed as text: refused with the typed message.
- All inputs stale: colour is not Green; message says paused, not Healthy.
- Rule says 'distance below 0.8%' and distance exactly 0.8%: boundary asserted both ways with Decimal.
- Suggested rule appears active without a confirm: red.
- Float anywhere in thresholds (money-parsed-through-float class).
- Order-door import from the rule editor or rule store: scan red.

Threat model: in scope: thresholds off by units or percent vs fraction, stale data turning Green, override leaking to the global, rules saved with unknown keys; out of scope: legal review of personalised adjustment logic (Q211, held: platform-view suggestions stay off in production).

Findings checked: guard-as-forbidden-list, guard-without-killing-test, normalise-before-validate, fallback-time-claims-missing-data, money-parsed-through-float, setting-read-from-two-sources, loss-region-inferred-from-breakevens, advice-wording-denylist-per-module

Standing items: (a) n/a: no time-budgeted job in this item (the evaluation pass lives in D1; its test covers the cap). (b) n/a: no CI step added. (c) applies to any wording scan added (advice-wording): names the catalogue by import source and fails closed. (d) applies: rule-store and input states above.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Targeted tests: tests/rules/, tests/table/, tests_app/test_rules_*.py (new), tests_app/test_response_door.py, frontend/tests for the rule editor and status chip, every file naming StrategyHealth or HEALTH_LABEL_TEXT
Rules: no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR (the one exception: a changed API model regenerates docs/api/openapi.json and is registered in tests_app/test_response_door.py, per builder-brief.md).
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Open
Open: technical: REQ-041 AC-3's 'alert + prepare exit orders' and AC-1 of REQ-042 order half are out of scope (ADR-165); proposal: the Exit rule action list shows only 'Alert me'; the enum value for prepare-orders stays in the model but the editor and the API refuse it while Execute is off (one switch). Recorded, no question.
Open: business: none new (ADR-165 (5) and (6) already decide machinery now, no playbooks). The 7 unclear video values are in D3.
Platform-view note: anything this item shows as 'the platform's view' on strikes or adjustments is behind the production-off switch until Q211 clears (ADR-055 (1)); user-rule triggers are the user's own and are not.

## Legacy map rows (copy_from_check.py)
Rows of spec/technical-design/legacy-reuse.md that name this brief's requirements. Act on each:
COPY/ADAPT -> use it (provenance header) or write in the report why not; REFERENCE -> read before
designing; SKIP -> do not re-survey.

| `services/autopilot/condition_engine.py` (1096) | REFERENCE | condition vocabulary; rebuild on Decimal | REQ-041 |
| `services/autopilot/strategy_monitor.py` (1876) | REFERENCE | trigger loop | REQ-043 |
| `services/autopilot/adjustment_engine.py` (1388) | REFERENCE | auto default (`:246`); Alert + Prepare only | REQ-042, REQ-045 |
| `services/autopilot/{delta_band,delta_rebalance,dte_zone,trailing_stop,premium_tracker,adjustment_cost_tracker}*.py` | REFERENCE | trigger definitions | REQ-045, REQ-047 |
| `src/composables/autopilot/useWebSocket.js` (505) + test (832) | ADAPT (P3b) | token off the query string (`:53`); decouple from autopilot | REQ-043, REQ-048 |
| `src/views/PositionsView.vue` (1306), `stores/positions.js` (213), `DashboardView.vue` (505), `components/autopilot/monitoring/*` | ADAPT (P5) | strategy-scoped; reword advice (`GammaRiskAlert.vue:22`) | REQ-008, REQ-043, REQ-044 |
