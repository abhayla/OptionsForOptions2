# W-1xx builder brief (lane A2): Leg picker with live prices per strike, depth popup per leg, futures and forward price

Common brief: docs/process/builder-brief.md
Core: the picker's strike table and the depth popup are drawn from ONE server read of the user's own live feed (at most once a second), with the forward level the engine prices each expiry with.
Proof: step 1 is a server read test on the recorded Kite frames (`tests/fixtures/kite_ws/`, frame mode 184 carries five depth levels, `ofo/marketdata/kite_frames.py:31-33`): the read returns 5 bid and 5 ask levels with quantities for one NIFTY option, the strike rows for ATM +/- 10, and the parity forward for the nearest expiry; each value is compared with the recorded frame by hand-written expected values. The live-window run is the orchestrator's.
Tier: A (reads the live feed; the forward level feeds pricing).

## Work item
The orchestrator allocates the W-id, writes `work/W-1xx.md` (requirement_ids REQ-080) and its row in `docs/process/coverage-stages.yaml`; commit them unchanged.

## Spec basis (quoted)
REQ-080 AC-1: "The Strikes tab lists strikes around ATM (10 each side by default; 10 / 20 / 30 / 40 selectable) with ATM highlighted."
REQ-080 AC-2: "Prices come from the platform's own feed over its socket at most once a second"
REQ-080 AC-3: "Buy and Sell choose the leg's side only; the picker never places an order"
REQ-080 AC-4: "Quantity mode (Advanced) lists multiples of the lot size read from the instrument file"
REQ-080 AC-5: "legs can still be added and show the ADR-085 reprice prompt until a price exists. No stale price is shown as current"
REQ-080 AC-6: "The Futures tab lists every listed futures expiry of the underlying with its LTP"
REQ-080 AC-7: "5 levels of bid and ask with quantities"
REQ-080 AC-7: "The popup has no order button."
REQ-080 AC-8: "never an empty or old table"

## Copy from
Copy from: spec/technical-design/legacy-reuse.md frontend section, rows `src/stores/optionchain.js`, `views/OptionChainView.vue`, `components/optionchain/StrikeFinder.vue` (ADAPT, P3b / P5: no local ATM fallback, strike logic in the backend) for the strike-table layout idea only. Backend: row 5 / `option_chain_live_engine.py` (ADAPT): the in-repo chain read (`ofo_app/chain_push.py`) is the adapted copy; reuse it. Futures and forward tab, depth popup: Copy from: none - no algochanakya row; the forward comes from `ofo/marketdata/forward.py` (`parity_forward`, `spot_fallback_forward`).

## Sensibull screens (study folder D:\Abhay\Ventures\competitors\sensibull\2026-10-21\; never copy a screenshot or account data into the repo)
- 032-038: Add/Edit drawer = leg picker: tabs Straddles | Strangles | Strikes | Futures; expiry select; LTP / OI / Greeks column sets; per-strike B / S buttons + Qty; footer '2 legs selected', Clear All, Done. Build the Strikes and Futures tabs here; the Straddles and Strangles quick picks are REQ-079 (held, lane B4) and are NOT in this PR.
- 024: depth popup per leg (Open / High / Low / Close, best bid / offer with quantity); 025: Lots vs Qty setting; 244-245: Qty column lists 65, 130, 195.
- 026-031: Info panel 'Fut. Prices' tab (real + synthetic futures per expiry) = the Futures tab with the forward used for pricing.
- Difference kept on purpose: the popup has no order button (ADR-002; Sensibull's depth sits inside its basket sheet, screens 040-044).

## What to build
1. `ofo_app/routes/leg_picker.py` (new): `GET /api/market/strikes` (underlying, expiry, each_side 10|20|30|40) returning rows: strike, CE and PE LTP, OI, and at Advanced IV and delta from the engine; `GET /api/market/depth` (instrument id) returning five levels each side with quantities, open / high / low, previous close where the frame carries it (F-47), last trade time, the time read; `GET /api/market/futures` (underlying) returning each listed futures expiry with LTP and, per option expiry, the forward level with its label. All money as strings; reuse `chain_push.py` window helpers (`pick_window`, `window_ids`) and the one shared fan-out, never a vendor connection per browser.
2. Depth: `NormalizedQuote` (`ofo/marketdata/quote.py`) carries only best bid / ask; add a depth structure read from the same frame decoder (`kite_frames.py`), Decimal prices, integer quantities, price 0 = absent (F-29). A frame without depth gives 'Depth not available' with the reason.
3. Refresh: server pushes at most once a second per open popup / table (reuse the chain socket's limiter); closing the popup stops it. A subscription taken for the popup is released on close and not lost on re-acquire (finding live-subscription-lost-on-release-reacquire).
4. Frontend: extend `components/strategy/LegPicker.vue` (today: one leg at a time, underlying -> expiry -> type -> strike -> side -> lots) into a drawer with a Strikes tab (table, multi-select, Buy / Sell, lots or quantity selector, Done adds all legs each with a planned entry captured through `routes/planned_entry.py`) and a Futures tab; `components/strategy/DepthPopup.vue` (new, opened from a depth icon on each leg row; no order button); `lib/legPicker.js` for request building.
5. Underlying locked while legs exist (ADR-019, already true in `LegPicker.vue`): keep it.
6. Regenerate `docs/api/openapi.json`; register new ApiModel classes in `tests_app/test_response_door.py`.

## AC status (main + branches #457 gc6/create-guided, #466 gc6/w118-sel; no evidence/ file for REQ-080)
| AC | Status |
|---|---|
| AC-1 Strikes tab, ATM +/- n | missing (`LegPicker.vue` is a single-leg form; chain screen shows ATM rows, `ofo_app/chain_push.py`) |
| AC-2 LTP / OI / IV / delta per strike | partial (chain rows carry LTP, OI, bid, ask; IV and delta per strike not served) |
| AC-3 multi-select + Done | missing |
| AC-4 quantity mode | missing (lot size via `Catalogue.lot_size`, `instruments/catalogue.py:316`) |
| AC-5 no live data | partial (reprice prompt exists, `REPRICE_PROMPT` in `lib/legPicker.js`) |
| AC-6 Futures tab + forward | missing (forward logic in `ofo/marketdata/forward.py`, no route) |
| AC-7 depth popup | missing (frames decode five levels, quote model keeps best bid / ask only) |
| AC-8 depth not available | missing |

## Attack cases
Frame without depth (mode 44 quote); depth price 0 on one level (shown as absent); instrument not streaming; feed stale (the table and popup say so, no old numbers); 40 strikes each side = 160 subscriptions (cap respects the 3000-token feed limit); ATM tie (nearest strike, lower on a tie); picker opened with legs of another underlying (locked); two popups opened and closed fast (subscription count returns to its start value); parity forward unavailable (fall back to spot forward and label it); user without a Zerodha session (rows show a dash and the reason above the list); SENSEX (lot 20, strike gap 100) as well as NIFTY.

## Findings checked
Findings checked: live-subscription-lost-on-release-reacquire, liveness-from-shared-subscribers, last-live-answer-kept-after-drop, freshness-judged-on-request-start-clock, fallback-time-claims-missing-data, daily-list-trims-far-strikes-trips-truncation-guard, aggregate-across-mixed-instrument-kinds, instrument-identity-keyed-on-one-broker, money-parsed-through-float

Standing items: (a) applied: the depth / table push reuses the chain socket's existing once-a-second limiter and its small subscription reservation; a test shows the shared index and chain subscriptions still run while 3 popups are open; (b) n/a: no CI step gains an import; (c) n/a: no static detector added; (d) applied: depth answer states are stated, absent price 0, absent frame, instrument not streaming, feed stale, Zerodha session missing; each has a test and a message.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Targeted tests: tests/marketdata/ (frame and quote tests you touch), tests_app/test_chain_live.py, tests_app/test_leg_picker_routes.py (new), tests_app/test_response_door.py; frontend: `npx vitest run tests/leg-picker.test.js tests/depth-popup.test.js`, `npm run lint`, `npm run build`.
Rules: no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR (the one exception is docs/api/openapi.json when an API model changes)
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Open
Open: technical: where the Straddles / Strangles tabs of screens 032-038 live. They place strikes by a fixed rule (REQ-079, held for Q211), so they are built in lane B4, switched off; this PR leaves a tab slot that renders nothing until that switch is on. Decision proposed: leave the slot out of this PR and let B4 add it.
Open: technical: IV and delta per strike at Advanced come from the engine per strike; if serving 80 strikes at once is slower than 1 s, compute only the visible window and say so. No business question.
