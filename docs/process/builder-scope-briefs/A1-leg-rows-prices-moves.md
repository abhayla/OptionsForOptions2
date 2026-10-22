# W-1xx builder brief (lane A1): Leg rows, entry prices and Shift/Width/Hedge in the Strategy Builder

Common brief: docs/process/builder-brief.md
Core: one server function takes the builder's legs plus ONE edit (strike step, multiplier, include tick, typed price, Reset Prices, Shift / Width / Hedge click) and returns the new legs with the engine's numbers; the browser sends the edit and draws the reply.
Proof: step 1 is a test on the REAL instrument file (recorded catalogue fixture): a NIFTY iron condor moved once each by Shift +1, Width +1, Hedge +1; the new strikes and the engine's max loss are written in the test from a hand computation BEFORE the code exists. The live-session run of the same check (REQ-078 AC-1) is the orchestrator's, in the owner's final live window; you also time 50 consecutive edits on the dev server (p95 at or under 1,000 ms).
Tier: A (a strike move or a typed price changes the money numbers and re-captures planned entries from the live feed; 1,000 product lines is the reading limit: if you are over it at the AC-5 / AC-6 point of REQ-078, push REQ-076 + REQ-077 as branch part 1 and REQ-078 as a stacked part 2 and say so in the report).

## Work item
The orchestrator allocates the W-id, writes `work/W-1xx.md` (requirement_ids REQ-076, REQ-077, REQ-078) and its row in `docs/process/coverage-stages.yaml`; commit them unchanged.

## Spec basis (quoted; ADR-165 scope: no order is sent, Execute is switched off in Step 1)
REQ-076 AC-1: "read from the instrument file, never strike plus a typed constant"
REQ-076 AC-1: "At the lowest or highest listed strike the button is disabled and says why. A futures leg has no stepper."
REQ-076 AC-2: "A stepped leg is a new contract, so its planned entry is captured again from that contract's LTP (mid of bid and ask when it has no LTP) with the new capture time"
REQ-076 AC-3: "the browser computes no P&L, payoff, margin or Greek"
REQ-076 AC-4: "A strategy-level multiplier (whole numbers 1 to 50) sets each leg's lots to that leg's base lots times the multiplier; setting it back to 1 returns every leg to its base lots."
REQ-076 AC-5: "quantity is always lots times the lot size read from the instrument file for that contract, never a typed lot size"
REQ-076 AC-6: "Unticking a leg removes it from every number on screen (summary, payoff, scenario table, margin, Greeks), recomputed by the engine for the remaining legs"
REQ-076 AC-7: "The tick state is never saved and never reaches the execution plan"
REQ-076 AC-8: "The leg list shows the name of the template the engine matched for the current leg set"
REQ-076 AC-8: "Name and marks come from the server reply and update on every edit."
REQ-076 AC-9: "The shape name is a label only: it never adds, removes, reorders or changes a leg"
REQ-076 AC-10: "Steppers, multiplier and toggles keep working without live data"
REQ-077 AC-1: "Each leg's planned entry can be typed by the user."
REQ-077 AC-2: "A typed price must be a positive multiple of the contract's tick size read from the instrument file"
REQ-077 AC-3: "Every expiry scenario value, max profit, max loss, breakeven, net premium and charge estimate uses the typed price as that leg's entry, computed by the engine"
REQ-077 AC-4: "A typed price is saved with the definition, marked as typed, with its time"
REQ-077 AC-5: "Reset Prices re-captures every leg's planned entry from its current LTP (the mid of bid and ask when there is no LTP), with one new capture time"
REQ-077 AC-6: "The marker never changes any number: the scenarios keep using the planned entry until the user presses Reset Prices or the leg's reset"
REQ-077 AC-7: "nothing is captured on reopening"
REQ-077 AC-9: "No typed price is ever shown as a live market price"
REQ-078 AC-1: "Core proof first, before any screen work"
REQ-078 AC-1: "the 95th-percentile reply at or under 1,000 ms"
REQ-078 AC-2: "Shift works for any shape, Custom Strategy included; Width only for straddles, strangles, iron butterflies and iron condors; Hedge only for vertical spreads, iron butterflies and iron condors"
REQ-078 AC-3: "Shift +1 / -1 moves every option leg by one strike step of the underlying"
REQ-078 AC-4: "every call leg moves up one step and every put leg moves down one step (reversed for -1)"
REQ-078 AC-5: "Hedge +1 / -1 moves only the legs marked Hedge"
REQ-078 AC-6: "The browser sends only the control and its direction"
REQ-078 AC-6: "the whole move is refused and nothing changes"
REQ-078 AC-7: "it never adds or removes a leg and never changes a side, lots, expiry or option type"
REQ-078 AC-8: "Every moved leg is a new contract and gets a newly captured planned entry with the move time"
REQ-078 AC-9: "A manual strike edit (stepper or picker) resets the Shift total to 0."
REQ-078 AC-10: "never computed from yesterday's list"
Scope change from ADR-165: REQ-076 AC-7's Execute refusal and REQ-077 AC-8's Execute review are moot while Execute is off; keep only what is testable now (tick state absent from the saved definition; a typed price never leaves the planning numbers).

## Copy from
Copy from: spec/technical-design/legacy-reuse.md frontend section, row `src/views/StrategyBuilderView.vue` + `stores/strategy.js` (ADAPT, P4): layout idea of the leg row only; delete client P&L and price fallbacks. Row `src/components/strategy/StrategyLegRow.vue` (ADAPT): the in-repo copy is read-only; extend, do not re-copy. Shift / Width / Hedge, multiplier and typed price have no algochanakya row: Copy from: none - the rules are in REQ-078 and in the Sensibull bundle notes below (a new server module).

## Sensibull screens (open before writing a screen; study folder D:\Abhay\Ventures\competitors\sensibull\2026-10-21\, INDEX.md numbering; never copy a screenshot or account data into the repo)
- 011/012: one leg row = tick | B/S | expiry | strike with -/+ | CE/PE | lots | editable price with a corner marker | depth icon | delete; header '2 selected - Bull Call Spread', Clear, Reset Prices.
- 108-110: Shift, Width, Hedge steppers (Shift shows the cumulative move, resets after a Width change); bundle-findings.md section 7.2 gives the exact rules (step = strike gap; Width step = 2 gaps; Hedge min = 1 gap, even number of legs, at most 4).
- 100-134 (deep dive): shape auto-detection, UN_KNOWN shapes get no controls, lots dropdown, multiplier, tick box; 209-211: 'Prices have changed' marker and Reset Prices (measured 188.05 -> 189.80); 230-233: per-index step and width; 244-245: Lots vs Qty.
- Differences kept on purpose (ADR-152 exceptions): Sensibull sends only ticked legs ('Trade 3'); here an unticked leg never reaches any plan.

## What to build
1. `backend/ofo/strategy/leg_edit.py` (new, stdlib + Decimal): `step_strike`, `apply_multiplier`, `include_leg`, `shift`, `width`, `hedge`, each pure, taking the listed strikes from the catalogue (`Catalogue.strike_gap`, `contracts_for`); one refusal type that names the leg and strike.
2. Hedge marks: add `protective: true` to template legs in `backend/ofo/strategy/catalogue.yaml`, `template.schema.json`, `model.py` (TemplateLeg) and `loader.py`; `matching.py` returns the matched template's protective legs. Data only, no per-strategy code (REQ-028 AC-5).
3. Typed price and tick size: `Catalogue.tick_size` exists (`instruments/catalogue.py:339`) and has no caller yet; validate typed prices with it and the four-part catalogue error (see `ofo/errors`).
4. Outcome: `OutcomeLeg` (`ofo/outcome/service.py`) gains `included`, `price_source` (captured or typed), `price_moved` (planned vs live LTP) and the shape name + hedge mark; `serialize.py` and the `LegIn` / `OutcomeRequest` models in `ofo_app/routes/outcome.py` carry them; the engine receives only included legs.
5. New route `POST /api/strategies/leg-edit` (`ofo_app/routes/leg_edit.py`, registered in `main.py`): body = current legs + one edit; reply = new legs + the outcome. Planned entries re-captured through the existing `routes/planned_entry.py` helper, not a second capture path. Regenerate `docs/api/openapi.json`; register new ApiModel classes in `tests_app/test_response_door.py`.
6. Stored form: a typed mark persists with the entry (`ENTRY_LEG_KEYS` in `ofo/strategy/stored_form.py`); the tick state is NOT stored. Check the stored-form version rule before changing the key set.
7. Frontend: `components/strategy/LegList.vue` (rows with tick, stepper, lots, price box with marker), `components/strategy/StrategyControls.vue` (Multiplier, Shift / Width / Hedge, Reset Prices), wiring in `pages/StrategyBuilderPage.vue`, `lib/legEdit.js` (builds the request only). Late replies: the newest request wins (same pattern as `seq` in `LegPicker.vue`).
8. Builder history: every Shift / Width / Hedge click is one history entry (`ofo/strategy/builder_history.py` already has `change_strike`); add the three labels in the catalogue wording file.

## AC status (checked on main + branches gc6/create-guided #457 and gc6/w118-sel #466; no evidence/ file exists for any of these REQs)
| AC | Status |
|---|---|
| REQ-076 AC-1 stepper | missing (no stepper in `LegPicker.vue`; `BuilderSession.change_strike` exists in `ofo/strategy/builder_history.py:235`, domain only) |
| REQ-076 AC-2 re-capture | partial (`routes/planned_entry.py:108` captures on add; not on a step) |
| REQ-076 AC-3 server numbers | partial (`routes/outcome.py:466` recomputes; no edit route) |
| REQ-076 AC-4 multiplier | missing |
| REQ-076 AC-5 lots / quantity / freeze reason | partial (`OutcomeLeg` has lots, lot_size, quantity; no per-leg block reason) |
| REQ-076 AC-6 include tick | missing |
| REQ-076 AC-7 | reduced by ADR-165 (see Spec basis) |
| REQ-076 AC-8 / AC-9 shape name, Hedge mark | partial (`ofo/strategy/matching.py` match() and CUSTOM_STRATEGY exist; not in the outcome reply; no protective flag in templates) |
| REQ-076 AC-10 empty / stale | partial (`EmptyState.vue`, not-connected outcome) |
| REQ-077 AC-1..AC-2 typed price | missing (tick size unused) |
| REQ-077 AC-3 | partial (engine uses `LegIn.planned_entry`, so a typed price already flows once sent) |
| REQ-077 AC-4 saved + mark | partial (entry saved by `stored_form.py`; no typed mark) |
| REQ-077 AC-5 Reset Prices | missing |
| REQ-077 AC-6 moved marker | missing |
| REQ-077 AC-7 reopen | partial (`REPRICE_PROMPT` in `lib/legPicker.js`) |
| REQ-077 AC-8 | reduced by ADR-165 |
| REQ-077 AC-9 | partial |
| REQ-078 AC-1 core | missing (builder part: this brief's step 1; live run: orchestrator) |
| REQ-078 AC-2..AC-9 | missing |
| REQ-078 AC-10 | partial (instrument-file freshness is lane C, Step 3; read the loaded-today flag it exposes; until it lands, disable when the catalogue date is not today) |

## Attack cases
Step at the last listed strike (disabled, reason shown); a strike gap that jumps (23,000 -> 23,100 far from the money); Shift that would land one leg on an unlisted strike (whole move refused, no leg changed); Width -1 at width 0; Width on a Custom Strategy (disabled with reason); Hedge on 6 legs; futures leg with Shift (does not move); typed 81.32 on tick 0.05 (refused, previous price stays); typed price then Shift (typed price replaced, screen says so); unticking the bought wing (Max loss reads Unlimited); multiplier 50 with a leg over its freeze limit (block reason on that leg, never split); two edits fired fast (older reply never draws over the newer); edit with no live data (strikes move, numbers follow REQ-077 AC-9); reply for a stepped leg whose new contract has no LTP and no bid / ask (unpriced state, ADR-085 prompt).

Threat model: in scope a forged or stale edit body (strike not listed, lots outside 1..10000, a tick state or typed flag smuggled into the saved definition, an edit applied to a different leg set than the server holds); out of scope a user editing their own browser state to see their own numbers differently (the server recomputes).

## Findings checked
Findings checked: money-value-computed-outside-engine, money-parsed-through-float, fallback-time-claims-missing-data, last-live-answer-kept-after-drop, instrument-identity-keyed-on-one-broker, state-read-after-await, test-asserts-implementation-output, targeted-tests-miss-dependent-files, guard-without-killing-test

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step gains an import; (c) applied: any scan test you add (a grep that no frontend file computes money) fails closed on re-exports and names the helper by import source; (d) applied: answer states of the instrument file and the feed are listed as attack cases above (listed strike, unlisted strike, no LTP, no bid / ask, feed down, catalogue not loaded today) and each has a test.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Targeted tests: tests/strategy/test_leg_edit.py (new), tests/strategy/test_matching.py, tests/strategy/test_builder_history.py, tests_app/test_leg_edit_route.py (new), tests_app/test_outcome_route.py, tests_app/test_response_door.py; frontend: `npx vitest run tests/leg-edit.test.js tests/strategy-table.test.js`, `npm run lint`, `npm run build`. Grep tests/, tests_app/, frontend/tests/ and frontend/e2e/ for every old value you change.
Rules: no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR (the one exception is docs/api/openapi.json when an API model changes)
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Open
Open: technical: which leg of a vertical spread carries the Hedge mark. Spec basis: REQ-076 AC-8 says 'protective' and REQ-078 AC-2 lists vertical spreads; the study (bundle-findings 7.2) says the server marks them and does not list which. Proposal: the Hedge leg is the leg farther from the money in each vertical pair or wing (condor / butterfly wings, the bought leg of a credit spread, the sold leg of a debit spread); open screens 108-110 and the preset-matrix.md rows for a bull call spread first and follow what they show; if they show nothing, use the proposal and record it as a decision row.
Open: technical: Start tracking (REQ-109) with an unticked leg. Proposal: refused with the reason 'Tick every leg to track: the whole strategy is tracked as one plan.' (same reasoning as REQ-076 AC-7, text lives in the wording catalogue); decision row to be written by the orchestrator.
