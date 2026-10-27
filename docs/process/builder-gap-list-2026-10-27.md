# Builder, strike drawer and option chain: gap list against Sensibull (2026-10-27)

Goal: `docs/process/builder-goal-2026-10-27.md` (Q1 "gap list + live walk"). Scope narrowed by the owner at 10:25 IST:
this phase is the Strategy Builder, its strike drawer and the Option Chain only; the separate screens are listed in
section 4 without comparison. This file is the plan the owner
approves (Q4). Not committed; the orchestrator reviews it.

How it was made (2026-10-27, 09:44-09:52 IST, market open):
- Running app on main 2e1134d5 (screen 127.0.0.1:5173, API 127.0.0.1:8765, owner's live Kite session), driven with
  Playwright at 1536 x 864 and once at 390 x 844. Read only: no broker, order or login endpoint was called. One test
  strategy (NIFTY 3 Nov short iron condor 22300 PE / 22650 PE / 22850 CE / 23200 CE, 1 lot, not saved) was built
  through the strike drawer.
- Screenshots: `.playwright-mcp/gap-*.png` in the main checkout (git-ignored). Named in the "OFO2 today" column.
- Sensibull side: the private study `competitors/sensibull/2026-10-21/` (screenshots opened for S-010, S-032, S-060,
  S-107; all other Sensibull facts are from `catalogue-raw.md`, cited by screen number). No image is copied here.
- Known items (walkthrough "RESUMED 2026-10-27", issues #582 and #583, REQ-078 speed) are placed in their rows, not
  re-reported as new.

Verdicts: **matches** / **differs** / **missing** / **n-a** (not for us: stocks, orders, advice wording) /
**unmeasured** (not seen today, reason given). Every verdict rests on a seen fact.

Owner row = row of `docs/process/builder-sequence-2026-10-22.md`, an issue, or "new".

---

## 1. Builder (`/strategies/strategy-builder`)

| Gap id | Sensibull screen(s) | Region / feature | Sensibull does | OFO2 today | Verdict | Spec | Owner row |
|---|---|---|---|---|---|---|---|
| G-001 | S-012, S-107 | A. Underlying field | Search box "NIFTY 22971.70 +0.36%" with chart icon and Info button | Native select "NIFTY" and spot "22743.1" (trailing zero dropped), no day change, no chart icon, no Info (gap-builder-condor.png) | differs | REQ-139 (change, OHLC) | row 41 |
| G-002 | S-130..S-133, S-230, S-232 | A. Underlyings offered | NIFTY, BANKNIFTY, FINNIFTY, SENSEX (+ stocks) | Select lists NIFTY and SENSEX only (page text at 390 px, 09:50) | missing | REQ-090 (stocks out: ADR-157) | row 46 |
| G-003 | S-026, S-031 | A. Info panel | Popover: OHLC, expiry, monthly future; F&O data (ATM, PCR, lot, ATM IV, max pain, IVP, VIX); Fut. prices tab | No Info button anywhere on the builder (gap-builder-condor.png) | missing | REQ-106, REQ-107 (IVP, held), REQ-080 AC-6 (futures) | rows 42, 60 |
| G-004 | S-027 | A. Underlying chart | Chart icon opens a candle chart with OI profile | No chart icon (gap-builder-condor.png) | missing | REQ-107 AC-4 (held) | row 60 |
| G-005 | S-025, S-244 | A. Settings | Lots / Qty and "Show Manual P&L"; saved per account | Settings popover holds only "Show legs as Lots / Quantity" (page text after click, 09:48) | differs | REQ-138 | row 40 |
| G-006 | S-010 | Empty builder | "No Trades Added" + one button "Build a new custom strategy"; right column shows Summary / Charts and Graphs / Greeks and IVs placeholders | "No legs yet" + two buttons "Add leg" and "Pick from Option Chain", plus Add/Edit and a disabled Save; right column is one sentence "No draft strategy is open" (gap-builder-empty.png) | differs | ADR-193, UI study UI-110 | new |
| G-007 | S-010 | Spot on an empty builder | Spot and change shown before any leg | "NIFTY —": no spot until the drawer subscribes the index (gap-builder-empty.png) | differs | REQ-080 AC-6, REQ-072 | #583 (I-6) |
| G-008 | S-011 | Ready-made: one click loads legs | One click loads real legs at ATM | Click on "Short Iron Condor" on the empty builder: `POST /api/strategies/load-template` answered 503, nothing loaded (console 09:45) | differs | REQ-079 (held Q211; built per goal) | #583 (I-1), row 55 |
| G-009 | S-010, S-105 | Ready-made cards | 4 cards per row, each with a mini payoff icon | 4 cards per row, text only, no icon (gap-builder-empty.png) | differs | UI study UI-111 | row 55 |
| G-010 | S-105, catalogue 100-134 | Ready-made groups | Neutral = 8 shapes (Short Straddle, Iron Butterfly, Short Strangle, Short Iron Condor, Batman, Double Plateau, Jade Lizard, Reverse Jade Lizard) | Neutral = 18 shapes, including Bull Butterfly, Sell Call, Covered Call, Cash-Secured Put, Long Calendar with Calls/Puts, Diagonal Spread, Call/Put Ratio Spread (snapshot 09:44:48) | differs | REQ-028, REQ-079 | row 55 |
| G-011 | S-010 | Ready-made expiry picker | "Expiry 27 Oct" | "Expiry Today (0 days)" on 27 Oct (gap-builder-empty.png) | matches | REQ-079 | - |
| G-012 | S-037, S-038 | Quick picks | Straddles / Strangles are drawer tabs; Strangles has Quick Select 50/100/150/200 | "Quick picks" Buy/Sell radio + Straddle + Strangle 50/100/150/200 buttons under the ready-made grid; not in the drawer (gap-builder-empty.png, gap-drawer-strikes.png) | differs | REQ-079, UI study UI-201 | row 55 |
| G-013 | S-107 | B. Card header | "New Strategy", "Clear New Trades" | "New Strategy", "Clear all" (gap-builder-condor.png) | matches | REQ-135 AC-1 | - |
| G-014 | S-107 | B. Selection row | "4 selected - Short Iron Condor", Reset Prices | "4 selected - Short Iron Condor", Reset Prices (gap-builder-condor.png) | matches | REQ-076, REQ-077 | - |
| G-015 | S-107 | B. Leg row | One 36 px row: tick, B/S, expiry box, - strike +, CE/PE, lots box, price, depth, bin | Tick, B/S chip, expiry as text "3 Nov (7 days)", strike "22300.00" (two decimals), "H" mark, PE chip, "1 lot" + chevron, price box, depth, extra pencil, bin; every leg has a second line "Price has moved since ..." so rows are about 53 px (gap-builder-condor.png) | differs | REQ-076, REQ-077 AC-6 (second line kept by UI study Revision 1); decimals: none | rows 20, 21; new (strike decimals) |
| G-016 | S-102 | B. Per-leg expiry dropdown | List of all expiries with days | Not opened today | unmeasured | REQ-076 | - |
| G-017 | S-111 | B. Untick a leg | "3 selected", numbers recompute, button becomes "Trade 3" | Not exercised today (Revision 1 / I-10 decides the label) | unmeasured | REQ-076 AC-6, ADR-152 | - |
| G-018 | S-107..S-110 | B. Shift / Width / Hedge | Shows "Shift -", "Width 400", "Hedge 200" | "Shift - - +", "Width - +", "Hedge - +": no Width or Hedge value between the buttons on a short iron condor (gap-builder-condor.png; snapshot 09:46:35 lists only the buttons) | differs | REQ-078 | row 30 |
| G-019 | catalogue 012 ("recompute live") | B. Edit speed | Numbers recompute on each edit | Leg edits 1,804-2,482 ms, about 2.0 s typical (walkthrough 2026-10-27, REQ-078 AC-1 FAIL) | differs | REQ-078 AC-1 (p95 1,000 ms) | row 30, #560 |
| G-020 | S-103, S-231 | B. Multiplier | Dropdown 1..N | "Multiplier [1 v]" (gap-builder-condor.png) | matches | REQ-076 | - |
| G-021 | S-107 | B. Money row | "Price Get 92.7  Premium Get 6,026  Charges" | "Net premium: Get ₹14,023.75 (215.75 per unit)  Charges" (gap-builder-condor.png) | differs | REQ-081 AC-1 | row 26 |
| G-022 | S-022 | B. Charges | Modal: total, breakdown, disclaimer | Modal: Total Rs 263.88, Brokerage 160.00, STT 47.50, Exchange 22.50, GST 32.86, Stamp 0.95, SEBI 0.06, STT-on-exercise note (gap-builder-charges.png) | matches | REQ-081 | - |
| G-023 | S-107 | B. Action row | Add/Edit, Add to Drafts, Trade All, "..." | Add/Edit, Save, "..." (gap-builder-condor.png) | differs | ADR-165 (no Trade All); Add to Drafts: next phase (section 4) | - |
| G-024 | S-023, S-115 | B. "..." menu | Save, Save As, Share > (Facebook, Twitter, WhatsApp, Telegram, Copy Link) | "More actions" on the unsaved 4-leg strategy opens an empty menu (snapshot 09:48:46: `menu` with no items) | differs | REQ-134 (Save As, rename), REQ-086 (share link) | rows 29, 44 |
| G-025 | S-010, S-112..S-114, S-242 | B. Manual P/L row | Checkbox "Manual P/L" + "Add Manual P/L" dialog | No manual P&L row (gap-builder-empty.png) | missing | REQ-089 | row 39 (outside this goal per goal doc) |
| G-026 | S-024 | B. Depth popover | OHLC + 5 bid/offer levels | "Market depth: NIFTY 3 Nov 22300 PE": Open/High/Low/Prev close, 5 levels Bids/Qty/Offers/Qty, last trade and read time (gap-builder-depth.png) | matches | REQ-080 AC-7 | - |
| G-027 | S-209, catalogue 010-039 | B. Price refresh | "Prices last updated at" + Refresh button, auto every 30 s | Prices stream live (planned 70.10, "now" moved 69.9 -> 68.15 -> 72.2 within minutes); no refresh button seen (gap-builder-condor-full.png) | differs | REQ-135 (stamp), REQ-113 | - |
| G-028 | S-117, S-218, S-219 | C. Saved tab | Search; rows "name / NIFTY26OCT22500PE and 3 more"; hover pencil and bin | Search box; rows "E2E 28f delete, NIFTY, updated 25 Oct 2026 ..." + Open + Delete buttons; no legs line, no rename (snapshot 09:49:13) | differs | REQ-134 | row 29, #583 (I-2 test rows) |
| G-029 | S-119 | C. Positions tab | "No positions found" (would list broker positions) | Tab present; content not read today | unmeasured | REQ-044, REQ-061, REQ-104 | - |
| G-030 | S-118 | C. Draft Portfolios tab | Create New Portfolio + list | "Tracked" tab: "No tracked strategies here" (snapshot 09:49:29); the Draft Portfolios screens are next phase (section 4) | differs | REQ-109 | row 53 |
| G-031 | S-107, S-111 | E. Max Profit / Max Loss | Pills "+6,026(9%)", "-6,975(-11%)": whole rupees, signed | Pills "13,759.87 (3364% of funds)", "8,990.13 (2198% of funds)": paise, no sign (gap-builder-condor.png) | differs | REQ-081 AC-10 (percent basis is on purpose, see section 2); number format: none | row 26 |
| G-032 | S-107 | E. Figure sentences | None | "At most ₹13,759.87 at expiry, including about ₹263.88 of charges and taxes." under each figure (gap-builder-condor.png) | differs | REQ-034 AC-7 (on purpose, section 2) | - |
| G-033 | S-021, S-129 | E. Breakeven | Target / Expiry toggle; "22811 (-0.7%), 22971 (-0.0%)" | Toggle present, Target greyed; "22,434.25, 23,065.75", no percent (gap-builder-condor.png) | differs | REQ-084 (target); percent from spot: none - needs a requirement | row 37; new |
| G-034 | S-012, S-126 | E. Reward/Risk | "Reward / Risk 0.86" with 1/x flip | "Reward/Risk 1.53" with 1/x (gap-builder-condor.png) | matches | REQ-081 | - |
| G-035 | S-124 | E. POP | "POP 50%" | No POP row (gap-builder-condor.png) | missing | REQ-082 (held, legal check) | row 56 |
| G-036 | S-240 | E. Time value | "-6,026" | "-14118.00": no separator, paise (gap-builder-condor.png) | differs | REQ-081 | #582 item 3 |
| G-037 | S-127 | E. Intrinsic value | "0" | "0.00" + caption "value of the options, not P&L" (gap-builder-condor.png) | matches | REQ-081 | - |
| G-038 | S-128 | E. Funds Needed | "Funds Needed 77,615" | No Funds needed row (gap-builder-condor.png) | missing | REQ-081 (funds needed) | row 26, #537 |
| G-039 | S-241 | E. Margin Needed / Available | "66,169" / "61,325" | "68,109.10" / "409.00" with "Checked at 27 Oct 2026, 09:46:22 IST" (gap-builder-condor.png) | matches | REQ-055 | - |
| G-040 | S-028, S-243 | E. Funds & Margins gear | Gear: include existing positions in funds / margin | No gear (gap-builder-condor.png) | missing | REQ-138, REQ-081 AC-5/AC-6 | row 40, #537 |
| G-041 | S-039 | E. Margin shortfall | Nothing in the builder | Red bar, "Not enough funds for this strategy", two-line red paragraph (gap-builder-condor.png) | differs | REQ-055, ADR-152 (on purpose, section 2) | - |
| G-042 | S-124..S-129 | E. "?" on each figure | Circled "?" with tooltip on each label | Info icon on Max Profit, Max Loss, Breakeven, Reward/Risk, Time value, Intrinsic value, Margin needed, Margin available (gap-builder-condor.png) | matches | REQ-136 | row 32, #561 |
| G-043 | S-107 | E. Summary card height | About 172 px; chart starts about 270 px from the top | Summary card about 410 px tall (y 163-571) with the margin paragraph; chart tabs start at y 697 (gap-builder-condor-full.png) | differs | ADR-193, UI study UI-116 | new |
| G-044 | S-120 | D/E. Important info | Collapsible note "The profit and loss are projections ..." | "Important info" card under the summary, always open, planning sentence + projections note (gap-builder-condor.png) | matches | REQ-136 AC-3 | - |
| G-045 | S-012 | F. Chart tabs | Payoff Graph / P&L Table / Greeks / Strategy Chart | Payoff / P&L Table / Greeks / Strategy chart (gap-builder-pnl-table.png) | matches | ADR-194 | - |
| G-046 | S-012 | F. Add Booked P&L | Toggle top right of the chart card | None (gap-builder-condor-full.png) | missing | REQ-140 (tracked strategies) | row 54 |
| G-047 | S-012 | F. Expiry and target-date curves | Both curves on one chart | One curve at a time: At Expiry or Estimated Now; on Estimated Now the x-axis still reads "Index level at expiry" (gap-builder-estimated-now.png) | differs | REQ-083 | row 36 |
| G-048 | S-012, S-018, S-246 | F. SD bands | -2SD..2SD on the top axis; SD Fixed / Dynamic menu | None (gap-builder-condor-full.png) | missing | REQ-083, REQ-138 | rows 36, 40 |
| G-049 | S-012, S-019, S-214 | F. OI bars | Call/put OI bars behind the curve, "OI data at 22950" strip, Open Interest menu (OI or OI change, which expiries) | None (gap-builder-condor-full.png) | missing | REQ-083 | row 36 |
| G-050 | S-012 | F. Current price marker | "Current price: 22971.30" | Dashed line with label "22743.1" and legend "Spot 22748.55" (gap-builder-condor-full.png) | matches | REQ-034 | - |
| G-051 | S-122 | F. Hover tooltip | "When price is at 23,480 +2.2% / Expected P&L ... / Expiry date ..." | Hovering the chart centre added no tooltip text to the chart figure (evaluate 09:49:40) | missing | REQ-083 | row 36 |
| G-052 | S-012, S-123 | F. Projected P&L badge | "Projected profit: 7,714 (+22%)" with model tooltip | None (gap-builder-condor-full.png) | missing | REQ-083, REQ-084 | rows 36, 37 |
| G-053 | S-012 | F. Zoom | Zoom Out / Zoom In buttons | From / To boxes, "Apply range", "Default range"; a second "21700 ... 23700" line under the axis (gap-builder-condor-full.png) | differs | REQ-034 | row 22; new |
| G-054 | S-020, S-021 | F. What-if sliders | NIFTY Target slider + box; Date slider "4D to expiry" with < >; each with Reset | None (gap-builder-condor-full.png) | missing | REQ-084 | row 37 |
| G-055 | S-017, S-212, S-213 | F. Payoff Table | Target interval 10/25/50/100; target-date and expiry columns; Show %; current row highlighted | Table sub-tab: "NIFTY at expiry / You make/lose" every 100 points, plus "0-P&L" and "CURRENT 22,733" rows; one column (evaluate 09:47:38) | differs | REQ-137 | row 38 |
| G-056 | S-014 | F. P&L Table | Per leg Target P&L, Target Price, Entry, LTP; Total "Projected"; multiply toggles | Instrument / Entry / LTP / P&L / P&L % + Total and a "Full table" switch; contract shown as "65 2026-11-03 22,300 PE" (ISO date) (gap-builder-pnl-table.png) | differs | ADR-194 (compact shape), REQ-084 (target columns); ISO date: none | rows 18, 37; new |
| G-057 | S-015, S-215 | F. Greeks tab | Delta, Theta, Decay, Gamma, Vega + Total; Multiply by lot size / by lots | Delta, Gamma, Theta, Vega, IV + Total; no Decay, no toggles; IV printed as "0.183667"; four decimals (gap-builder-greeks.png) | differs | REQ-084 | row 37 |
| G-058 | S-016, S-216, S-217 | F. Strategy chart | Strategy price vs future over ~2 weeks, Invert Price | "The strategy chart is coming soon." (evaluate 09:47:32) | missing | REQ-091 (held) | row 61 |
| G-059 | S-012 | F. Controls per tab | Target/date controls sit under the chart for every tab | At Expiry / Estimated Now / From / To / Apply range also show on the P&L Table and Greeks tabs (gap-builder-greeks.png) | differs | REQ-034 | new |
| G-060 | S-013, S-121 | G. Strikewise IVs | Per-leg IV with - / +, Offset for all, change, Reset IVs | None (gap-builder-condor-full.png) | missing | REQ-084 | row 37 |
| G-061 | S-013 | G. Portfolio Greeks panel | Portfolio Delta..Vega with multiply toggles | Only the Total row of the Greeks tab (gap-builder-greeks.png) | differs | REQ-084 | row 37 |
| G-062 | S-013 | G. Target day futures prices | Future price per expiry on the target day | None | missing | REQ-084 | row 37 |
| G-063 | S-013 | G. Standard deviation table | 1SD 448.8 pts 2% -> range; 2SD 897.5 3.9% | None | missing | REQ-137 | row 38 |
| G-064 | S-234 | Warnings / Insights drawer | "Insights" link opens "Your warnings" chips | No warnings link on the hedged iron condor; an unhedged case was not built today | unmeasured | REQ-085 | row 31, #558 (parked) |
| G-065 | S-104 | Calendar / mixed expiry | Label "2 selected", Width/Hedge disabled, expiry line curved | Not built today | unmeasured | REQ-076, REQ-078 | - |
| G-066 | S-233 | Futures leg | Buy Future loads with margin, Max Profit/Loss Unlimited | Known: a future added from the Futures tab gets no planned entry and every number disappears (walkthrough 2026-10-27 I-12 FAIL) | differs | REQ-080 AC-9 | #583 (I-12) |
| G-067 | catalogue 010-039 | Layout: editor stays in view | Left column scrolls on its own while the chart scrolls | Left column stayed in view while the right column scrolled to the P&L table (gap-builder-pnl-table.png) | matches | UI study b.1 | - |
| G-068 | none | Unsaved strategy after a reload | Not studied | After a reload the 4-leg unsaved strategy was gone: "No draft strategy is open" (evaluate 09:50:46) | unmeasured (Sensibull side not studied) | none - needs a requirement | new |
| G-069 | catalogue pass 3 ("phone width not done") | Phone width 390 px | Not studied | No sideways scroll (scrollWidth 390); the top bar shows only Home and Strategies, Positions..Learn are cut off (gap-builder-390.png) | unmeasured (Sensibull side not studied) | REQ-009 | new |

## 2. Strike drawer (Add/Edit)

| Gap id | Sensibull screen(s) | Region / feature | Sensibull does | OFO2 today | Verdict | Spec | Owner row |
|---|---|---|---|---|---|---|---|
| G-070 | S-032 | Opening state | Opens on the nearest expiry with strikes already listed | Opens with "Expiry" unselected: "Choose an expiry to see its strikes." (gap-drawer-strikes.png) | differs | REQ-080 | new |
| G-071 | S-032 | Header | Underlying search "NIFTY 22970.35 +0.36%", chart, Info, close | Native selects NIFTY and expiry (label cut: "3 Nov (7 days"), Settings, close; spot as a text line "Index 22752.90, read 27 Oct 2026, 09:45:44 IST" (gap-drawer-strikes-3nov.png) | differs | REQ-080, REQ-139 | row 41; new |
| G-072 | S-032, S-037, S-038 | Tabs | Straddles / Strangles / Strikes / Futures | Strikes / Futures only (gap-drawer-strikes.png) | missing | REQ-079 | row 55 |
| G-073 | S-036 | Tab switch confirm | "You are changing strategy type from Strikes to Straddles" Cancel / Proceed | No quick-pick tabs, so nothing to confirm | missing | REQ-079, UI study UI-201 | row 55 |
| G-074 | S-032 | Strike table columns | Delta / Call LTP / Call OI bar / Strike / IV / Put OI bar / Put LTP / Delta | Call Delta / Call LTP / Call OI / Call IV / Strike / Put IV / Put OI / Put LTP / Put Delta; OI as raw numbers ("1764750"), no bars; two IV columns; strikes "22300.00" (gap-drawer-strikes-3nov.png) | differs | REQ-080 AC-2, UI study UI-202 | row 19; new |
| G-075 | S-032 | Table fits the drawer | Every value in its own column | Values run together ("0.8211613.50" = delta + LTP; "1068275" over the next cell) and Put LTP is cut ("225.0") in the 520 px drawer (gap-drawer-strikes-3nov.png) | differs | REQ-080 | new (walkthrough 2026-10-27 display list) |
| G-076 | S-032 | ITM / ATM marks | ITM halves shaded, ATM strike highlighted | ITM halves shaded cream, ATM row highlighted with an "ATM" tag (gap-drawer-strikes-3nov.png) | matches | REQ-080 | - |
| G-077 | S-032, S-033 | LTP / OI / Greeks views | Three column sets | "LTP / OI / Greeks" switch present; OI and Greeks views not opened today (gap-drawer-strikes.png) | matches (views' content unmeasured) | REQ-080, REQ-084 (theta, vega, gamma) | row 19, row 37 |
| G-078 | S-032 | Pick B / S per strike | B / S on row hover, Qty row under a picked side | B / S on hover; after a pick a "Lots [1 v]" row appears under that strike (gap-drawer-4picks.png) | matches | REQ-080 AC-3/AC-4 | - |
| G-079 | S-032 | Footer | "2 legs selected", Clear All, Done | "4 selected", "Pick from Option Chain", Clear All, Done; the footer covers the last table row (23200 shows under it) (gap-drawer-strikes-3nov.png, gap-drawer-4picks.png) | differs | REQ-080 | new |
| G-080 | S-032 | Extra blocks in the drawer | Only the strike table | A picked-legs list with "Remove" links and the old "Add a leg by contract" form (Type, Strike, Buy or sell, Lots, Add) inside the drawer (gap-drawer-4picks.png) | differs | UI study UI-110, UI-206 | new |
| G-081 | S-032 | "Show Editor" edge tab | Tab on the drawer edge collapses it to see the builder | None seen (gap-drawer-strikes.png) | missing | UI study UI-200 | new |
| G-082 | S-034 | Futures tab | Real and synthetic futures per expiry with B / S | Futures tab present; the future it adds gets no planned entry (walkthrough I-12) | differs | REQ-080 AC-6, AC-9 | #583 (I-12) |
| G-083 | S-035 | Drawer settings | Lots / Qty, Multiply by lot size | "Settings" button present; not opened today | unmeasured | REQ-080, REQ-138 | - |
| G-084 | none (Sensibull shows no such mark) | Contract Zerodha will not accept | - | The strikes reply has no Zerodha permission field, so B / S cannot be disabled in the drawer | differs | REQ-030 AC-16 | #582 item 5 |

## 3. Option Chain (`/market/option-chain`)

| Gap id | Sensibull screen(s) | Region / feature | Sensibull does | OFO2 today | Verdict | Spec | Owner row |
|---|---|---|---|---|---|---|---|
| G-085 | S-060 | Header strip | One strip: search "NIFTY 22966.25 +0.34%", chart, Info / Expiry 27 Oct / Fut Price / INDIAVIX + change / IVP / Per Lot | Page title "Option Chain"; "Underlying [NIFTY]", "Expiry [2026-10-27]", "0 days left", "NIFTY 22743.50 as of 9:50:19 AM", "live", Refresh (gap-chain-live.png) | differs | REQ-029 AC-8, REQ-106 (VIX), REQ-107 (IVP, held), REQ-087 (per lot) | rows 33, 42, 45, 60 |
| G-086 | S-066 | Expiry dropdown | "27 Oct (6 Days)" ... "30 Mar (160 Days)" | ISO dates "2026-10-27" ... "2031-06-24" (18 entries), no days (page text 09:50) | differs | REQ-029 | row 33 |
| G-087 | S-060 | Underlyings | NIFTY, BANKNIFTY, FINNIFTY, SENSEX | NIFTY, SENSEX (page text 09:50) | missing | REQ-090 | row 46 |
| G-088 | S-060 | First data on open | Table on open | "Waiting for live data." at 7 s (gap-chain.png); table at about 20 s (gap-chain-live.png). Sensibull open time not timed | unmeasured (Sensibull not timed) | REQ-029 AC-4, REQ-133 | row 33 |
| G-089 | S-060 | LTP view columns | OI Chg% / OI-lakh / OI bar / LTP / Strike / IV / LTP / OI bar / OI-lakh / OI Chg% | LTP / Change / OI / Volume / Strike / LTP / Change / OI / Volume; OI raw ("15411630"), no bars, no lakh (gap-chain-live.png) | differs | REQ-029 AC-2 (default Strike, LTP, Change, OI, Volume) | row 33 |
| G-090 | S-060 | IV column | IV beside the strike | No IV column (table text has no "IV", 09:50) | missing | REQ-029 AC-2 ("IV is shown to every user") | row 33 |
| G-091 | S-060 | Change column | OI Chg% filled | Every "Change" cell is "-" (gap-chain-live.png) | differs | REQ-029 AC-2 | row 33 |
| G-092 | S-060 | ITM / ATM | ITM shaded yellow, ATM bold | ATM row highlighted; no ITM shading (gap-chain-live.png) | differs | REQ-087 | row 45 |
| G-093 | S-061, S-062 | Greeks view, All columns view | Footer buttons LTP / Greeks / All Column View, each with a column menu | No view switch (gap-chain-live.png) | missing | REQ-029 AC-3 (Details view), REQ-087 | rows 33, 45 |
| G-094 | S-063 | Settings | Lots / Qty, strikes around ATM 10-40, "Show 100 multiples only", font size | No settings on the page (page text has no "Settings", 09:50) | missing | REQ-087 | row 45 |
| G-095 | S-067 | Per Lot toggle | Premium x lot size | None | missing | REQ-087 | row 45 |
| G-096 | S-064, S-065 | Row actions | On hover: B / S / lightning / chart / more | A checkbox + "Buy" + "Sell" always shown on both sides of every row (gap-chain-live.png) | differs | REQ-030 AC-1, AC-2, AC-4 (checkboxes required); lightning is n-a (ADR-002) | row 34 |
| G-097 | catalogue 060-067 (not clicked) | Selected legs | Not studied (B / S not clicked by owner rule) | "Selected Legs" panel: "NIFTY 2026-10-27 22800.00 CE", Buy / Sell, - 1 +, Remove, "Add Selected (1)" (page text 09:50:29) | unmeasured (Sensibull side not clicked) | REQ-030 | row 34 |
| G-098 | none (Sensibull has none) | Live strategy preview | - | After one pick only the Selected Legs panel shows; no net premium, max profit/loss, breakevens or mini payoff (page text 09:50:29) | missing (our requirement) | REQ-031 | row 35 |
| G-099 | S-060 | "Open with OI / IV / Live Charts" | Footer buttons to the OI, IV and chart pages | None | missing | REQ-107 (held) for IV/OI history; buttons: none - needs a requirement | row 60; new |
| G-100 | S-063 | Download as Excel | In settings | None | n-a | REQ-131 (Draft, held) | - |

## 4. Next phase (owner-deferred, 2026-10-27 10:25 IST)

Not compared in this phase. Screens only: Strategy discovery 070-075 (Strategy Wizard) and 080-087 (Easy Options);
Draft Portfolios 084-092, 118, 220-224; OI pages 140-144, 214; IV chart 151; options and straddle charts 146-147.

---

## Counts (per row, by the verdict cell)

| Screen | Rows | matches | differs | missing | n-a | unmeasured |
|---|---|---|---|---|---|---|
| Builder (G-001..G-069) | 69 | 14 | 31 | 17 | 0 | 7 |
| Strike drawer (G-070..G-084) | 15 | 3 | 8 | 3 | 0 | 1 |
| Option Chain (G-085..G-100) | 16 | 0 | 6 | 7 | 1 | 2 |
| **Total** | **100** | **17** | **45** | **27** | **1** | **10** |

Counted by a script over the verdict cell of each G-row (first word). G-077 counts as matches (its OI and Greeks views
were not opened); G-098 counts as missing against our own REQ-031. The ten "unmeasured" rows (G-016, G-017, G-029,
G-064, G-065, G-068, G-069, G-083, G-088, G-097) say why in the row.

## Ten biggest gaps by user impact

1. **G-008 / G-007**: on an empty builder a ready-made click answers 503 and the spot shows "—". The cause is the
   one in #583 (the index is read without its own subscription). A new user's first click does nothing.
2. **G-047..G-052, G-054**: the payoff chart shows one curve at a time. It has no SD bands, no OI bars, no hover values,
   no projected badge and no target or date sliders. These are the core of Sensibull's builder.
3. **G-089..G-091**: the option chain has no IV column (REQ-029 AC-2 asks for it), every "Change" cell is "-", and OI
   is a raw 8-digit number with no bar.
4. **G-074 / G-075 / G-070**: in the strike drawer, values run together and Put LTP is cut off at 520 px. It opens with
   no expiry chosen.
5. **G-002 / G-087**: BANKNIFTY and FINNIFTY are offered neither in the builder nor in the chain.
6. **G-043 / G-031**: the summary card is about 410 px tall, so the chart starts below the first screen. Figures show
   paise and "3364% of funds".
7. **G-055 / G-057 / G-060..G-063**: the payoff table has one column; the Greeks tab has no Decay and prints IV as
   "0.183667"; there are no strike-wise IVs, target-day futures or SD table.
8. **G-093..G-095, G-092**: the chain has no Greeks or All-columns view, no settings, no per-lot toggle and no ITM
   shading.
9. **G-024 / G-018**: the "..." menu opens empty (no Save As, no Share), and Width / Hedge show no value.
10. **G-019**: a leg edit takes about 2 s against REQ-078's 1 s.

---

## Differs on purpose (do not "fix")

- **ADR-165, no order placing**: no Trade All, no "Trade N" for unticked legs, no Buy button for a lone future, no
  basket (S-040..S-044) (G-023).
- **ADR-002, every order belongs to a strategy**: no lightning quick-trade on the chain row (G-096).
- **ADR-003, decision support wording**: no "Please place a stop loss" style text in warnings (S-234); facts only.
- **ADR-152 safety exceptions**: a margin shortfall shows in the builder and blocks (G-041; Sensibull shows nothing,
  S-039). Changing the underlying with legs asks first (Sensibull clears them silently, catalogue 100-134). An unticked
  leg is "left out of the numbers" only (S-111).
- **ADR-157, no stocks**: no stock underlyings or stock presets (S-240..S-249), and no Delivery or Shortfall Penalty
  insights (S-248, S-249).
- **REQ-081 AC-10 / ADR-164**: the max profit / loss percent is of the user's available funds read from Zerodha, not
  of funds needed (Sensibull). With Rs 409 available this reads "3364% of funds" (G-031). The basis stays; only the
  number format is open.
- **REQ-034 AC-7 and UI study Revision 1**: the plain sentences under Max Profit / Max Loss / Breakeven stay visible
  (G-032). So does the second line on a leg, "Price has moved since ..." (G-015).
- **REQ-049**: the "Price data: estimated from spot" strip above the summary is a data-health label that Sensibull
  does not have.
- **ADR-194**: the P&L Table opens compact, with a "Full table" switch (G-056).
- **REQ-030 AC-1/AC-4**: the chain has checkboxes on both sides and a Selected Legs panel that stays visible (G-096,
  G-097).

## Needs a requirement (builder, drawer and chain features with no REQ yet)

| Feature | Sensibull screens | Nearest spec |
|---|---|---|
| Breakeven percent from spot beside each breakeven | S-021, S-107 | none (UI-116 waits on a server field) |
| Number format rules for the builder and drawer (whole rupees vs paise, a minus sign on losses, strikes without ".00") | S-107, S-032 | none |
| An unsaved strategy survives a page reload | none studied | none |
| Chain footer "Open with OI / IV / Live Charts" (the target pages are next phase) | S-060 | REQ-107 (held) covers part of the target pages |
