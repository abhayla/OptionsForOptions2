# Sensibull vs OFO2 gap list (2026-10-21)

How to read: one row per Sensibull capability seen on 2026-10-21 (screen numbers point to `README.md` sections and the
owner's local screenshots). "OFO2 status" was checked against `main` at `c040b7b6` (the merge of PR #489), never from
memory:
- **Built** - code for it is on `main` and reachable (a file and line, or a done work item `W-###`).
- **Partial** - some of it is on `main`; the cell says which part is missing.
- **Missing** - searched and not found; the search is named.
- **Held** - built on a branch or open PR, not on `main` (PR number given).
- **Excluded-by-ADR-xxx** - an owner decision rules it out; the quote is in the appendix at the end.

Note on work-item status: several work files still say `todo` although their screen is on `main` (W-115 Home, W-117
Learn/Alerts, W-118 Option Chain). The code wins here; the stale status is a bookkeeping gap, not a product gap.

Value = value to an OFO2 user (beginner/intermediate options seller planning a NIFTY/SENSEX strategy; ADR-004).
Effort: S = under a day, M = 1-3 days, L = a week or more (rough, one builder + one review).

## 1. Strategy Builder (Sensibull 010-039, 100-134)

| # | Capability | Sensibull (screen) | OFO2 status | OFO2 evidence | Value | Effort | Notes |
|---|---|---|---|---|---|---|---|
| B1 | Builder screen reachable from the menu | 010 | Built | `frontend/src/router/routes.js:11` `'strategies-strategy-builder': () => import('../pages/StrategyBuilderPage.vue')`; W-064 done | H - the prime workflow (ADR-007) | - | F-49 fixed by GC-6 BUILDER-WIRE |
| B2 | Underlyings NIFTY + SENSEX | 010, 143 | Built | `frontend/src/components/strategy/LegPicker.vue` UNDERLYINGS; REQ-001 Verified | H | - | |
| B3 | BANKNIFTY, FINNIFTY, stock options | 143 | Excluded-by-ADR-001 | ADR-001 "underlyings NIFTY (NSE) and SENSEX (BSE)" | M | L | Later scope question, not a gap now |
| B4 | Ready-made catalogue that loads legs at ATM-relative strikes in one click | 010-012, 100 | Partial | 21 templates as data (`backend/ofo/strategy/catalogue.yaml`, W-005, W-047) but shown only on Learn: `backend/ofo_app/routes/strategy_templates.py:1` "the reviewed strategy templates for the Learn page"; no builder loader (grep `strategy-templates` in `frontend/src`: only `LearnPage.vue`) | H - fastest way for a beginner to start | M | Sensibull places strikes by a fixed rule from ATM (README 1.7c); platform-placed strikes are limited by ADR-055 (1); see SPEC CHANGE S2 in the plan |
| B5 | Shape auto-name ("Bull Call Spread", "Custom") on the leg list | 011, 101 | Partial | Matcher exists `backend/ofo/strategy/matching.py:1` "Match a concrete leg set to the parametric template it fits ... or say it is Custom"; used only by `reconciliation/grouping.py` and `loader.py` (grep `from ofo.strategy.matching`), not by the outcome API or screen | M | S | |
| B6 | Per-leg expiry (calendars, diagonals) | 101, 108 | Partial | Expiry chosen per leg in `LegPicker.vue` (`/catalogue/{u}/expiries`); ADR-006 per-leg expiries; engine returns no worst-case loss for mixed expiries (ADR-143) | M | M | Sensibull values the later leg by model at the first expiry |
| B7 | Strike -/+ stepper on each leg | 011, 101 | Missing | `LegPicker.vue` uses a strike dropdown from `offeredStrikes(...)` (line 45); grep `stepper` in `frontend/src`: 0 hits | H - the most-used edit | S | |
| B8 | Shift / Width / Hedge strike controls | 101-110 | Missing | grep `shift|width|hedge` in `LegPicker.vue`: 0 hits; no engine function | H - adjust a whole shape in one click | M | Sensibull rules (steps, which shapes) are in README 1.3; OFO2 should compute them on the server (ADR-008) |
| B9 | Lots per leg | 011 | Built | `LegPicker.vue:34` `const lots = ref(1)`; `lotsValid` | H | - | |
| B10 | Multiplier (scale every leg) | 107 | Missing | grep `multiplier` in `frontend/src`: 0 hits | M | S | |
| B11 | Include / exclude a leg from the numbers (tick box) | 101-103 | Missing | No tick box in `LegPicker.vue` (grep `checkbox`: 0 hits) | M - "what if I drop the hedge?" | S | Must be analysis-only: Execute always sends the whole strategy (see section "must be different") |
| B12 | Editable entry price per leg, Reset Prices | 011, 101 | Partial | Planned entry is captured from live and kept (`LegPicker.vue:154` "A priced leg keeps its captured entry"); no manual price field found in `LegPicker.vue` | M | S | ADR-068/075 define planned entry; a typed price needs a rule (labelled "your price") |
| B13 | Per-leg depth popup | 024 | Partial | 5-level depth kept for Execute pricing (W-097 in_review); not on the Builder screen | L | S | |
| B14 | Net premium "Pay / Get" line | 012 | Partial | Net premium is in the Execute reply (W-102, `frontend/src/components/execution/ExecuteCost.vue`); not on the Builder summary (grep `net_premium` in `backend/ofo_app/routes/outcome.py`: 0 hits) | M | S | Engine extension (Tier A), then display |
| B15 | Charges breakdown popup | 022 | Partial | Round-trip charges inside max-profit/loss (W-075; `outcome.py:282` `charges: Optional[Money] = None  # W-075`); total on Execute (`ExecuteCost.vue:14-15`); no itemised breakdown on screen | L | S | Rates engine W-074 already itemises; exposing it is an engine/API extension (Tier A), then display |
| B16 | Max profit / max loss tiles | 012 | Built | `frontend/src/components/strategy/SummaryCards.vue`; W-001, W-064 | H | - | OFO2 adds plain-language sentences (REQ-034 AC-7) |
| B17 | Breakevens at expiry | 012 | Built | `SummaryCards` `:breakevens`; Lower/Upper BE labels W-082 | H | - | |
| B18 | Breakeven at target date | 012, 129 | Missing | No target date in OFO2 (ADR-120); Estimated Now is "now", not a chosen date | M | M | Depends on SPEC CHANGE S1 |
| B19 | Reward / Risk ratio | 012, 126 | Missing | `SummaryCards.vue:3-4` "the Risk/Reward card is dropped (a ratio would be client maths and the API sends none)" | M | S | Engine extension (Tier A), then display |
| B20 | POP (probability of profit) | 012 | Missing | grep `\bpop\b|probability` in `backend` + `frontend/src`: only Python `.pop()` calls | H - beginners ask "how likely" | M | Wording risk under ADR-055 (1); see owner decision D4 |
| B21 | Time value / intrinsic value totals | 012, 127 | Missing | grep `intrinsic|time_value` in `outcome.py`: 0 hits | L | S | |
| B22 | Funds needed, margin needed, margin available | 012, 128 | Built | `frontend/src/components/strategy/MarginLine.vue:2` "ADR-099: Zerodha's margin for the planned orders, in the outcome screen's margin slot" | H | - | |
| B23 | Margin shortfall warning in the builder | 039, 139 | Built (better than Sensibull) | `MarginLine.vue:22` `<p v-if="short" ...>Available funds are below the margin needed.</p>` | H | - | Sensibull showed none in the builder |
| B24 | Include existing positions in the margin figure | 012 | Missing | unverified: grep `existing position` in `backend/ofo_app/outcome_margin.py` not run; no toggle in `MarginLine.vue` | M | M | Kite basket margin can take positions into account |
| B25 | Payoff chart at expiry | 013 | Built | `frontend/src/components/strategy/PayoffChart.vue:19` aria-label "Profit and loss at expiry across index levels" | H | - | |
| B26 | Target-date (T+0 / "now") curve on the payoff chart | 013 | Partial | Estimated Now exists as a view (W-090 `ScenarioControls.vue:1` "the At Expiry / Estimated Now switch"); the outcome API returns ONE view per call (`backend/ofo_app/routes/outcome.py:151` `view: Literal["at_expiry", "estimated_now"]`; `PayoffOut` has a single `view` at `:265-267`); `PayoffChart.vue:60-62` draws one series | H - shows today's risk, not only expiry | M | Two calls per edit, or an engine/API extension (Tier A) returning both curves. It overlays the two existing modes; it is not a third ADR-120 mode |
| B27 | Hover tooltip: P&L at that level now and at expiry | 013, 125 | Partial | `PayoffChart.vue:75` tooltip `'P/L: ₹' + pnl` (expiry only) | M | S | |
| B28 | OI bars overlaid on the payoff chart | 013 | Missing | grep `oi` in `PayoffChart.vue`: 0 hits | M | M | OI is already on the chain socket (`backend/ofo_app/chain_push.py:97`) |
| B29 | SD bands / expected move on the chart | 013 | Missing | grep `standard.deviation|sigma` in `backend` + `frontend/src`: 0 hits | M | M | Defined in REQ-027 (Q254: "Expected move (one standard deviation) = spot × ATM implied volatility × √(calendar days to expiry ÷ 365)"); used for the default range in REQ-034 AC-4 |
| B30 | Scenario table: P&L at each index level | 014 | Built (OFO2's core) | Single strategy table with per-leg scenario cells, ADR-008; W-003, W-004, W-064; `StrategyTable.vue` | H | - | Sensibull's table is totals only; OFO2 shows every leg |
| B31 | Range and step of the scenario table | 014 | Built | W-090 (#399 merged): `ScenarioControls.vue:1` "the range pick (the step is the Admin setting)" | M | - | |
| B32 | P&L table per leg (entry, LTP, P&L) | 015 | Built | Table columns Entry Price, LTP, Unrealized P&L (`backend/ofo/table/columns.py:4`) | H | - | |
| B33 | Greeks per leg | 016 | Built (Advanced level) | `backend/ofo/table/columns.py:15` "**Advanced**: adds Greeks and IV assumptions (IV, Delta, Gamma, Theta, Vega)." | M | - | Hidden at Guided (Q31) |
| B34 | Portfolio Greeks total + rupee tooltips | 016, bundle 7.1 | Partial | TOTAL row sums Greeks: `backend/ofo/table/model.py:31` "The TOTAL row sums the legs' UNROUNDED position Greeks and rounds ONCE at the end"; no rupee-example tooltips found | M | S | Advanced level only |
| B35 | Strategy price history chart | 017 | Excluded-by-ADR-066 | ADR-066 "shows users no historical market data"; REQ-052 AC-1 | L | M | SPEC CHANGE S4 if wanted |
| B36 | What-if: target level slider | 020 | Excluded-by-ADR-120 | ADR-120 "No what-if sliders (spot, implied volatility or days to expiry)" | H - most-used planning control | M | SPEC CHANGE S1 |
| B37 | What-if: target date stepper | 020 | Excluded-by-ADR-120 | same | H | M | SPEC CHANGE S1 |
| B38 | Strikewise IV edit and IV offset | 021 | Excluded-by-ADR-120 | same ("implied volatility") | L for beginners | M | Keep excluded (recommended) |
| B39 | Target-day futures prices | 021 | Missing (internal only) | Per-expiry put-call-parity forward is computed (W-060) but not shown | L | S | |
| B40 | Info panel: ATM IV, IV percentile, PCR, max pain, VIX, events | 026-031 | Missing | `frontend/src/pages/MarketContextPage.vue:2` "No PCR, OI totals, VIX or any figure the API does not send." | M - helps choose a range | M | Data-feasibility test first (ADR-012) |
| B41 | TradingView chart with OI profile | 027 | Missing | grep `tradingview` in `frontend/src`: 0 hits | L | L | Licence + ADR-066 history limit |
| B42 | Leg picker drawer: Straddles / Strangles / Strikes / Futures tabs, quick select 50-200 pts, LTP/OI/Greeks per strike | 032-038 | Partial | `LegPicker.vue:2` "Underlying -> expiry -> CE/PE/FUT -> strike (none for FUT) -> BUY/SELL -> lots -> Add" (one leg at a time, no prices shown in the picker) | H - picking strikes is the main job | M | |
| B43 | Pick legs from the Option Chain with B/S, import into the builder | 065 | Held (#466) | `OptionChainPage.vue:4` "No order placement, selection or import here (REQ-029 AC-6; REQ-030 is a later item)"; PR #466 W-120 | H | M | REQ-030 Approved |
| B44 | Manual P&L (past adjustments) | 112-113 | Missing | grep `manual` in `backend/ofo/outcome`: 0 hits | L | S | OFO2's strategy ledger records real fills instead (ADR-102) |
| B45 | Save / Save As with a name | 115-117 | Built (no name field verified) | `frontend/src/components/strategy/SaveDraftBar.vue:1` "Save Draft and the saved list (W-071 ...)" | H | - | |
| B46 | Saved strategies list with search | 117 | Partial / Held | List inside `SaveDraftBar.vue`; full "My Strategies" page is PR #393 (W-109) | M | S | |
| B47 | Share a strategy by link | 116 | Partial | A draft opens from a URL (`frontend/src/lib/draftLink.js`, W-073); `StrategyActions.vue:2-3` "Add Row, Delete Selected, Import/Update Positions, Save, Share and Buy Basket Order are not in this slice" | M - word of mouth | S | Social buttons optional |
| B48 | Builder history, undo, restore | (none in Sensibull) | Partial (API only) | `backend/ofo_app/routes/strategies.py:360` `/strategies/{strategy_id}/history`, `:372` `/restore/{seq}`; grep `restore|/history|undo` in `frontend/src`: 0 hits | M - OFO2-only strength | S | REQ-070 Approved |
| B49 | Analyse live positions in the builder | 119 | Missing / blocked | W-083 (existing positions on connect) status `blocked`; Positions W-111 on branch `build/W-111-positions` | H for active traders | L | |
| B50 | Warnings: weekend theta, events, liquidity, expiry-day, no stop-loss | bundle 2.3 | Partial | Expiry-day warning W-086 done; data-health labels on stale legs (`StrategyBuilderPage.vue:257-261`); no theta-bleed / event / liquidity codes found (grep `theta_bleed|liquidity` in `outcome.py`: 0 hits) | H - protects beginners | M | Codes from the engine, text from the catalogue (ADR-003 Q226) |
| B51 | Underlying switch keeps or confirms the legs | 141 | Built (different, safer) | `LegPicker.vue:42-43` "Locked while any leg exists ... a leg's contract belongs to its underlying." `const underlyingLocked = computed(() => props.legs.length > 0)` | M | - | Sensibull silently cleared all legs |
| B52 | Live price refresh | 012 | Built (faster) | Live push at most once a second per strategy (W-065); Sensibull recomputes every 30 s | H | - | |
| B53 | UX levels (Guided / Standard / Advanced) | (none) | Built | `StrategyBuilderPage.vue:43` `uxLevel`; ADR-004 | H - OFO2-only | - | |
| B54 | Plain-language outcome sentences ("At most Rs X at expiry, after charges") | (none) | Built | `SummaryCards` `what_can_i_make` / `what_can_i_lose`; ADR-071; W-066, W-075 | H - OFO2-only | - | |
| B55 | Builder works without a broker login | 200-206 | Partial | Drafts work without Zerodha (ADR-020); without live data the screen shows "No numbers are shown because there is no live market data" (`StrategyBuilderPage.vue:242`) - so no numbers at all | H - first-visit experience | M | Sensibull shows 1-minute-delayed numbers; OFO2 data rights (ADR-053, F-23) limit this |

## 2. Execution from the builder (Sensibull 040-044)

| # | Capability | Sensibull (screen) | OFO2 status | OFO2 evidence | Value | Effort | Notes |
|---|---|---|---|---|---|---|---|
| E1 | Trade the whole strategy as one basket | 040 | Built (different) | Execute screen `frontend/src/pages/ExecuteStrategyPage.vue:1` (W-104); read-only Kite basket the user places on Kite's page (REQ-073, W-080) | H | - | |
| E2 | Per-leg "send this leg now" buttons | 040-041 | Excluded-by-ADR-002 / REQ-073 | The app sends no order; the user places the whole basket on Kite (ADR-054, REQ-073) | - | - | Deliberately different |
| E3 | Buys before sells | 040 (advice text only) | Built | Dependency-aware plan (ADR-017, W-022); two baskets when a sell depends on a buy (ADR-117; PR #478 et al. for the live path) | H | - | |
| E4 | Margin shortfall blocks the basket | 041 (icon only) | Built | `backend/ofo/execution/margin_gate.py:79` `render("margin_basket_insufficient", ...)`; W-081 in_review; ADR-016 | H | - | |
| E5 | Risk tiers before the basket opens | (none) | Partial | ADR-140 decided; implementation unverified (grep `ELEVATED` not run) | H | M | |
| E6 | Market protection / limit pricing | 041 | Built | Depth-based executable limit with slippage, tick rounding (W-078, ADR-080) | H | - | |
| E7 | Freeze-limit slicing | bundle 7.2 | Built (different) | Block above the freeze limit, never split (ADR-092, W-076; PR #420 held) | M | - | |
| E8 | Intraday (MIS) product | 040 | Excluded-by-ADR-080 | ADR-080 "(1) Q264: every entry and adjustment order is NRML (carry forward), with no product choice on screen" | L | - | |
| E9 | Market hours and kill switch on execution | (none) | Held | PR #455 MKT-HOURS (ADR-119), PR #463 KILL-SWITCH (ADR-127) | H (safety) | - | |
| E10 | Order status after placing | 042-044 | Built (part) | Return check "Check with Zerodha" (`frontend/src/components/execution/ReturnCheck.vue`, W-096); four states ADR-135 | H | - | |

## 3. Wizard, Easy Options, Expiry Trades (070-087, 160-165)

| # | Capability | Sensibull (screen) | OFO2 status | OFO2 evidence | Value | Effort | Notes |
|---|---|---|---|---|---|---|---|
| W1 | Guided entry: "where will NIFTY go" -> a few explained setups | 080-087 | Held (#457) | PR #457 W-119 Guided Create (ADR-121/122/124); REQ-024 Specified, REQ-069 Approved | H - beginners' front door | M | Spec F-51 says no studied app had a guided flow; today's logged-in study shows Easy Options and Expiry Trades are guided flows - F-51 needs a correction (finding to register) |
| W2 | Defensive / Balanced / Aggressive variants of one view | 081-083 | Missing | No such grouping in `backend/ofo/strategy/catalogue.yaml` (levels are Beginner/Intermediate/Advanced) | M | M | Risk labels, not profit labels, fit ADR-003 |
| W3 | "How does this trade work?" plain bullets | 084 | Partial | Learn page six template parts (`frontend/src/lib/learnContent.js`); not shown next to a loaded strategy | H | S | |
| W4 | Wizard: target + date -> hundreds of trades ranked by profit | 070-075 | Excluded-by-ADR-003 + ADR-055 | ADR-003 forbids "Best trade"; ADR-055 (3) "no 'best', 'winning' or ranking wording" | - | - | Must stay different |
| W5 | Expiry-day target ladder incl. "YOLO" | 160-165 | Excluded-by-ADR-003 | same | - | - | |
| W6 | Events that can affect the trade | 074 | Missing | grep `event` calendar in `backend/ofo`: no market-event source | M | M | Data source needed |

## 4. Drafts and paper trading (090-092)

| # | Capability | Sensibull (screen) | OFO2 status | OFO2 evidence | Value | Effort | Notes |
|---|---|---|---|---|---|---|---|
| D1 | Save a plan without real money | 090 | Built | Save Draft (W-061, W-071; ADR-062) | H | - | |
| D2 | Track a draft's P&L over days (paper trading) | 090-092 | Partial | Live Strategies follows each saved strategy live (`frontend/src/pages/LiveStrategiesPage.vue:1`, W-113); no booked/unbooked paper P&L, no paper exits | H - practice before money | M | Fits ADR-002 "plan first" |
| D3 | Convert a draft to real trades | 091 | Built | Execute Strategy from a saved strategy (`StrategyActions.vue:4` "Execute Strategy opens the Execute screen, only for a saved strategy") | H | - | |
| D4 | Notes on a strategy | 091 | Missing | grep `notes` in `backend/ofo/strategy/definition.py` not found (unverified beyond that file) | L | S | |
| D5 | Import the real order book into a draft | What's New | Excluded-by-ADR-134 (partly) | ADR-134 "(1) Anything the broker ... already provides - its order book ... is NOT rebuilt in this app" | L | - | |

## 5. Positions, groups, exits, stop-loss, conditional exits (050-053, section 7)

| # | Capability | Sensibull (screen) | OFO2 status | OFO2 evidence | Value | Effort | Notes |
|---|---|---|---|---|---|---|---|
| P1 | Positions list with P&L totals | 050 | Held / Partial | W-111 part 1 "strategy-linked positions and outside lots, no P&L figures" on branch `build/W-111-positions` (PR #410 closed by GitHub) | M | M | ADR-110 open-plan rule applies |
| P2 | Named groups of positions | 051 | Built (by design) | A strategy IS the group (ADR-002); adoption of outside positions W-083 `blocked` | H | - | |
| P3 | Exit a strategy | 051 | Built | Execute screen offers entry or exit (`ExecuteStrategyPage.vue:5` "The owner picks entry or exit") | H | - | |
| P4 | Stop-loss order per position | 051, 7 | Missing | grep `stoploss|stop_loss` in `frontend/src`: 0 hits | H | M | ADR-134: if Kite GTT/SL does it, link or prepare it, do not rebuild |
| P5 | Conditional exit (index crosses a level -> exit all, via Zerodha ATO) | section 7 | Missing | Rule engine domain W-013 done (`backend/ofo/rules/`), no trigger, alert or prepared basket (REQ-041/042 Approved, GC-4 rows moved to GC-6, blocked) | H - the "monitored against my rules" promise | L | OFO2 must stay assisted (ADR-009); ATO is a broker feature (ADR-134) - see plan |
| P6 | Strategy health statuses (four colours) | (none) | Missing | REQ-043 Approved; `LiveStrategyCard.vue` shows only "Monitoring paused" badge (line 117) | H - OFO2's paid differentiator | L | |
| P7 | Booked / unbooked / FIFO P&L | bundle 7.1 | Partial | Fill ledger and realised P&L from broker fills (ADR-102, W-091 in_review); not on a screen | M | M | |
| P8 | View funds drawer | 050 | Partial | Funds in margin line and Execute cost; no drawer | L | S | ADR-134: link Kite funds |
| P9 | Share verified P&L / leaderboards | 050, 10 | Excluded-by-ADR-055 | ADR-055 (3) "no strategy marketplace and no 'best', 'winning' or ranking wording" | - | - | |

## 6. Orders (Orders page)

| # | Capability | Sensibull | OFO2 status | OFO2 evidence | Value | Effort | Notes |
|---|---|---|---|---|---|---|---|
| O1 | Full order book with tabs | Orders | Excluded-by-ADR-134 | ADR-134 (1) | - | - | |
| O2 | One line per strategy order in four states + "Open Kite order book" | - | Missing | ADR-138 decided; no Orders page in `frontend/src/pages` (glob) | M | M | Order-book store PRs #451/#452 held |

## 7. Option Chain (060-067)

| # | Capability | Sensibull (screen) | OFO2 status | OFO2 evidence | Value | Effort | Notes |
|---|---|---|---|---|---|---|---|
| C1 | Live chain Calls / Strike / Puts, expiry picker, ATM row | 060 | Built | `frontend/src/pages/OptionChainPage.vue:1` (W-118 code on main); fields `:12` `[['ltp', 'LTP'], ['change', 'Change'], ['oi', 'OI'], ['volume', 'Volume']]` | H | - | Change shows "-" (F-47) |
| C2 | IV column, Greeks view | 061-062 | Missing | Not in `SIDE_FIELDS` | M | M | Engine has IV/Greeks (W-002) |
| C3 | OI bars, OI change % | 060 | Partial | OI and OI change on the socket (`chain_push.py:97-98`); no bars, no % | M | S | |
| C4 | Per-lot toggle, ITM shading, strikes-around-ATM setting | 060-066 | Missing / unverified | not found in `OptionChainPage.vue` header | L | S | |
| C5 | Bid / offer, intrinsic, time value, breakeven % (all columns) | 063 | Missing | not in `SIDE_FIELDS` | L | S | |
| C6 | Live preview while legs are selected | - | Missing | REQ-031 Approved; nothing on main | M | M | |
| C7 | Download as Excel | 066 | Missing | - | L | S | |

## 8. Analyse pages (140-153)

| # | Capability | Sensibull | OFO2 status | OFO2 evidence | Value | Effort | Notes |
|---|---|---|---|---|---|---|---|
| A1 | OI change / OI vs time / multi-strike OI | 140-144 | Missing | `MarketContextPage.vue:2` | M | L | Market-wide maths once and shared (ADR-012) |
| A2 | FII / DII data | 145 | Missing | - | L | M | External data source |
| A3 | Live straddle / multi straddle charts | 146-147 | Missing / Excluded-by-ADR-066 (history) | ADR-066 | L | L | |
| A4 | Screener, heatmap, technical signals, stock data | 148-151 | Missing | - | L (index-only product) | L | Stocks are out of scope (ADR-001) |
| A5 | IV chart, IV percentile | 152 | Missing | - | M | M | Needs IV history (ADR-066 internal use only) |
| A6 | Events calendar | 153 | Missing | - | M | M | |
| A7 | Market Analysis video + "Verdict" + "Trades?" | 153 | Excluded-by-ADR-003 + ADR-055 | ADR-055 (1); spec F-24 (Research Analyst definition) | - | - | Needs SEBI RA registration |

## 9. Other screens

| # | Capability | Sensibull | OFO2 status | OFO2 evidence | Value | Effort | Notes |
|---|---|---|---|---|---|---|---|
| X1 | Home with action tiles | 000-001 | Built | `frontend/src/pages/HomeOverviewPage.vue:1` (W-115 code on main) | M | - | |
| X2 | Social proof (live P&L carousel) | 001 | Excluded-by-ADR-055 | ADR-055 (1) "no past or expected return of any strategy is shown as a performance claim" | - | - | |
| X3 | Mindful Trading (stats, breather, check-in) | 10 | Missing | grep `mindful|breather` in `frontend/src` + `backend`: 0 hits | H - matches the core promise "Plan your trade. Follow your strategy. Then execute." | S | Cheap, on-brand |
| X4 | Watchlist (instruments and strategies) | 10 | Partial | Live Strategies watches saved strategies (W-113); no instrument watchlist | L | M | |
| X5 | Learn: per-strategy pages | 10 | Built (part) | `frontend/src/pages/LearnPage.vue:1` (21 templates, six parts); no "Open in Builder" (`LearnPage.vue:6` "No money, no order link") | M | S | Open-in-Builder depends on B4 |
| X6 | Video courses | 10 | Missing | - | L | L | |
| X7 | Alerts (in-app, push, email, WhatsApp) | (conditional exits only) | Missing (shell) | `frontend/src/pages/AlertsPage.vue:2` "No alert logic exists yet (GC-4)" | H | L | ADR-028; Notifier gateway exists outside this repo |
| X8 | Dark theme, chart provider choice | 10 | Missing | grep `dark:` (Tailwind dark variant) in `frontend/src`: 0 hits | L | S | |
| X9 | Support chat, FAQ, What's New | 10 | Missing | - | L | S | |

## 10. Accounts, plans, brokers, platform

| # | Capability | Sensibull | OFO2 status | OFO2 evidence | Value | Effort | Notes |
|---|---|---|---|---|---|---|---|
| G1 | Login with broker (Zerodha) | 180 | Built (owner account only) | Kite login callback + encrypted token (W-058); multi-user sign-in is Stage 5 | H | - | |
| G2 | Sign in with Google | 181 | Missing | ADR-021 decided; no sign-in route in `backend/ofo_app/routes/` (14 route files listed) | H for a public SaaS | M | Master plan Stage 5 |
| G3 | Other brokers (Angel, Upstox, ICICI) | 181 | Excluded-by-ADR-001 | ADR-001 "Zerodha as the only broker"; adapters ready (ADR-029) | M | L | |
| G4 | Free trial | 200 | Partial | 7-day trial engine W-007 done, policy W-008 blocked | M | - | ADR-023 |
| G5 | Paid plan and payments | 202 | Excluded-by-ADR-055 (for now) | ADR-055 (2) "the paid plan ... not built further"; billing shell "Free during early access" (ADR-144/146, `BillingShellPage.vue`) | Business | - | See owner decision D1 |
| G6 | Free Pro for Zerodha users | 201 | Partial (paused) | ADR-024 (owner's own clients only); W-011 blocked | Business | - | Sensibull: every Zerodha user |
| G7 | Native mobile app | - | Excluded-by-ADR-001 | ADR-001 "responsive web from day 1 with no native apps"; W-055 phone-width check done | M | - | |
| G8 | Public pages browsable logged out with delayed data | 180 | Partial | Landing page `/welcome` (`routes.js:71`); no data logged out (ADR-027 "All live data is behind login") | M | - | |
| G9 | One compute call returning every number | API | Built | Outcome API (W-063) `POST /api/strategies/outcome` (`backend/ofo_app/routes/outcome.py:466`); ADR-008 | H | - | Extend it with bounds and warning codes |
| G10 | Live prices over a websocket | API | Built | Platform socket (W-065), chain and index sockets (W-114, W-116) | H | - | |
| G11 | Product analytics, error monitoring, session replay | API | Missing | grep `bugsnag|sentry|rudder|clarity|gtag|posthog` in `frontend/src`, `index.html`, `package.json`: 0 hits | M (learning what users do) | M | Privacy rules apply (REQ-063, REQ-074) |
| G12 | Staging / QA environments | API | Partial | ofo_dev and ofo_test databases (ADR-048, ADR-078); no hosted staging yet (master plan Stage 7) | M | L | |

---

## Top 15 gaps (ranked)

Ranked by value to an OFO2 user times how close the gap sits to the Strategy Builder (the owner's next feature), then
by effort. "Gap" means a row that is Missing, Partial or Held and is not excluded by a decision (excluded rows that
deserve a decision are in the plan's SPEC CHANGE list instead).

1. **B42 + B43 - Picking strikes fast** (leg picker with prices, straddle/strangle quick picks; chain -> builder
   import, PR #466). Today a leg is added through five dropdowns with no price on screen. M.
2. **B7 + B8 - Strike steppers and Shift / Width / Hedge.** The single most-used edit in Sensibull; OFO2 has none. M.
3. **B4 - Ready-made shapes that load into the builder.** 21 templates exist as data but only on Learn. M; needs
   owner decision D2 (ADR-055 strike picking).
4. **B26 + B27 - The "now" curve on the payoff chart and a two-line hover.** The engine already computes Estimated
   Now, but the API returns one view per call (`outcome.py:151`), so this needs two calls or a Tier A API extension.
   It overlays the two existing modes; it is not a third ADR-120 mode. M.
5. **B20 + B19 + B29 - POP, reward/risk and the expected move (SD).** Beginners' "how likely / is it worth it"
   numbers; engine work under ADR-008. M; POP wording needs owner decision D4.
6. **B50 - Builder warnings as codes** (weekend/holiday decay, event, liquidity, unhedged short, expiry day). M.
7. **P6 + P5 + X7 - Monitoring against the user's rules: health colours, a stop/target rule, alert, prepared exit
   basket** (REQ-041/042/043/062). OFO2's paid reason to exist; L.
8. **W1 + W2 + W3 - Guided create** (PR #457) with plain "how this trade works" bullets and risk-labelled variants. M.
9. **D2 - Paper tracking of a saved plan** (P&L since saved, paper exit). M.
10. **B11 - Analysis-only leg toggle** ("what if I drop this hedge?") that never changes what Execute sends. S.
11. **B48 - Builder history / undo on screen** (the API exists). S.
12. **X3 - Mindful pre-trade check-in** on Execute. S, on-brand.
13. **B10 + B14 + B15 + B19 - Small summary items** (multiplier, net premium Pay/Get, charges breakdown,
    reward/risk). S each.
14. **B40 + C2 - IV, IV percentile, PCR, max pain, VIX** on the builder info strip and chain Greeks/IV view. M.
15. **B49 + P1 - Analyse existing positions in the builder** (W-083 blocked, W-111 branch). L.

## Where OFO2 must be DIFFERENT, not equal

Sensibull is mature and good at analysis. In five places it is weak or unsafe, and OFO2's own decisions already
require different behaviour. These are not gaps to close; they are the product's reason to exist.

1. **Partial-leg sends ("Trade 3" after unticking a leg).** Sensibull lets a user untick the hedge of an iron condor
   and send the rest, turning a limited-loss trade into an unlimited one (README 1.3). OFO2: ADR-002 "Every trade
   placed through the platform belongs to a strategy; there are no standalone orders at any level." and ADR-017 "the
   engine builds a dependency-aware plan (protective legs before the sells that depend on them)". So an OFO2 leg
   toggle (B11) may change the numbers on screen but never what Execute sends.
2. **Per-leg send buttons inside the basket.** Sensibull's basket has a SELL/BUY button per leg that sends that leg at
   once; one misclick in the study sent a real order. OFO2: REQ-073 "Orders reach Zerodha as a read-only basket the
   user places on Kite's own page", and ADR-117 "(1) When any sell leg depends on a protective buy, entry is TWO
   baskets: basket 1 holds the protective buys; the user places it on Kite and presses "Check with Zerodha"; basket 2
   holds the sells." No per-leg send exists, by design.
3. **No margin-shortfall block.** Sensibull shows "Margin Needed > Available" only as a red icon inside the basket and
   lets the user press Place. OFO2: ADR-016 "Margin is a hard gate: checked with Zerodha before any order and
   re-checked after each fill." and ADR-094 "A BUY leg whose `option_premium` is missing, not a number or negative
   makes the reply unusable and the check blocks (fail closed)." OFO2 also warns in the builder already (B23).
4. **Silent clear on underlying switch.** Sensibull drops every leg without a question when NIFTY becomes SENSEX.
   OFO2 locks the underlying while legs exist (B51) and ADR-019 says "The strategy definition (the user's decisions)
   never changes because the market moves". Keep the lock; if switching is ever allowed, it must ask first.
5. **Profit-ranked wizard wording.** "Find the Most Profitable Options Strategies", "743 trades ... sorted by profit",
   "YOLO". OFO2: ADR-003 forbids "*You should take this trade · This is the best trade · Best adjustment · Recommended
   trade · Guaranteed · Risk-free · Certain profit*" and ADR-055 (3) requires "no strategy marketplace and no "best",
   "winning" or ranking wording". OFO2's guided flow lists "Strategies you could consider" ordered by the user's
   preferences (ADR-032), never by profit.
6. **Editorial verdicts and trade ideas.** Sensibull publishes a daily "Verdict" and "Trades?" under its SEBI Research
   Analyst registration (INH200006895). OFO2 has none; spec F-24 records that "SEBI's Research Analyst definition is
   broad and has no exemption for tools", and ADR-055 (1) keeps suggestions "educational and generic - setups are
   shown as templates the user completes, with no platform-picked strikes, stop-losses, targets or adjustment
   instructions presented as the platform's view".

**The strategic point.** A Zerodha user gets Sensibull Pro for Rs 0 ("Pro Plan is available to you at zero cost";
README 11). OFO2 is Zerodha-only (ADR-001) and its plan was Rs 600 a month (ADR-026, paused by ADR-055 (2)). If OFO2
tries to win on analysis features it is chasing a free, eight-year-old product feature by feature, and it will lose
on breadth (Sensibull has OI tools, screeners, FII/DII, TradingView, multi-broker, mobile). OFO2's paid value can only
come from what Sensibull does not do: the strategy as a complete plan (legs + entry + exit + adjustment rules, ADR-009),
monitoring against the user's own rules with health colours (ADR-010, REQ-043), a dependency-safe execution path that
cannot leave a naked leg (ADR-017, ADR-117), a reconciliation with Zerodha that never guesses (ADR-120 (2)), and
plain-language risk at Guided level (ADR-004, ADR-071). The builder must be good enough that a user does not miss
Sensibull while planning; it does not need to match Sensibull's analyse menu.

---

## Appendix: ADR quotes used in this file (verbatim from `spec/decisions/`)

- ADR-001: "V1 is a public, multi-tenant SaaS web platform for Indian index derivatives, focused on making
  strategy-based option trading (especially option selling) easy: underlyings NIFTY (NSE) and SENSEX (BSE); Zerodha as
  the only broker; six leg types; each user trades only their own Zerodha account; responsive web from day 1 with no
  native apps."
- ADR-002: "The strategy, not the order, is the central object. Every trade placed through the platform belongs to a
  strategy; there are no standalone orders at any level."
- ADR-003 (Rules, Forbidden): "*You should take this trade · This is the best trade · Best adjustment · Recommended
  trade · Guaranteed · Risk-free · Certain profit*, and any promise of returns or of reduced losses (T1 #74)."
- ADR-004: "Primary users are beginner and intermediate options traders; advanced users are supported."
- ADR-008: "One strategy/risk engine produces every number (builder, order preview, live strategy, adjustment
  simulator, exit, payoff graph, scenario table)."
- ADR-009: "V1 is assisted, not autonomous: when a condition is met the platform alerts and prepares the exact orders,
  and the user reviews and executes."
- ADR-010: "Active strategies get rule-based strategy-health monitoring with four statuses."
- ADR-016: "Margin is a hard gate: checked with Zerodha before any order and re-checked after each fill."
- ADR-017: "The user presses one Execute Strategy; the engine builds a dependency-aware plan (protective legs before
  the sells that depend on them), checks margin before every order, confirms fills with Zerodha, and treats partial
  execution as an explicit exception where the user chooses Complete Strategy first."
- ADR-019: "The strategy definition (the user's decisions) never changes because the market moves; live market state
  is separate and drives calculations."
- ADR-026: "Pro costs Rs 600 per month (from the owner's Rs 20/day idea), with a discounted annual plan whose price
  admins set."
- ADR-027: "All live data is behind login; the public site is marketing only."
- ADR-032: "After choosing an expiry and range, the Guided Builder shows valid setups of the preferred types first,
  then other compatible strategies."
- ADR-055: "Until Zerodha compliance and the legal review (Q211) answer in writing, (1) suggestions stay educational
  and generic - setups are shown as templates the user completes, with no platform-picked strikes, stop-losses,
  targets or adjustment instructions presented as the platform's view, and no past or expected return of any strategy
  is shown as a performance claim; (2) the paid plan, free Pro for the owner's account-opening clients and referral
  rewards (ADR-024, ADR-025, ADR-026, ADR-038) are not built further and do not go live; (3) no strategy marketplace
  and no "best", "winning" or ranking wording."
- ADR-066: "In V1 the platform uses them only behind the scenes - to fill gaps when its own tick recording drops, for
  tests and for replays - and shows users no historical market data (REQ-047 AC-1 unchanged)."
- ADR-094: "A BUY leg whose `option_premium` is missing, not a number or negative makes the reply unusable and the
  check blocks (fail closed)."
- ADR-117: "(1) When any sell leg depends on a protective buy, entry is TWO baskets: basket 1 holds the protective
  buys; the user places it on Kite and presses "Check with Zerodha"; basket 2 holds the sells."
- ADR-120: "(1) No what-if sliders (spot, implied volatility or days to expiry) in the Strategy Builder in V1;
  REQ-034 AC-6 stays as written: two modes only, "At Expiry" and "Estimated Now"."
- ADR-134: "(1) Anything the broker (Zerodha today, any broker later) already provides - its order book, order
  statuses and rejection reasons, order cancel and modify, trade history, the position list - is NOT rebuilt in this
  app; where the user needs it, the app links to the broker."
- ADR-080: "(1) Q264: every entry and adjustment order is NRML (carry forward), with no product choice on screen".
