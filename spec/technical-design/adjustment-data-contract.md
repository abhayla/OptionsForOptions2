# Adjustment Data Contract (design note)

Status: delegated design note, not an acceptance criterion. Source: ChatGPT's plan in T2 #104 (the owner asked "So
where are we? How do you want to proceed?", T2 #103, and delegated the answers, T2 #83/#99). The owner did not
separately confirm this matrix; it is the working method for ADR-012 and ADR-013, not a new requirement.

## The matrix

Every piece of data or metric the adjustment engine may use gets one row (T2 #104, "This becomes our **Adjustment
Data Contract**"):

| Data / Metric | Source | Raw/Derived | Frequency | Historical? | Strategy-specific? | Scale approach |
|---|---|---|---|---|---|---|
| NIFTY spot | Market provider | Raw | Live | Yes | No | Shared |
| Option LTP | Market provider | Raw | Live | Yes | Contract | Shared |
| Net Delta | Our calculation | Derived | Live | Snapshot | Yes | Per strategy |
| 5-day NIFTY move | Our calculation | Derived | Periodic | Yes | No | Shared |
| Strategy P&L | Our engine | Derived | Live | Yes | Yes | Per strategy |

(The five rows are T2 #104's examples, not a complete list.) A value found later — e.g. in the owner's YouTube
adjustment video (open-questions Q212) — is placed into this matrix to decide whether it is feasible, and passes the
Data Feasibility Test (ADR-012 Q166) before it is built.

## Scale class of every calculation

For 5,000 / 100,000 / 500,000 users, each calculation is put in one class (T2 #104, "Pass 3 — Scale architecture"):

- **shared once** — computed once and reused by every user (e.g. NIFTY 5-day move; ADR-012 Q170);
- **per active strategy** — computed for each active strategy (e.g. net Delta, strategy P&L);
- **only when requested** — computed on demand, not continuously;
- **stored historically** — kept as history (see ADR-013 Q168 tiers and storage rule).

Order of work (T2 #104): data inventory and feasibility → this matrix → scale classes → only then adjustment
intelligence (what is an opportunity, which metrics trigger it, which approaches are shown).


## Values in the owner's reference video (REQ-071, Q212) — recorded 2026-09-29
Source: the owner's Iron Condor adjustment video (YouTube id BpIyvYL5ahE, 30m46s, Hindi with English (India) captions),
linked in the owner chat at T2 #93. Transcript extracted on 2026-09-29 (method: youtube-transcript-api) and kept
outside the repo (third-party content). Quotes are the captions' own English, verified word for word against the
transcript (35 quotes, 1 corrected). Values only — the video's adjustment method is deliberately not copied (REQ-071
AC-1). "In contract?" compares with the five example rows above only; several "No" values are already built elsewhere
(fill prices: REQ-057 / W-019; lots and expiries: the instrument catalogue, REQ-053; margin: REQ-056) and need only
a catalogue row here. Feasibility follows the Data Feasibility Test (ADR-012 Q166, REQ-047 AC-5); "unknown" mostly
waits on the vendor/licensing questions Q204/Q210 or on the pricing-model/IV-source choice. Rows marked unclear
(10, 12, 13, 24, 25, 26, 28) need the owner's meaning before they are built.

| # | Value | Transcript quote | In contract? | Source | Frequency | Calculation | Feasibility (contract's test) |
|---|---|---|---|---|---|---|---|
| 1 | Underlying spot (the video trades BANKNIFTY, which is outside this product's NIFTY/SENSEX scope; the value applies to NIFTY and SENSEX) | "Where is the market? Get option chain. The market is around 47.850." | Partly: "NIFTY spot" row; BANKNIFTY / other underlyings not listed | Vendor feed (interim Zerodha) | tick | raw | pass - raw, live; licensing per Q204/Q210 open |
| 2 | Option chain (strikes, expiries, per-strike prices) | "Get option chain. The call is of 260 rupees." | Partly: "Option LTP" only; chain/contract catalogue not a row | Vendor feed + instrument list | tick (prices), daily (contract list) | raw | pass - raw, live; scale shared once |
| 3 | Option LTP / premium of a leg | "Come to P&L. It will be written here. Current price 69.55." | Yes: Option LTP | Vendor feed | tick | raw | pass |
| 4 | Per-contract delta (Greek) | "Now I have to make 25 delta and 17 delta." | No (only Net Delta, strategy level) | Computed by our engine | per minute / on request | Pricing model from LTP, spot, IV, rate, time (record inputs per ADR-012) | unknown - calculable, but model, rate, IV source and reproducibility record not decided |
| 5 | Distance of a strike from spot, in points | "It means we need a call of 100 points away. So basically the market is 100 points away." | No (ADR-012 Q170 names "distances" but no row) | Computed by our engine | tick | strike - spot | pass - derived from raw rows 1-2 |
| 6 | Distance of a strike from spot, in percent | "Because if I see, This is 2% up and this is 2% down." | No | Computed by our engine | tick | (strike - spot) / spot | pass - derived |
| 7 | Gap between two strikes of one strategy (short-to-long width) | "I have to go 400 points away from this. 48900." | No | Computed from strategy legs | on event / leg change | abs(strike A - strike B) | pass - derived from legs |
| 8 | Strategy P&L (total, unrealised) | "Come up. There is a loss of 6400." | Yes: Strategy P&L | Our engine | tick | sum of leg (LTP - entry) x qty | pass |
| 9 | Realised (booked) P&L of closed legs, and their running total | "Here in the upper side, I have booked a loss of 15000." also "The losses you have booked, they add up here." | Partly: "Strategy P&L" does not split realised / unrealised or keep a running booked total | Our engine + Zerodha fills | on event (leg closed) | sum of (exit - entry) x qty over closed legs | pass - derived from fills |
| 10 | Remaining profit potential (max profit of current position) | "You still have a profit of 26000." also "You have only 5000 rupees left in the center to earn." | No | Computed by our engine (payoff engine, ADR-008) | tick / on leg change | max of expiry payoff, net of booked P&L (unclear if booked P&L is included - speaker's arithmetic not stated) | pass - engine-owned; exact definition unclear |
| 11 | Loss at a given market level (payoff-at-level) | "Earlier you had a loss of 40.000. Now you are having a loss of 14.000." | No | Computed by our engine | on leg change / on request | payoff at expiry at that spot | pass - core engine output |
| 12 | Payoff curve slope / steepness | "I am doing this so that my blue line has a low steepness." | No | Computed by our engine | on request | slope of the payoff curve (unclear whether "blue line" is the expiry or the current-day curve) | unclear meaning; if it means the curve, pass |
| 13 | Profit-zone edges on the payoff | "Then till you are in this pointer of green area, Basically this place and this place." | No | Computed by our engine | on leg change | spots where payoff = 0 (unclear: could mean break-evens or the strikes) | unclear meaning; if break-evens, pass |
| 14 | Net premium (credit) collectable / remaining | "If you do not have a premium of 100 rupees to gain, then why are you adjusting?" | No | Computed by our engine | tick | sum of sold premiums - sum of bought premiums, current | pass - derived |
| 15 | Fill prices (entry / exit) per leg | "I have booked it at 69.55." | No (Zerodha is authority on orders, ADR-016..019) | Zerodha orders/trades | on event | raw | pass - Zerodha API; needs user broker session |
| 16 | Lots / quantity and lot size | "We have taken 10 slots here." ("slots" is probably lots) | No | User input + instrument list; confirmed by Zerodha positions | on event | raw | pass |
| 17 | Expiry date / days to expiry | "Pay off will be obviously April. Because we are doing the month." | No | Instrument list + exchange calendar | daily | expiry - today, in trading and calendar days | pass |
| 18 | Time of day (market clock) | "We will start around 3 o'clock." also "It is 3.15 pm." | No | Platform clock + exchange session times | per minute | raw | pass |
| 19 | Broker auto square-off time on expiry day | "This is 3.24 pm. Here, Jirodha will cut his positions." | No | Zerodha published rule (not an API field) | daily | raw | unknown - clock value 3.24 pm not confirmed; must come from Zerodha's published rule |
| 20 | Overnight gap (open vs previous close) | "It was a big gap down. From 48500, the market went straight down to 47700." | No | Computed by our engine from spot snapshots | daily (at open) | today open - previous close | unknown - needs a stored previous close; V1 has no historical market data (REQ-047 AC-1, Q180) |
| 21 | Underlying move over 1 day (points) | "If the market closes 1000 points in the next day, then your destruction is simple." | Partly: "5-day NIFTY move" row; 1-day window not listed (Q170 lists 1/3/5/20-day) | Our calculation | periodic | spot now - spot N trading days ago | unknown - needs history; Q210 licensing |
| 22 | Underlying high-low range over a period (points) | "if you see this range, it has hit low from 49,000 to 46,500. 2,500 points." | No | Computed from stored spot / candles | daily | max - min of spot over the window | unknown - needs history (REQ-047 AC-1, Q210) |
| 23 | Daily / 1-hour candles (OHLC) of the underlying | "You can put a one-hour chart on the trading view if you want." | No | Vendor feed history (video uses TradingView, outside our platform) | per candle | raw | fail for V1 - no historical market data for users (REQ-047 AC-1); unknown for later (Q210) |
| 24 | Swing high / swing low (support / resistance levels) | "So we have to find the range in the chart because of the swing." | No | Computed from candles | daily | pivot high/low detection (method not defined in video; unclear) | unknown - needs row 23; definition unclear |
| 25 | Trending vs range-bound state of the underlying | "The market is trending now. The market is trending, I do not put iron condor." | No | Computed from candles | daily | not stated in video (unclear) | unknown - definition not given; needs row 23 |
| 26 | Volatility (implied vol of options / premium level) | "There is a loss of 6400. Why? Because of volatility. It is not because of the movement." | No (Q170 lists "volatility measures", no row) | Computed from option LTP, or vendor field | per minute | implied vol solved from LTP with the pricing model (unclear whether the speaker means IV or India VIX) | unknown - model and source not decided (same as row 4) |
| 27 | Margin required by a strategy; margin available | "Ion condor has a low margin." also "That person can do it only when the person has a margin." | No (Q170 lists "margin utilisation", no row) | Zerodha margin API | on event / on request | raw (required); available margin raw | pass - Zerodha API; needs user session |
| 28 | Capital deployed and loss as percent of capital | "The loss is Rs. 19,000 at Rs. 5,00,000. It is going to touch almost 4%." | No | User input / margin (row 27) + our engine | tick | loss / capital x 100 (which capital: notional or margin, unclear) | pass once capital definition is chosen |
| 29 | Count of adjustments made so far | "If you adjust twice, your profit will be gone." | No | Platform activity history (REQ-047 AC-1) | on event | count of adjustment events on a strategy | pass - own history, always kept |
| 30 | Brokerage / charges and return on capital | "There is a 14% gain in capital. And the charges are 0.25%." | No | Zerodha charge schedule + our engine | on event | charges from fills; return = P&L / capital | unknown - charge schedule source/licensing not decided |

Not in the video: net delta (the contract's own example) is never spoken; only per-contract delta (row 4).

## Gap list (values the contract does NOT yet cover)
Rows with "No": 4 (per-contract delta), 5, 6, 7 (distances, width), 10 (profit potential), 11 (loss at level), 12, 13 (payoff slope/edges, both unclear), 14 (net premium), 15 (fill prices), 16 (lots), 17 (expiry / days to expiry), 18 (market clock), 19 (square-off time), 20 (gap), 22 (range), 23 (candles), 24, 25 (swing, trend), 26 (volatility), 27 (margin), 28 (capital %), 29 (adjustment count), 30 (charges).
Partly covered (extend an existing row): 1 (non-NIFTY underlyings), 2 (chain), 9 (realised vs unrealised), 21 (1-day window).
Fully covered: 3 (Option LTP), 8 (Strategy P&L).
Total: 30 rows; 2 covered, 4 partial, 24 gaps.
Unclear speaker meaning: rows 10, 12, 13, 24, 25, 26, 28.
