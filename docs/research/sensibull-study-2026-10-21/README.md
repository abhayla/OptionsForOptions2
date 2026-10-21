# Sensibull study (2026-10-21) - curated catalogue

What this is: a public-safe, condensed record of a hands-on study of Sensibull (web.sensibull.com), the market leader
for Indian options-strategy tools, made on 2026-10-21 on a desktop browser (1536 px wide), logged in through Zerodha
and, separately, through Google with no broker. It covers every screen visited, the API calls the screens make, and
facts read from Sensibull's public JavaScript bundle (text read only; nothing in it was run).

What was removed: every personal detail of the study account (client id, name, email, funds and margin available,
names of drafts and strategies made during the study, any user id). One real-order incident happened during the
study: a misclick sent one order, it was rejected, and a process lesson was recorded. No other detail is kept here.

Screenshots: referred to by number (`NNN-<screen>`). The image files are NOT in git; they stay in the study folder on
the owner's PC. Numbers below match those files.

Where numbers appear (prices, lots, margins) they are public market facts from 2026-10-21 (NIFTY ~22,977, lot 65,
strike step 50; SENSEX lot 20, strike step 100), shown only to make an example concrete.

Companion files in this folder:
- `gap-list.md` - every Sensibull capability against what OptionsForOptions2 (OFO2) has actually built, with proof.
- `proposed-plan.md` - DRAFT plan for owner approval built on the gap list.

---

## How to use this when designing an OFO2 feature

1. Grep this file for the feature's name and its synonyms (e.g. `Shift`, `Width`, `Hedge`, `POP`, `breakeven`,
   `basket`, `draft`, `conditional exit`, `OI`). Section headings are the Sensibull screen names.
2. Cite the screen numbers (`NNN`) in your brief or design note; the owner can open the matching screenshot.
3. Read the "Lesson for OFO2" lines: they mark where Sensibull is weak or unsafe and where OFO2's decisions (ADRs)
   require a different behaviour. Do not copy those behaviours.
4. Before building, check `gap-list.md` for the row: it says whether OFO2 already has it, partly has it, or excludes
   it by a decision, with the file or work item that proves it.
5. The spec (`spec/decisions`, `spec/requirements`) always wins over anything here. This study is evidence, not a
   requirement.

---

## 1. Strategy Builder (screens 010-039 and 100-134) - the owner's prime focus

Route: `/option-strategy-builder?instrument_symbol=NIFTY` (alias `/builder`). Free for users who log in with Zerodha;
Pro (paid) for logins through Google, ICICI, Upstox or Angel One (bundle: per-login plan map).

### 1.1 Layout
- LEFT column: underlying search with live price and change (NIFTY, BANKNIFTY, FINNIFTY, SENSEX, plus any F&O stock
  by search), chart icon, Info, Settings; the leg editor; bottom tabs Ready-made | Positions | Saved Strategies |
  Draft Portfolios.
- RIGHT column: summary strip, chart tabs, what-if sliders, IV / Greeks / standard-deviation panel.
- "Prices last updated at <time>"; the computed numbers refresh every 30 seconds (prices also arrive over a websocket).

### 1.2 Ready-made strategies (010-012, 100)
- Empty state "No Trades Added", "Build a new custom strategy"; catalogue filtered Bullish / Bearish / Neutral /
  Others plus an expiry picker; each card has a mini payoff icon.
- 36-38 presets. Bullish: Buy Call, Sell Put, Bull Call Spread, Bull Put Spread, Call Ratio Back Spread, Long Calendar
  with Calls, Bull Condor, Bull Butterfly, Range Forward, Buy Future, Long Synthetic Future. Bearish: Buy Put, Sell
  Call, Bear Call Spread, Bear Put Spread, Put Ratio Back Spread, Long Calendar with Puts, Bear Condor, Bear Butterfly,
  Risk Reversal, Sell Future, Short Synthetic Future. Neutral: Short Straddle, Iron Butterfly, Short Strangle, Short
  Iron Condor, Batman, Double Plateau, Jade Lizard, Reverse Jade Lizard. Others: Call Ratio Spread, Put Ratio Spread,
  Long Straddle, Long Iron Butterfly, Long Strangle, Long Iron Condor, Strap, Strip.
- One click loads real legs at ATM-relative strikes: e.g. Bull Call Spread = BUY 23000 CE / SELL 23200 CE for the
  27 Oct expiry. The SERVER picks the strikes (`POST oxide /v1/compute/1/presets`) and marks which legs are hedges.
- SENSEX has no "Buy Future" preset.

### 1.3 Leg row and leg controls (011-012, 101-107)
- Leg row: tick box (include / exclude the leg) | B/S badge | expiry dropdown (each expiry with days left, "27 Oct
  (6 Days)" ... "30 Mar (160 Days)") | strike with -/+ steppers (one strike step: NIFTY 50, SENSEX 100) | CE/PE |
  lots dropdown | price (editable; an edited price shows a small corner marker and is sent as the entry price) |
  depth icon | delete.
- Header: tri-state tick box, "<n> selected - <shape name>" (the shape is classified server-side, e.g.
  BULL_CALL_SPREAD, SHORT_IRON_CONDOR; mixed expiries give UN_KNOWN and only "<n> selected" shows), "Clear New
  Trades", "Reset Prices" (back to live).
- Unticking a leg removes it from the numbers AND changes the main button to "Trade <n>" (only ticked legs are
  sent). Example: untick the long put of an iron condor -> Max Loss becomes "Unlimited".
  **Lesson for OFO2:** this lets a user send a partial, unhedged strategy. See gap-list "must be different".
- Strike Controls (Dec 2025 feature): **Shift** -/+ moves every strike one step; **Width** -/+ changes the distance
  between the short strikes (iron condor 400 -> 500: shorts 22800/23200 -> 22750/23250; step = 2 strike gaps);
  **Hedge** -/+ changes the distance of the protective wings from the shorts (200 -> 250; step = 1 gap; asymmetric
  wings handled: the nearer side moves out to match). Controls show only for 2+ legs, at least one option, a
  recognised shape and no live positions loaded; Width and Hedge are disabled for unknown shapes (e.g. calendars).
  Computed in the browser, then the new legs are re-sent to the server (108-110).
- Multiplier 1..150 multiplies every leg's lots.
- Net premium line: "Price Pay 81.3  Premium Pay 5,285" ("Get" for a credit). Charges link.
- Buttons: Add/Edit (leg picker) | Add to Drafts (paper) | Trade All (basket) | "..." (Save, Save As, Share).

### 1.4 Summary strip (012, 125-129)
Max Profit and Max Loss (with % of funds needed) | Breakeven with a Target / Expiry toggle | Reward/Risk with a "1/x"
flip to Risk/Reward | POP (probability of profit) | Time Value | Intrinsic Value | Funds & Margins: Funds Needed,
Margin Needed, Margin Available (live from the broker), gear: include existing positions in the funds and margin
calculation. For an existing trade the tiles become Profit Left / Loss Left.

What the tooltips say (one-line paraphrases, not Sensibull's wording):
- POP: a model probability; for a credit trade it is high when the breakeven is far from the price, for a debit trade
  when it is close.
- Max loss: the most the trade can lose whatever the market does, except calendar spreads, which can lose more.
- Breakeven at target date: the level where P&L is zero on the target date, assuming IVs do not change.
- Intrinsic value: what the options would be worth if expiry were now; it is option value, not P&L.
- Funds needed: the margin to enter; buys must be completed first or the sells may need more funds or be rejected.
- SD: about a 66% chance of staying within 1 SD and 95% within 2 SD on the target day.
- Projected P/L: from a theoretical Black-76 price (futures-based model), so it can differ from actual P&L,
  especially for illiquid in-the-money options.
- Delta / Theta / Vega / Gamma / Decay: each in rupees with a worked example.

**Lesson for OFO2:** Margin Needed above Margin Available showed NO warning in the builder (server field
`margin_shortfall` was null); the shortfall appeared only later inside the basket as a red icon (039, 139).

### 1.5 Charts (013-019)
Tabs: Payoff Graph | Payoff Table | P&L Table | Greeks | Strategy Chart; an "Add Booked P&L" toggle.
- Payoff Graph: expiry line (green/red) plus a blue target-date curve; open-interest bars for calls and puts on the
  same x-axis (choose OI or change in OI, and which expiries); -2SD..+2SD bands on the top axis; current-price marker;
  "Projected profit/loss" badge; zoom. SD mode: Fixed (N days, default 7) or Dynamic (= target date). "OI overlay is
  not available for MCX, USDINR and far expiries" (hidden unless a leg expires within 60 days).
- Hover tooltip: "When price is at 23,480 +2.2% (+509) | Expected P&L on <target date> <amount> (<%>) | Expiry date
  <amount> (<%>)".
- Payoff Table: rows of underlying levels at a chosen interval (e.g. 50), columns P&L on target date and on expiry,
  current price highlighted, "Show %".
- P&L Table: per leg Target P&L, Target Price, Entry Price, LTP; Total "Projected"; lot-size / lots toggles.
- Greeks: per leg Delta, Theta, Decay, Gamma, Vega and Total.
- Strategy Chart: about two weeks of the combined strategy price against NIFTY futures; "Invert Price".

### 1.6 What-if (020) and IV panel
- "NIFTY Target" slider with a number box (e.g. +6.1% -> 24392) and a "Date: 4D to expiry" slider with < > steps and
  Reset. Every number (projected P&L, target breakeven, Greeks) recomputes.
- Strikewise IVs: per-leg IV with -/+, an Offset that shifts every IV (+1 vol point turned a projected -412 into
  -901 in one example), "Reset IVs". Target Day Futures Prices (put-call parity where no future trades). Standard
  Deviation table (1SD ~448 points ~2% on that day).

### 1.7 Other builder pieces
- Charges popup (022): Brokerage + STT + exchange transaction + GST + stamp + SEBI, with a disclaimer that charges
  are approximate.
- Depth popup per leg (024): OHLC and best bid / offer with quantities.
- Settings (025): Lots vs Qty; show Manual P&L.
- Info panel (026-031): price, OHLC, expiry, futures; tabs F&O Data (futures OI change, ATM strike, PCR, lot size,
  ATM IV, max pain, P&L per Rs 1 move, IV percentile, India VIX), Events (macro events with impact), Candlestick
  Patterns, Futures prices (real and synthetic), Contract specifications.
- Chart window (027): TradingView chart with an OI profile.
- Leg picker drawer (032-038): tabs Straddles | Strangles | Strikes | Futures; expiry select; LTP / OI / Greeks column
  sets; per strike B / S buttons and quantity; Strangles has Quick Select 50/100/150/200 points; switching tab asks
  "You are changing strategy type from Strikes to Straddles" (Cancel / Proceed); "<n> legs selected", Clear All, Done.
- Manual P&L: "a (positive or negative) number that you can enter to account for P&Ls from any past positions"; it
  shifts max profit, max loss and breakevens.
- Save (115-117): "..." -> Save / Save As / Share (Facebook, Twitter, WhatsApp, Telegram, Copy Link); name up to 20
  characters. The saved record keeps the legs and their initial prices, NOT IVs, target or manual P&L. Saved
  Strategies tab lists name + "NIFTY26OCT22500PE and 3 more" with search. Delete = archive.
- Builder Positions tab: would list live broker positions to analyse or adjust ("No positions found" in the study).
- Calendar / diagonal: the "On Expiry" line becomes a curve (later leg valued by the model at the first expiry).
- Warnings drawer "Your warnings": codes from the server, text owned by the browser - weekend theta bleed, holiday
  bleed, upcoming results event, physical delivery (stocks), margin shortfall penalty, "No stop loss" (an unhedged
  position: place a stop loss or buy a further strike), and per-leg liquidity (not traded in the last 5 minutes; bid /
  offer spread too wide, use limit orders).
- "Important info": "The profit and loss are projections, and they depend on premia, liquidity, IV, etc."
- **Lesson for OFO2:** switching the underlying (NIFTY -> SENSEX) silently cleared every leg, no confirmation.
- Without a broker login (Google, 200-206): the builder works, shows "Standalone Funds / Standalone Margin" (no
  available margin), Trade is disabled with "To trade this, login with a supported broker.", Add to Drafts still works.

### 1.7b Builder controls seen in a second pass (same day, Zerodha login)
- **Refresh prices** (round button) re-runs the numbers on the latest market data but does NOT change the legs' entry
  prices. **Reset Prices** re-bases every entry price to the current LTP (measured: 188.05 -> 189.8) and recomputes.
- **"Prices have changed" marker:** entry prices are frozen when a strategy is loaded or added; a small corner marker
  on a price means the live price has moved since.
- **Saved strategies keep save-time prices:** reopening a saved strategy restores its legs WITH the prices saved at
  save time (and any manual price edit), not today's prices; Width/Hedge values come back too. Rename is a pencil
  (20 characters). Delete asks "This action cannot be reversed." but is a soft delete (the record is archived).
- **Drafts Mode inside the builder:** a draft-portfolio strategy loads in a dashed blue frame with Net Positions /
  Orderbook, add orders manually or import Zerodha trades, exit all, per-leg booked / unbooked P&L, convert to a real
  trade. For positions already held, the summary shows **Profit left / Loss left** first (what is still to gain or lose
  from now) and the original max profit / max loss below.
- **Free vs Pro wall (Google login, free plan):** only the default Bull Call Spread loads; any other ready-made card
  opens "Upgrade to Sensibull Pro" (custom strategies, payoff diagrams, target price and date, Greeks, IV, IVP). Draft
  Portfolios are hidden for Google logins.
- **Standalone funds / margin:** the margin needed for the new trades alone, ignoring every other position and any
  margin benefit from them. Shown for Google logins, in Drafts Mode, or when "include existing positions" is off; with
  Zerodha and the toggles on, the labels are Funds Needed / Margin Needed plus Margin Available from the broker.
- Payoff Table target interval 10 / 25 / 50 / 100; Greeks "Multiply by Lot Size" turns per-unit Greeks into
  per-position (delta 0.52 x 65 = 34). Strategy Chart plots a debit strategy as a negative price ("Invert Price" flips
  it). Builder settings (Lots/Qty, SD mode, include positions) are account settings stored on Sensibull's server.
- Bug seen (screenshot 220): switching the underlying from the search box while the builder is in Drafts Mode crashed
  the screen to "Oops! Something went wrong ... Retry". OFO2 already locks the underlying while legs exist.
- Multiplier 2 doubles every leg's lots and every number (BANKNIFTY spread margin 39,743 -> 78,517). A single futures leg
  disables the strike box and turns the main button into a one-click "Buy". An "Insights" link opens a "Your warnings"
  drawer (e.g. "No stop loss" for an unhedged future), with chips Decay / Stoploss / Event / Delivery / Shortfall.

### 1.7c Every ready-made strategy on every index (measured matrix, 152 rows)
Method: for each index (NIFTY, BANKNIFTY, FINNIFTY, SENSEX) and each of the 38 preset codes, the page's own read-only
compute calls were made (presets -> builder_v3 -> calculate_margin_v5), nearest expiry, 1 lot per leg. The full
matrix (legs, max P/L, breakevens, POP, net premium, margin, detected shape) is kept in the study folder on the owner's
PC; this is the public-safe summary.
- **How Sensibull places preset strikes:** ATM = the strike nearest spot. Spreads and ratios put the second strike
  about 1% of spot away (200 points on NIFTY / FINNIFTY, 500 on BANKNIFTY, 400 on SENSEX). Iron condor and strangle
  shorts sit one such distance either side of ATM, wings another distance out (NIFTY at ~22,810: shorts 22600 / 23000,
  wings 22400 / 23200). Condors, butterflies, range forward and risk reversal start about 250 (NIFTY) / 500 (BANKNIFTY) /
  700 (SENSEX) points out of the money with equal wing gaps. Calendars sell the near expiry and buy the same strike in
  the next MONTHLY expiry. Batman uses ratio spreads 50 points apart; Double Plateau = bull condor + bear condor
  (8 legs). In short: a fixed, mechanical rule from ATM, not a market view.
- **Shape detection names only 16 shapes** (single calls/puts, straddles, strangles, iron condors and butterflies, the
  four vertical spreads, long and short); everything else (ratios, calendars, condors, butterflies, jade lizards,
  synthetics, futures, strap / strip) comes back UN_KNOWN, so Shift / Width / Hedge are not offered for them.
- **SENSEX has no futures presets** (Buy Future / Sell Future return an error; the UI hides them).
- **FINNIFTY "Long Calendar with Calls" fails** with a server "Internal Calculation Error" (an index with monthly
  expiries only).
- **Every preset carried a "liquidity_risk" warning**, so the warning is shown so widely that it loses meaning.
- **Margin vs max loss example:** a NIFTY bull put spread (sell 22800 PE, buy 22600 PE) has a max loss of about
  Rs 9,222 but needs about Rs 37,393 margin (~4x), because Zerodha blocks SPAN + exposure, not just the max loss.
  Sensibull's "funds needed" is roughly margin + premium paid, not exact. Sensibull's max profit / loss excludes
  charges.

### 1.8 Basket order panel from the builder (040-044)
- Header: broker, Intraday / Overnight, refresh prices, Charges & Margin. Per leg card: 5-level depth, OHLC, last and
  average price, Market / Limit, price, lots and a per-leg SELL/BUY button that sends THAT leg at once. Footer: Margin
  Needed vs Available (red icon when short: "You may not have enough margin to do this trade."), Re-arrange (drag the
  order sequence; default = the sequence with the least margin), "Place All at Market" with a dropdown (all at limit,
  individual).
- After one leg is placed alone, "Place All" is disabled; a rejected leg shows its reason and a Retry button.
- Buy-before-sell is only advice text; no client code orders buys first (bundle 7.3).
- Market protection: a market order far from LTP becomes a limit 0.5%-5% away.
- **Lesson for OFO2:** per-leg send buttons sit inside the review sheet where a scroll moves other controls; this is how
  the study's one misclick sent a real order (rejected). Sensibull lets one leg of a multi-leg strategy go alone
  (legging risk) and shows the margin shortfall only as an icon, without blocking.

---

## 2. Strategy Wizard (070-075) - `/trade-options-strategies`
- Inputs: stock or index, prediction (Above / Between / Below; code also has Not above, Around, Not below), target
  value, target date (expiry), filters, Go. "Tell us where a stock is going and we will give you smart option
  strategies to trade."
- Result: "We found 743 trades for your prediction of NIFTY above 23300 on 27 Oct"; table Trade, Profit, Breakeven,
  Approx. capital, "<n> days return %", Trade; sorted by profit; 149 pages.
- Filters: premium get/pay; expiries; hedged (buy call, buy put, call spread, put spread, iron condor, iron
  butterfly) and unhedged (sell call, sell put, straddle, strangle) with counts; ATM IV on target per expiry
  (editable); spread gap 50..500; max loss limit; min profit; delta range.
- "16 events that can affect your trade" table; a caution that projected P&L is "illustrative, educational, and
  indicative only".
- Page title: "Find the Most Profitable Options Strategies".
- **Lesson for OFO2:** profit-ranked results and "most profitable" wording are forbidden by ADR-003 / ADR-055.

## 3. Easy Options (080-087) - `/trade-options` ("Simple, low-risk, and fun option trading")
- Per index: "Where do you think NIFTY will go in 6 days?", a plain explainer of the index, a 1-month chart, UP /
  NEUTRAL / DOWN.
- UP gives three cards: Defensive / Balanced / Aggressive ("Choose this if you think NIFTY will not go down, and stay
  above 22866 (-0.5%)"), max profit, max loss, lots -/+, standalone funds, Add to Drafts / Trade.
- "How does this trade work?" in plain bullets ("You buy 23000 Call because you think NIFTY will go up; You sell 23100
  Call to reduce your costs and losses ..."), mini payoff, max profit "When NIFTY is above 23100", breakeven
  "23046 move by +0.3%", margin with a "Refundable" badge.
- Add to Drafts: choose / create a draft portfolio -> confirm legs -> "This is not a real trade. This is a draft
  portfolio without real money." -> Load in Builder / Open full draft portfolio.

## 4. Expiry Trades (160-165)
- "Where will SENSEX close on Expiry?" Bullish / Bearish / Neutral; index list with expiry day and when trades become
  available; a target ladder (Defensive / Moderate / Aggressive / "YOLO") with "Time left"; card with profit, max loss,
  standalone funds; details in plain bullets ("This strategy will make 1788 Rs if SENSEX expires above 74200").
- **Lesson for OFO2:** "YOLO" framing and profit-first cards are the opposite of OFO2's positioning.

## 5. Draft Portfolios / paper trading (090-092) - `/draft-portfolios/<id>`
- "Drafts Mode" (dashed border): totals (Total / Unbooked / Booked P&L, Total Decay), strategy list with tick boxes,
  strategy header with notes, Net Positions / Orderbook tabs, Open in Builder, Add Orders, Exit Orders, Edit, Delete,
  "Convert To Real Trades", Greeks, Import Orders (import a real order book into a draft).
- "Real Trades cannot be placed/modified while in Draft Portfolios/Drafts Mode".

## 6. Positions (050-053) and Orders
- Positions: toggle Positions | Groups; totals Total / Booked / Unbooked P&L, Total Decay; charges; Share Verified
  P&L; closed positions toggle; View Funds drawer (available margin, used margin, cash, SPAN, exposure, premium,
  collateral, add / withdraw funds link).
- Groups: "Keep a track on your strategies by grouping different positions together"; menu Open in Builder, Exit
  Positions, Add to Group, Add to Drafts, Stoploss Order, Conditional Exit. Positions poll every 45 seconds.
- Orders: All | Open | Executed | Stoploss | Conditional Exits; row time, side, product, instrument, LTP, filled /
  total, price, status. Orders placed outside Sensibull: "please use your broker".

## 7. Conditional exits, stop-loss, ATO
- Conditional Exit (June 2025): exit all selected positions when the INDEX crosses a level; "powered entirely by
  Zerodha's 'Alert Triggers Order (ATO)' feature", Zerodha only, NSE/BSE indices only; set from Positions, can click
  the payoff graph to set the level; max 20 trades per conditional exit; warnings for duplicate ATOs, multiple exits,
  quantity mismatch, and an exit that would open a new inverse position if the position was already closed.
- Limit caution: "Your order will be dispatched to the exchange when <underlying> goes <direction> <price>. ... your
  limit order may not get traded."
- Stop-loss orders on Zerodha listed per position ("Stoploss set", "SL Qty").

## 8. Option Chain (060-067) - `/option-chain`
- Header: underlying, chart, Info, expiry with days left, futures price, India VIX, IVP, Per Lot toggle.
- LTP view: Calls (OI change %, OI with bar, LTP) | Strike | IV | Puts (mirror); ITM shaded; ATM strike bold.
- Greeks view: Gamma Vega Theta Delta OI | LTP | Strike | LTP | OI Delta Theta Vega Gamma.
- All-columns view: OI change, OI %, OI, bid, offer, intrinsic (vs futures or spot), time value, breakeven %, LTP
  change, strike, IV change, mirrored for puts.
- Row hover: B | S | quick trade | chart | more. Settings: lots / qty, strikes around ATM 10-40, 100-multiples only,
  font size, Download as Excel. "Open with" OI / IV / Live Charts.

## 9. Analyse pages (140-153)
- Open Interest: OI Change (intraday or custom range, time slider, strike range), Open Interest (bars, replay), Multi
  Strike OI, Option OI vs Time (with PCR), Futures OI vs Time (long buildup / short covering / short buildup / long
  unwinding).
- FII / DII data: participant x segment with Bullish / Bearish strength labels, history.
- Live Options Charts: auto ATM straddle price and VWAP, replay; Multi Straddle-Strangle charts.
- Stock Data, Options Screener (ATM IV, IV change, IVP, results date, volume spike, OI action), Heatmap, Technical
  Signals (candlestick patterns, MAs), IV Chart, Calendar (economic, results, holidays).
- Market Analysis: a daily video plus a written "Verdict" and "Trades?".
  **Lesson for OFO2:** editorial verdicts and trade ideas are research-analyst services; Sensibull shows "SEBI
  Registered Research Analyst INH200006895". OFO2 holds no such registration (spec F-24, ADR-055).

## 10. Other screens
- Home (000-001): social proof ("<n> people are sharing their live positions right now"), live P&L cards carousel,
  six tiles (Easy options, Strategy wizard, Strategy builder, Draft Portfolios, NIFTY Heatmap, #VerifiedBySensibull),
  "Mindful Trading: Breathe, then trade" promo, lower list grouped by job.
- Mindful Trading: when on, a trade goes through 1) today's stats (pauses, skipped trades), 2) a 10-second breather,
  3) "Have you thought this through?" check-in, 4) the trade. In-app rules: "Capital preservation is the only job you
  have as a trader", "Keep at least 30% extra margin", "Never trade illiquid options".
- Watchlist: 10 lists, instruments AND strategies can be watch-listed, TradingView chart with OI profile.
- Verified by Sensibull: P&L leaderboards (long-term, live, daily: P&L, charges, accuracy, capital), follow traders,
  share on Twitter.
- Learn Options Strategies: one page per strategy (example with live strikes, Open in Builder, payoff sketch, Market
  View, The Trade, Breakeven, Max Profit / Loss, Effect of Time / Volatility, Pros, Cons, Summary). Free video courses.
- Settings: chart provider (TradingView by Sensibull, ChartIQ by Kite, TradingView by Kite), light / dark theme.
- What's New blog: Quicker Strike Controls (Dec 2025), basket page changes, Conditional Exits (Jun 2025), import order
  book into drafts, SL orders on Zerodha, FII DII revamp, OI page, OI profile.

## 11. Login, plans and pricing (180-181, 200-206)
- "Login with your broker": Zerodha (+ open an account), other brokers: Angel One, Upstox, ICICI Direct; "Sign in with
  Google"; "Is it safe to login with my broker?". "No extra charges to trade directly from Sensibull - You only pay
  your normal brokerage to your broker." Every page is browsable logged out (feeds delayed 1 minute).
- Zerodha login: "Active Pro Plan - Pro Plan is available to you at zero cost", "Highest Plan with all 25+ features,
  Rs 0/month".
- Google login: 3-day full trial then a free plan ("No automatic charges"); Pro list Rs 1,300 -> Rs 800/month ("Just
  Rs 27/day"), 1-year offer Rs 392/month; anniversary sale 24 months Rs 9,999, 12 months Rs 5,555.
- Free plan ("8 Useful Features"): basket orders, watchlist, basic option chain, FII DII, stock data, education,
  daily market analysis, Verified by Sensibull, events calendar. Pro only: Strategy Builder, analyse trades and
  positions, named position groups, Strategy Wizard, Expiry Trades, Easy Options, advanced option chain, OI charts,
  multi-strike OI, live options charts, multi straddle-strangle, heat map, screener, technical signals, IV chart.
- **Business reading:** Zerodha users get Sensibull Pro free (Zerodha-subsidised). A paid OFO2 aimed at Zerodha users
  competes with a free, mature product.

## 12. APIs and architecture (observed)
- Hosts (Cloudflare, Mumbai edge, HTTP/3): `web.sensibull.com` (Vite-built React SPA, ~263 lazy chunks, 4.3 MB);
  `oxide.sensibull.com` (compute: builder maths, presets, margin, OI, draft portfolios; `/v1/pluto` = login and order
  baskets); `api.sensibull.com` (older API, Python/Tornado by its 404 page; saved strategies, builder settings);
  `portal.sensibull.com` (journal, shared analyses); `aperture-api.sensibull.com` (first-party event tracking);
  `wss://wsrelay.sensibull.com/broker/{id}` (binary live prices and order updates; ping check every 15 s, reconnect
  after 60 s of silence).
- Builder data flow: preset -> `POST /v1/compute/1/presets` returns trades by Kite instrument token and the hedge
  legs; every edit -> `POST /v1/compute/1/builder_v3` (~1 KB request, ~58 KB reply) returning everything the screen
  needs: max profit / loss, profit left / loss left, reward/risk, breakevens at expiry and at target, Greeks, POP,
  intrinsic / time value, two 823-point payoff curves, SD, projected futures, per-trade details, liquidity warnings,
  insights (theta bleed, stop loss, event, physical settlement, margin shortfall), builder warnings, and the slider
  bounds and steps. Stale replies are dropped by a request id. Margin -> `POST
  /v1/compute/1/broker_data/calculate_margin_v5` (quantity in UNITS there, in LOTS in builder_v3), with "consider
  existing positions" flags. OI overlay -> `builder_intraday_oi_v2`. Drafts -> `/v1/compute/vt2/...` ("virtual
  trading"). Charges -> `broker_data/user_order_charges`. Liquidity -> `check_liquidity`.
- No pricing maths in the browser: every payoff, POP, Greek and breakeven is server-side. The browser computes only
  Shift / Width / Hedge, the IV offset and date clamping.
- Frontend stack: React 18.3.1, Redux Toolkit + RTK Query + redux-saga, styled-components 5.2.1, Material-UI v4
  remnants, Radix UI, date-fns + moment, lodash, custom SVG charts, self-hosted TradingView charting library.
- Third parties: RudderStack (analytics pipeline), Google Analytics, Bugsnag (errors), Microsoft Clarity (session
  replay), Freshchat (support chat), Razorpay (payments), Google sign-in.
- Environments in the bundle: production, staging (several), QA, test. Broker-branded basket sites per broker.

Lessons for OFO2 from the architecture:
- One compute call that returns every number AND the warnings AND the control bounds keeps the screen dumb. That
  matches OFO2's ADR-008 ("One strategy/risk engine produces every number"); OFO2's outcome API should also return
  slider/stepper bounds and warning codes rather than leaving them to the browser.
- Two quantity units (lots in one call, units in another) is a bug magnet; pick one at the API boundary.
- Warnings as codes with text owned in one catalogue is the same pattern as OFO2's reviewed template catalogue
  (ADR-003 Q226).
- A 30-second recompute is enough for a planning screen; OFO2 already pushes at most once a second (W-065).
