# W-1xx builder brief (lane A4): Guided Builder remainder - strategy modes, suggested setups, strategy preferences

Common brief: docs/process/builder-brief.md
Core: for a chosen strategy type, expiry and expected range, the server returns a few concrete setups (legs at strikes chosen by the mode), each priced by the engine, and the chosen setup loads into the Builder as an editable 'Suggested Setup'.
Proof: step 1 is a server test on the real instrument file and a recorded spot: for NIFTY at a recorded spot, template Bull Call Spread, range and expiry given, the mode function returns legs that are all listed contracts, and the engine's max profit, max loss and breakeven for them equal a hand computation written first; the same call with the platform-strike switch OFF returns the 'not available' answer and no strike (switch from lane B4).
Tier: A (reads engine delta / live prices to place strikes; a preference table = migration).

## Work item
The orchestrator allocates the W-id, writes `work/W-1xx.md` (requirement_ids REQ-025, REQ-027, REQ-068, REQ-069; REQ-024 / REQ-026 / REQ-028 remainders) and its coverage-stages row; commit them unchanged. Depends on #457 (Create guided flow, W-119) merged, on lane B4 (held-switch module and the fixed-rule strike placer) and on lane A3 (per-user setting store).

## Spec basis (quoted; remaining ACs only)
REQ-024 AC-7: "The market-view step starts simple (bullish, bearish, neutral, big move, not sure) with optional detail: expected move, volatility, time horizon"
REQ-025 AC-2: "Results are shown as 'Strategies you could consider', never as the trade to take."
REQ-025 AC-3: "Saved strategy preferences shape which valid strategies are shown first"
REQ-025 AC-4: "A preferred strategy is never silently forced or auto-selected."
REQ-026 AC-5: "capped per index by an Admin setting: defaults NIFTY 3,000 points, SENSEX 9,000 points"
REQ-027 AC-1: "Modes: Conservative, Balanced, Aggressive, Manual Custom."
REQ-027 AC-3: "The output is labelled 'Suggested setup', never 'Recommended trade'."
REQ-027 AC-4: "The user can manually override every suggested strike"
REQ-027 AC-5: "they stay out of production until the Q211 legal review clears them in writing"
REQ-027 AC-5: "Moving strikes the user already chose (Shift, Width, Hedge, ADR-150 (1)) is not covered by this hold."
REQ-068 AC-1: "Users can mark several preferred strategy types, all with equal priority"
REQ-068 AC-3: "Selecting a strategy lets the user explore its payoff across levels"
REQ-068 AC-4: "valid setups of the preferred types are shown first; when none is valid the screen says so"
REQ-068 AC-5: "In the Builder, preferences are guidance only"
REQ-068 AC-6: "the current strategy stays the one active strategy until the user chooses 'Use this setup'"
REQ-069 AC-1: "a small curated set of setups is shown"
REQ-069 AC-3: "gives a short reason, expandable to detailed reasoning covering the selected range, expiry, strike placement, risk profile, capital/margin"
REQ-069 AC-4: "Setups are reviewed one at a time, with an optional Compare view"
REQ-069 AC-5: "Choosing a setup loads it into the Builder in a visible 'Suggested Setup' state with assumptions and risk summary"
REQ-069 AC-7: "If edits move the strategy away from the original range, the user gets"
REQ-069 AC-8: "The original expiry/range, the generated setup, every change and the final configuration are kept as strategy context and history"
REQ-069 AC-9: "setups stay out of production until the Q211 legal review clears them in writing"
REQ-028 AC-2: "It also represents modifications, adjustment proposals, exits and execution plans."

## Copy from
Copy from: spec/technical-design/legacy-reuse.md strategy-template section, rows `app/api/routes/strategy_wizard.py` (596) and `app/schemas/strategy_templates.py` (ADAPT: wizard + compare for the Guided Builder, drop `deploy`), `app/api/routes/optionchain.py` find-by-delta / premium (ADAPT: split into service + route, Decimal, lot size and strikes from the catalogue); frontend section row `src/views/StrategyLibraryView.vue`, `stores/strategyLibrary.js`, `StrategyWizardModal.vue` (ADAPT, P5: reword 'Recommended For You' at `:30`). Services row `services/ofo_calculator.py` is REFERENCE only (float, second calculator): never copy.

## Sensibull screens (study folder D:\Abhay\Ventures\competitors\sensibull\2026-10-21\; never copy a screenshot or account data into the repo)
- 080-087 Easy Options: three cards Defensive / Balanced / Aggressive per direction with max profit, max loss, quantity -/+; 'More Details' modal 'How does this trade work?' bullets, payoff, breakeven (87 shows the card, 83-84 the modal): the shape of REQ-069 AC-2 and AC-3.
- 070-075 Strategy Wizard: Prediction Above / Between / Below + target + expiry + filters; result table. Do not copy its ranking by profit or its 'Most Profitable' title (ADR-003, ADR-055); results are 'Strategies you could consider'.
- 160-162 Expiry Trades: target ladder Defensive / Moderate / Aggressive; See Details modal.
- Differences kept on purpose: no ranking by profit, no return wording, labels 'Suggested setup' and 'Strikes placed by a fixed rule - change them'.

## What to build
1. `ofo/strategy/modes.py` (new): Conservative / Balanced / Aggressive / Manual Custom as data (a mode = per-leg target rule read from admin config, no numbers committed here: see Open: business); `ofo/strategy/setups.py` (new): from template + expiry + range + mode, build 2-4 candidate leg sets using lane B4's placer, drop invalid ones, fail closed with the reason. A setup is a leg set the engine prices; text 'why you are seeing this' from the reviewed catalogue (`ofo/errors/templates.py` pattern), numbers from the engine.
2. `ofo_app/routes/setups.py` (new): `POST /api/strategies/setups` (template or objective, expiry, range, mode) returning setup cards (summary, thumbnail points, key numbers) and, on demand, details (legs, payoff, breakevens, margin, charges, assumptions, reason). Preferences first (REQ-068 AC-4): preferred types ordered first, others after with the 'none valid' line. Respects the held switch from B4: off means the route answers with the held reason and places nothing.
3. Preferences: `GET/PUT /api/settings/strategy-preferences` using the generic per-user setting store from A3; Settings -> Strategy Preferences page (library cards, 'Prefer this', Beginner / Intermediate / Advanced labels from W-047 data `ofo/strategy/catalogue.yaml`); the Builder's 'Related to your preferences' area and the notification only after a meaningful change (REQ-068 AC-5 definition).
4. Builder: loaded setup shows the 'Suggested Setup' state; range-departure prompt (REQ-069 AC-7); original range, generated setup, every change and final configuration kept as strategy context in the stored definition (`ofo/strategy/definition.py` already has PREFERENCE_NAMES for expected range) and in builder history (`builder_history.py`: LABEL_ALTERNATIVE exists).
5. REQ-024 AC-7 optional detail on the market-view step; REQ-026 AC-5 admin cap setting replacing the default constants in `frontend/src/lib/guided.js` (from #457) with a server-served value.
6. Regenerate `docs/api/openapi.json`; register new ApiModel classes in `tests_app/test_response_door.py`.

## AC status (main + #457 gc6/create-guided + evidence/)
| AC | Status |
|---|---|
| REQ-024 AC-1..AC-6, AC-8 | exists on #457 (`frontend/src/pages/CreateStrategyPage.vue`, `lib/guided.js`, W-119); not re-briefed |
| REQ-024 AC-7 optional detail | missing (W-119 note) |
| REQ-025 AC-1, AC-2, AC-5 | partial (#457 cards are 'strategies to consider'); AC-3, AC-4 missing |
| REQ-026 AC-1..AC-4, AC-6..AC-8 | exists on #457; verified evidence/W-025 AC-3, AC-5, AC-6, AC-7 for the domain pick lists |
| REQ-026 AC-5 admin cap | missing (defaults hard-coded, W-119 note) |
| REQ-027 AC-1..AC-5 | missing (ExpectedMove exists in `ofo/scenario/levels.py:59` for the scenario range, no strike modes) |
| REQ-028 AC-1, AC-3..AC-5 | exists, verified (evidence/W-005); AC-2 partial (`ofo/strategy/modification.py`; adjustment proposals are lane D) |
| REQ-068 AC-2 | exists, verified (evidence/W-047 AC-2) |
| REQ-068 AC-1, AC-3..AC-6 | missing |
| REQ-069 AC-1..AC-9 | missing (W-119 'Not here' list) |

## Attack cases
Switch off (route places nothing, answer names the hold, no leg in the reply); template needing an expiry the underlying lacks (plain message, not 500); range wholly below spot; range inside one strike gap; no valid setup for the preferred type (the line says so, others shown after); preference saved for a type later removed from the catalogue; two preferred types equal priority (order stable, not ranked by profit); mode placing a strike the instrument file does not list (setup dropped, reason kept); stale spot (refused with the REQ-049 reason); wording scan: no 'recommended', 'best', 'you should' in any new string; user edits a setup past the original range (prompt, then original vs effective numbers before Continue anyway).

Threat model: in scope a setup request that tries to turn the held switch on by body, header or query, and a preference body with unknown keys; out of scope the owner editing the production configuration file (owner-edited by design).

## Findings checked
Findings checked: advice-wording-denylist-per-module, setting-read-from-two-sources, guard-as-forbidden-list, money-value-computed-outside-engine, outcome-multi-expiry-unhandled-500, fallback-time-claims-missing-data, research-finding-held-in-chat, test-asserts-implementation-output

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step gains an import; (c) applied: the wording test lists the allowed strings and refuses everything else (allow-list, finding guard-as-forbidden-list), names the catalogue by import source; (d) applied: answer states of the held switch (on, off, setting unreadable) and of the engine (priced, refused, no IV) are listed in attack cases and tested.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Targeted tests: tests/strategy/test_modes.py (new), tests/strategy/test_setups.py (new), tests_app/test_setups_route.py (new), tests_app/test_strategy_preferences_route.py (new), tests_app/test_strategy_templates_route.py, tests_app/test_response_door.py; frontend: `npx vitest run tests/create-strategy.test.js tests/setups.test.js tests/strategy-preferences.test.js`, `npm run lint`, `npm run build`.
Rules: no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR (the one exception is docs/api/openapi.json when an API model changes)
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Open
SETTLED BY THE SPEC (orchestrator correction, 2026-10-21): REQ-027's body (the "short-strike delta bands" decision, also spec/open-questions.md line ~294) sets **Conservative 0.10-0.15, Balanced 0.20-0.25, Aggressive 0.30-0.35** (absolute delta; admin-tunable bands) with its own NIFTY 23,047 Iron Condor example and the wing rule that follows it. Read REQ-027 from line 50 and build to it: these are the default band values in admin configuration. Production stays off until Q211 (REQ-027 AC-5).
Open: technical: delta placement reads the engine's delta at the live spot; proposal: pick the listed strike whose delta is nearest the mode target, ties to the strike farther from the money.
Open: technical: this brief cannot start before B4's switch and placer merge; proposal: if B4 slips, build the preferences store and Settings page (REQ-068 AC-1..AC-3) first, they have no dependency on B4.

## Legacy map rows (copy_from_check.py)
Rows of spec/technical-design/legacy-reuse.md that name this brief's requirements. Act on each:
COPY/ADAPT -> use it (provenance header) or write in the report why not; REFERENCE -> read before
designing; SKIP -> do not re-survey.

| `app/constants/trading.py` (158), `strategy_types.py` (421), `enums.py` (375), `websocket.py` (65), `brokers.py` (29) | REFERENCE | hardcoded lot sizes conflict with REQ-053; strategy-type names/categories useful | REQ-028 |
| `scripts/seed_strategies.py` (1312), `app/models/strategy_templates.py` (75) | REFERENCE | row 7; our W-005/W-047 library exists: fill only missing templates; `example_spot` Float (`:62`) | REQ-028 |
| `services/options/{expected_move,gamma_risk,iv_metrics,oi_analysis,theta_curve}_service.py` | REFERENCE | algorithms for REQ-026 / REQ-047 | REQ-026, REQ-047 |
| `services/autopilot/{strike_finder_service,strategy_converter,template_service,suggestion_engine,position_sizing,position_leg_service,leg_actions_service,break_trade_service,staged_entry_service}.py` | REFERENCE | leg exit/add actions break ADR-002 | REQ-027, REQ-037 |
| `docs/features/ofo/REQUIREMENTS.md` (63), `README.md` (68), `docs/plans/ofo-implementation-plan.md` (396) | COPY | `docs/reference/legacy/ofo/`; reference for REQ-069 (ranking rules would be a SPEC CHANGE) |
