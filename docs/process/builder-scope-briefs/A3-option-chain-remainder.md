# W-1xx builder brief (lane A3): Option Chain remainder - Advanced columns, display options, selection checks, live preview

Common brief: docs/process/builder-brief.md
Core: the Option Chain's server reply carries every extra value (per-lot premium, intrinsic value, time value, breakeven %, Zerodha eligibility per contract, the engine's preview numbers for the selected legs) so the screen only draws strings.
Proof: step 1 is a server test on the recorded chain frames: NIFTY 22,900 CE, LTP 150.00, spot 22,976.85 returns intrinsic 76.85, time value 73.15, breakeven 23,050 (+0.32%) and LTP per lot (65) 9,750.00 (hand computation written first, REQ-087 AC-4 example); the same rows with no spot return a dash, not 0.
Tier: A (server money strings from the live feed, engine numbers in the preview, a new per-user setting table = migration).

## Work item
The orchestrator allocates the W-id, writes `work/W-1xx.md` (requirement_ids REQ-029, REQ-030, REQ-031, REQ-087) and its coverage-stages row; commit them unchanged. Start from main AFTER #466 (W-120, gc6/w118-sel) and #457 are merged tonight; if #466 is not merged yet, branch from `gc6/w118-sel`.

## Spec basis (quoted; remaining ACs only, the ones already verified are listed in the status table)
REQ-029 AC-3: "Advanced Details adds Bid/Ask, Delta, Gamma, Theta, Vega, OI Change and other advanced fields"
REQ-029 AC-5: "The chain is reachable from the Strategy Builder ('Select from Option Chain') and from Market"
REQ-029 AC-9: "Filters adapt to UX level"
REQ-029 AC-10: "the chain can browse another expiry and import from it without changing the strategy's expiry, and every leg shows its expiry"
REQ-030 AC-3: "the Builder is the default and authoritative place where the whole strategy is reviewed before execution"
REQ-030 AC-7: "exact quantity entry is available in Advanced"
REQ-030 AC-12: "Selecting a contract already in the strategy asks: increase quantity / keep separate / cancel"
REQ-030 AC-13: "Selections are validated before import against: duplicate contracts, same contract with opposite actions, mixed expiries, invalid/unavailable contracts, invalid lot quantities, contracts Zerodha currently does not permit"
REQ-030 AC-14: "Matching templates are identified but the selection is never auto-converted or auto-executed"
REQ-030 AC-16: "A contract Zerodha currently won't accept stays visible"
REQ-031 AC-1: "The selection area shows net premium (credit/debit), max profit, max loss, breakevens and a mini payoff graph"
REQ-031 AC-2: "The preview updates live as legs are added/removed or quantities change."
REQ-031 AC-3: "The full scenario table, Greeks and detailed analysis stay in the Strategy Builder."
REQ-087 AC-1: "every premium times the contract's lot size read from the instrument file, with the lot size in the column heading"
REQ-087 AC-2: "In-the-money cells are shaded: calls with a strike below spot, puts with a strike above spot"
REQ-087 AC-3: "kept as a per-user preference"
REQ-087 AC-4: "each side adds intrinsic value (against spot, labelled so), time value (LTP minus intrinsic) and breakeven %"
REQ-087 AC-5: "A cell whose input is missing (no LTP, no spot)"
Not in this PR: REQ-029 AC-7 (live chain only for logged-in Pro users) is launch scope (login REQ-012, plans REQ-017-023, ADR-165 (8)); the chain stays open to the one fixed owner.

## Copy from
Copy from: spec/technical-design/legacy-reuse.md frontend section, rows `src/stores/optionchain.js` (550), `views/OptionChainView.vue` (1240), `components/optionchain/StrikeFinder.vue` (ADAPT, P3b / P5: no local ATM fallback at `:155`, strike logic in the backend); services section row `option_chain_live_engine.py` (ADAPT). The in-repo chain read and screen are already the adapted copy (W-116, W-118): extend them. Per-lot / intrinsic / breakeven columns and the preview: Copy from: none - no algochanakya row.

## Sensibull screens (study folder D:\Abhay\Ventures\competitors\sensibull\2026-10-21\; never copy a screenshot or account data into the repo)
- 060-067 Option Chain (catalogue-raw.md last section): header with expiry list '27 Oct (6 Days)', Fut price, INDIAVIX, Per Lot toggle (702.65 -> 45,672); LTP view, Greeks view, All Column view (OI chg, Bid, Offer, Intrinsic Val, Time Value, Breakeven %); ITM shaded; ATM row bold; settings: Lots / Qty, strikes 10 / 20 / 30 / 40 around ATM, 'Show 100 multiples only'; row hover B | S.
- 032-038 and 011/012: how selected contracts become builder legs ('2 legs selected', Done).
- docs/design/screens-research-2026-10-19.md section Option Chain (in this repo) is the project's own reading of these screens: follow its content list.
- Differences kept on purpose: no quick-trade lightning button, no order of any kind from the chain (REQ-029 AC-6, ADR-002).

## What to build
1. Server: extend `ChainCellOut` / `ChainRowOut` in `ofo_app/chain_push.py` with per-lot value, intrinsic value, time value, breakeven and breakeven %, Greeks at Advanced (from the engine, not the vendor), and `zerodha_permitted` per contract (reuse `ofo/instruments/eligibility.py` and `ofo_app/eligibility_from_zerodha.py`); every value a money string or a dash with a reason.
2. `POST /api/market/chain/preview` (`ofo_app/routes/chain.py`): the selected legs in, the outcome route's summary numbers out (net premium, max profit, max loss, breakevens, payoff points); reuse the outcome builder, never a second engine call path.
3. Migration + store for a small per-user setting table (key, JSON value, updated_at, keyed by the session's user reference, today the one fixed owner; code takes the user from the session and never hard-codes the owner, ADR-165 (8)): first use is strikes-each-side (REQ-087 AC-3). B1 (margin preference) and A4 (strategy preferences) reuse this table: write it generic, `ofo_app/user_setting_store.py`, with its own migration and `PINNED_BODIES` if it pins a function body.
4. Frontend: `pages/OptionChainPage.vue` gains the Per lot toggle, ITM shading, 10 / 20 / 30 / 40 selector, Advanced column set, UX-level filters, an eligibility badge 'Currently unavailable on Zerodha' with Add disabled and Refresh (REQ-030 AC-16), the AC-12 prompt (increase quantity / keep separate / cancel), exact quantity entry at Advanced, the live preview panel with a mini payoff, and the 'Select from Option Chain' entry in the Builder (`StrategyBuilderPage.vue`) and Market nav.
5. AC-14: the selection summary shows the matched template name from `ofo/strategy/matching.py` match(); the selection is never converted.
6. Regenerate `docs/api/openapi.json`; register new ApiModel classes in `tests_app/test_response_door.py`.

## AC status (main + #466 gc6/w118-sel + evidence/)
| AC | Status |
|---|---|
| REQ-029 AC-1, AC-2, AC-4, AC-6, AC-8 | exists, verified (evidence/W-116: AC-1, AC-4, AC-8; evidence/W-118: AC-1, AC-2, AC-6, AC-8); not re-briefed |
| REQ-029 AC-3 Advanced columns | partial (bid / ask / OI change in `ChainCellOut`; Greeks missing) |
| REQ-029 AC-5 reachable from Builder and Market | partial (Market route exists; Builder entry missing) |
| REQ-029 AC-7 Pro-only | launch scope, not built |
| REQ-029 AC-9 UX-level filters | missing |
| REQ-029 AC-10 other expiry import | partial (selection persists across expiries in #466; the Builder's own expiry rule not enforced) |
| REQ-030 AC-1, AC-2, AC-4, AC-5, AC-6, AC-7 stepper, AC-8, AC-9, AC-10, AC-11, AC-15 | exists on #466 (`frontend/src/stores/chainSelection.js`, W-120); not re-briefed |
| REQ-030 AC-3, AC-7 exact quantity | missing (W-120 left Advanced quantity out) |
| REQ-030 AC-12 | missing |
| REQ-030 AC-13, AC-16 | missing (needs the eligibility field above) |
| REQ-030 AC-14 | missing |
| REQ-031 AC-1..AC-3 | missing |
| REQ-087 AC-1..AC-5 | missing |

## Attack cases
Spot stale or missing (shading off with the reason; per-lot unaffected; intrinsic dashes); LTP missing on one side (dash, never 0); LTP 0 from the feed (absent, F-29); put breakeven below zero strike edge; same contract picked twice in two expiries; Buy and Sell of one contract (two legs, no netting); preview with 1 leg of unlimited loss (Unlimited, not a number); preview while the feed drops (last numbers marked stale, not live); contract not permitted by Zerodha (visible, not addable, reason shown); preference read for a user who never set one (default 10); SENSEX lot 20.

## Findings checked
Findings checked: money-value-computed-outside-engine, money-parsed-through-float, fallback-time-claims-missing-data, liveness-from-shared-subscribers, last-live-answer-kept-after-drop, positions-reply-refused-for-non-platform-rows, trust-broker-status-word, outcome-multi-expiry-unhandled-500, test-asserts-implementation-output

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step gains an import; (c) n/a: no static detector added; (d) applied: eligibility answer states are permitted, not permitted, reply absent, read failed, ambiguous contract; each maps to badge, dash or block with its own test.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Targeted tests: tests_app/test_chain_live.py, tests_app/test_chain_permissions.py (from #466), tests_app/test_chain_preview.py (new), tests_app/test_user_setting_store.py (new, runs its own file: it is a migration / DB store), tests_app/test_response_door.py; frontend: `npx vitest run tests/option-chain.test.js tests/chain-selection.test.js tests/chain-display.test.js`, `npm run lint`, `npm run build`.
Rules: no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR (the one exception is docs/api/openapi.json when an API model changes)
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Open
Open: technical: the per-user setting store is created here and reused by B1 and A4; whichever PR merges first owns the migration number. Proposal: A3 merges first (index order); the others rebase onto it.
Open: technical: W-120 recorded 'AC-5 combine rule' as an open owner call. REQ-030 AC-5 and AC-11 are already unambiguous in the spec (same contract and action combines; opposite actions stay two legs), so no owner question is needed; build to the text.
Open: business: none found in these REQs.

## Legacy map rows (copy_from_check.py)
Rows of spec/technical-design/legacy-reuse.md that name this brief's requirements. Act on each:
COPY/ADAPT -> use it (provenance header) or write in the report why not; REFERENCE -> read before
designing; SKIP -> do not re-survey.

| `app/utils/jwt.py` (63), `dependencies.py` (171), `user_resolver.py` (105), `app/api/routes/auth.py` (515), `app/models/users.py` (60) | SKIP | legacy auth/users (Kite-as-login; token embeds broker connection) | REQ-012 |
| `src/views/LoginView.vue` (606), `SettingsView.vue` (608), `stores/auth.js` (263) | ADAPT (P2b) | Google + WhatsApp OTP, Zerodha connect, cookie auth | REQ-012, REQ-013 |
