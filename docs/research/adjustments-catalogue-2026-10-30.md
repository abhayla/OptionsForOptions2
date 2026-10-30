# Adjustments: catalogue and draft playbooks (research, 2026-10-30)

Status: **RESEARCH + DRAFT**. Nothing here is a requirement or ships to users until the owner approves it item by item;
each approved item then becomes a REQ (or an edit of REQ-045/046/047/112) and, for Part 3, a default playbook
(REQ-045 AC-7).

Written in the role the owner set: an experienced, consistently profitable NIFTY/SENSEX options trader who adjusts
intraday and positional positions at the open, during the day, at the close and on expiry day.

**Owner answers that shape this document (2026-10-30, this session):**
1. Scope = what the app can **suggest** (the user reviews and executes). Automatic adjustments are listed, but only in
   Part 5, marked `SPEC CHANGE / later`.
2. Depth = **catalogue + draft playbooks**: every adjustment and supporting feature, then per-strategy playbooks with
   concrete starting numbers, marked DRAFT.

**Spec basis:** ADR-003 (decision support; "Possible adjustment", never "best adjustment"; adjustments never described
as reducing risk by default); ADR-206 (adjustments suggested on paper and on imported real positions; "the kinds of
adjustment are specified by the owner later; each specific then becomes a default playbook"); REQ-045 (triggers AC-3,
candidate actions AC-4, generic approaches only when no user rule AC-5, editable default playbooks AC-7, grouping AC-8);
REQ-046 (four layers, Before/After); REQ-047 (data, history tiers, no user-facing historical market data in V1);
REQ-071 + `spec/technical-design/adjustment-data-contract.md` (the 30 values from the owner's Iron Condor video, owner
readings Q246/Q248); REQ-112 (suggestion outcomes); ADR-016..019 (Zerodha is the authority, no auto retry); vision
(V1 = NIFTY on NSE, SENSEX on BSE, options and futures, Zerodha only). Legal review Q211 still applies to anything
personalised.

**Wording rule used below:** names like "roll the untested side" describe mechanics for the team. Any user-facing text
goes through the ADR-003 wording check.

---

## How to read this document

| Part | What it holds | IDs |
|---|---|---|
| 0 | How an expert decides whether to adjust at all (principles the app must respect) | P-01.. |
| 1 | Indian market facts that constrain adjustments (sourced, dated) | M-01.. |
| 2 | Catalogue of adjustment **actions** | A-01.. |
| 3 | Catalogue of **triggers** (what makes an adjustment worth looking at) | T-01.. |
| 4 | **Situations**: open, intraday, close, expiry day, events, overnight | S-01.. |
| 5 | Supporting **features** the app needs (incl. automatic ones, marked later) | F-01.. |
| 6 | **Draft playbooks** per strategy family, with starting numbers | PB-01.. |
| 7 | Data the above needs, mapped to the adjustment data contract | D-01.. |
| 8 | What competitors offer (gaps we can win on) | C-.. |
| 9 | Suggested build order (core first) and the owner decisions still open | |

"State in OFO2" columns use: **Built** (code exists), **Spec'd** (in an approved REQ, not built), **New** (not in the
spec yet). Built/Spec'd is from reading `backend/ofo/adjustment/`, `backend/ofo/rules/` and REQ-045/046/047/112 on
2026-10-30; it is a reading, not a test run.

---

## Part 0 — How an expert decides (principles)

These are not features; they are the rules every suggestion, playbook and screen must respect. Each one names what it
means for the app.

| ID | Principle | Why (plain words, one example) | What the app must do |
|---|---|---|---|
| P-01 | **Adjust the risk, not the P&L.** Act on what the position will do next (delta, distance to short strike, gamma, days left), not on how much it has lost. | A strangle down ₹6,400 only because IV rose (owner video row 26) is a different problem from one down ₹6,400 because spot is at the short strike. The first may need nothing. | Every trigger shows *why* in risk terms; Before/After shows Greeks, not only P&L. P&L attribution (F-13) tells "lost from movement" vs "lost from volatility" vs "gained from time". |
| P-02 | **Every adjustment is a new trade.** After adjusting, ask: "would I open this resulting position fresh, today, at these prices?" If no, closing is usually better. | Rolling a tested call further out for a ₹40 debit, to end with a position you would never open, just postpones a loss. | Before/After shows the *After* as if it were a fresh trade: max profit, max loss, POP, breakevens, margin. "Exit everything" is always one of the possible approaches. |
| P-03 | **Decide the exit and the adjustment budget at entry.** How many adjustments (usually 2), and the loss at which you stop adjusting and exit. | Owner video: "If you adjust twice, your profit will be gone" (row 29). Third adjustment = usually a losing trade being dragged. | Playbook fields `max_adjustments` and `stop_line` (F-07). After the limit, the only possible approaches shown are exit / reduce. |
| P-04 | **Count the cost.** Every adjustment pays brokerage, STT, exchange fees, GST, stamp duty and the bid-ask spread on 2-4 legs, and usually cuts max profit. | A 4-leg roll on 10 NIFTY lots can cost ₹600-1,000 in charges plus spread; if the premium left to earn is ₹1,500 (video row 14: "if you do not have a premium of 100 rupees to gain, then why are you adjusting?"), the adjustment can cost more than it can save. | Before/After shows an "Adjustment cost" line: charges + estimated spread + change in max profit; shows "premium still left to earn" (row 10). Warn when cost > X% of premium left. |
| P-05 | **Time changes everything.** The same 1% move is mild with 10 days left and violent on expiry day (gamma). | NIFTY at 24,000, short 24,200 CE: a 150-point move on day 1 moves its delta from ~0.25 to ~0.40; on expiry afternoon it moves it from ~0.10 to ~0.70. | Triggers and playbooks have different numbers by DTE bucket (≥5 days, 2-4 days, last day) and by time of day. |
| P-06 | **Undefined risk needs earlier action than defined risk.** Naked shorts (strangle, straddle, ratio) can lose without limit; spreads (condor, fly) cannot. | A short strangle's tested side at 0.35 delta is a stronger alarm than an iron condor's at 0.35, because the condor's wing caps the loss. | Default triggers are tighter for naked structures. "Add a hedge" (A-09) is always offered for naked positions. |
| P-07 | **Hedge first, then sell; close shorts before longs.** | Entering a short before its hedge blocks full margin (and risks a rejection); closing the long wing first leaves a naked short for seconds. | Every adjustment basket is ordered: buys before sells on entry, short buy-backs before long sales on exit (F-11). |
| P-08 | **Roll for a credit, or think twice.** A roll that costs money must buy a clearly better position. | Rolling the tested strangle side from 24,200 CE to 24,400 CE for a ₹30 debit, 10 days out, is fine; doing it on expiry day for a ₹30 debit usually is not. | Before/After labels a roll "for credit" / "for debit" and shows it. Playbooks prefer credit rolls. |
| P-09 | **Don't adjust into an event without knowing it is there.** RBI policy, Union Budget, election results, US Fed/CPI, a long weekend. | A short straddle carried into budget day can gap 2-3% at the open. | Event calendar (F-09) flags held positions before the event. |
| P-10 | **"Do nothing" is a valid approach.** Many triggers are noise; theta works for a seller if the short strikes are not threatened. | Spot moves 0.6% toward a 15-delta short strike with 6 days left: often no action is the best choice. | REQ-045 AC-4 already lists "alert only" and "no-trade proposal"; the panel must show "No change" as an approach with its own risk numbers. |
| P-11 | **Don't average a losing short.** Adding lots to a losing side doubles the risk at the worst time. | Selling another 24,200 CE because "it's now more expensive" on a strong up-move. | "Add quantity" (A-15) is shown with a red warning and never in a default playbook. |
| P-12 | **Liquidity first.** Only roll to strikes with tight bid-ask and OI. | A far strike with ₹2 bid / ₹4 ask costs 50% of its value just to enter. | Strike pickers in adjustments hide or flag strikes whose spread is > X% of mid (F-12). |

---

## Part 1 — Indian market facts that constrain adjustments

(Filled from sourced research, see table. Anything not verified on an official page is marked so.)

Researched 2026-10-30. Confidence: **OFFICIAL** = a Zerodha / Kite Connect / exchange page opened that day;
**SECONDARY** = broker blog or news only; **UNVERIFIED** = not found. These go into admin config (D-09), never
hard-coded, because they change: NIFTY's expiry day changed in 2025, and both its lot size and STT changed in 2026.

| ID | Fact | Value | Effective | Source | Confidence |
|---|---|---|---|---|---|
| M-01 | NIFTY expiry | Weekly **Tuesday**, monthly the last Tuesday; on a holiday, the previous trading day (in 2026 the shifts land on Mondays). SEBI allows one weekly index expiry per exchange | NSE Tuesday from 2025-09-02 | business-standard.com (NSE expiry swap, 2025-08-28) | SECONDARY |
| M-02 | SENSEX expiry | Weekly **Thursday**; on a holiday, the previous trading day | current | share.market weekly-expiry article | SECONDARY |
| M-03 | Lot size | NIFTY **65** (was 75), SENSEX **20** | NIFTY from the 2025-12-30 revision | zerodha.com/marketintel bulletin 429705; SENSEX: algotest.in blog | NIFTY OFFICIAL, SENSEX SECONDARY |
| M-04 | Freeze quantity (largest single order) | NIFTY **1,800** units; SENSEX UNVERIFIED. Kite Connect `autoslice` splits a larger order into at most 10 slices | NIFTY 2026 | 5paisa blog; kite.trade/docs/connect/v3/orders | NIFTY SECONDARY; autoslice OFFICIAL |
| M-05 | Expiry-day extra ELM | **+2% of notional** on short options expiring that day (open shorts and new shorts) | 2024-11-20 | zerodha.com/z-connect/?p=391917 | SECONDARY (SEBI text not opened) |
| M-06 | Calendar-spread margin benefit | **Removed on expiry day** for the expiring contract, which matters for A-03/A-04/A-14 rolls on expiry day | Feb 2025 (sources say 1 or 10 Feb) | same | SECONDARY, date conflict |
| M-07 | Intraday position-limit checks | Checked several times a day, not only at end of day | 2025-04-01 | same | SECONDARY |
| M-08 | STT, options | **0.15% of premium** on the sell side; ITM option **exercised at expiry**: 0.15% × intrinsic value × units, paid by the buyer. This is why an expert closes ITM longs before 15:30 instead of letting them be exercised | 2026-04-01 | support.zerodha.com STT article; "options on expiry day" article | OFFICIAL |
| M-09 | STT, futures | 0.05% sell side | 2026-04-01 | same | OFFICIAL |
| M-10 | Settlement | Index options are cash-settled at the index's **closing value** on expiry day. The closing value itself comes from the last 30 minutes of trading, which is why some sources say "30-minute average"; both statements describe the same thing. So a position can still move after 15:00 even with no trades of its own | current | nseindia.com settlement-price page (search snippet) | SECONDARY |
| M-11 | GTT on options | Allowed on **NFO** (valid until expiry; cancelled if the lot size changes; OCO = stop-loss plus target). BFO support UNVERIFIED. Per instrument, not per strategy | current | support.zerodha.com GTT F&O article | OFFICIAL for NFO |
| M-12 | Basket order and hedge margin | Kite baskets compute the hedged margin. Zerodha's own article adds the sell leg then the hedge **inside a basket**; for separate orders the practice is buy first. **Exiting the hedge before its short raises margin** and can cause a shortfall | current | support.zerodha.com basket-OTM article | SECONDARY (snippet). Our rule P-07 / F-11 stays: buy first on entry, buy back the short before selling the hedge on exit |
| M-13 | Iceberg orders | Kite Connect variety `iceberg`, 2-50 legs | current | kite.trade/docs/connect/v3/orders | OFFICIAL |
| M-14 | MIS auto square-off | F&O **15:26** (₹50 + GST per order); no fresh MIS after the cutoff. BFO time UNVERIFIED. (Owner video row 19 said "3.24 pm"; that is now out of date) | page undated | support.zerodha.com intraday-auto-square-off-timings | OFFICIAL, BFO UNVERIFIED |
| M-15 | Low-OI contract blocks | Zerodha blocks **fresh** orders in low-OI contracts (NFO and BFO) at thresholds it does not publish. **Exits are always allowed.** An adjustment that rolls to a far strike can therefore be rejected on the new leg after the old leg is closed. The builder must warn about this, and P-12 applies | undated | support.zerodha.com oi-based-restrictions | OFFICIAL |
| M-16 | Expiry-day order cutoff | Zerodha publishes **none**; squaring off is the trader's job | current | support.zerodha.com options-on-expiry-day | OFFICIAL |
| M-17 | Kite API limits | **10 orders/s, 400/min, 5,000/day per user**; 25 modifications per order | current | kite.trade/docs/connect/v3/exceptions | OFFICIAL |
| M-18 | Market orders | Need `market_protection` (0-100% or -1 for auto), which turns them into limit orders within the circuit band. **SL-M is blocked on BSE/BFO**, so use SL-limit for SENSEX | current | kite.trade orders doc; support.zerodha.com slm-discontinued-by-bse | OFFICIAL |
| M-19 | Pre-open | 09:00-09:15 call auction for index and stock **futures only, not options** | 2025-12-08 (NSE/FAOP/71092) | business-standard.com | SECONDARY. For S-01, the futures pre-open price is an early read on the gap |
| M-20 | Normal session | 09:15-15:30 IST | current | already in the app: `backend/ofo/market_calendar.py` (ADR-119) | repo |
| M-21 | India VIX | Annualised 30-day expected volatility from out-of-the-money near- and mid-month NIFTY options (CBOE method) | current | nseindia.com India VIX page (snippet) | SECONDARY |
| M-22 | Algo rules for API orders | SEBI's retail-algo framework (2025) brings API order placement under broker approval and exchange-tagged algo IDs. This is relevant **only** to Part 5b automatic features | 2025 | not researched in this pass | UNVERIFIED. Must be researched before any F-A item |

**Gaps to close before building the dependent item:** SENSEX freeze quantity (F-11), BFO MIS square-off time and BFO
GTT (F-16 for SENSEX), the primary SEBI/NSE circular text for M-05..M-07, and M-22.

---

## Part 2 — Catalogue of adjustment actions

Grouped by what the action does. "Applies to" uses the app's catalogue ids (`backend/ofo/strategy/catalogue.yaml`).
REQ-045 AC-4 already lists, in general words: take profit, close leg, roll leg, roll spread, move strike, add/remove
hedge or leg, change quantity, re-centre, convert strategy, exit, alert only, no-trade proposal. This catalogue makes
each concrete enough to build a one-click builder and a Before/After.

### 2a. Rolls (move a leg to another strike or expiry)

| ID | Action | What it does | Typical use | When NOT to | Greeks / payoff effect | Cost | State |
|---|---|---|---|---|---|---|---|
| A-01 | **Roll the untested side toward spot** ("roll up the put" when market rises) | Buy back the far short (now cheap), sell a closer one of the same type | Strangle/condor when one side is tested: collects fresh credit, pulls net delta back toward zero | Market trending hard; untested side would be rolled to within ~1 SD of spot; already 2 adjustments | Reduces net delta; increases credit; narrows the profit range; max loss of a naked position rises on the untested side | 2 legs, usually a credit | Spec'd (generic "roll leg") |
| A-02 | **Roll the tested side away** ("roll up the call") | Buy back the threatened short, sell a further one | When the tested short's delta passes the trigger and there are still days left | Expiry day (debit is large, time to recover is nil) | Reduces delta and gamma on the tested side; costs a debit; breakeven moves out | 2 legs, debit | Spec'd |
| A-03 | **Roll out in time** (same strike, next expiry) | Close this week's short, sell the same strike next week | Tested short, near expiry, view unchanged: buys time and more credit | Event between now and the new expiry; next expiry illiquid | Lowers gamma, raises vega exposure, adds credit | 2 legs, usually credit | Spec'd |
| A-04 | **Roll up/down and out** (diagonal roll) | Close tested short, sell a further strike in the next expiry | The standard defence for a tested short with ≤2 days left | Same as A-03 | Combines A-02 and A-03; aims for a net-zero or credit roll | 2 legs | New (explicit) |
| A-05 | **Roll the whole spread** (both legs of a credit spread together) | Move the short and its wing by N strikes or to the next expiry | Iron condor / credit spread side tested; keeps risk defined | Width changes accidentally (builder must keep width unless asked) | Same as A-02/A-04 but stays defined-risk | 4 legs | Spec'd ("roll spread") |
| A-06 | **Shift a leg by ±N strikes** (one-click) | Generic: replace a leg with the same leg N strikes up/down | The building block for A-01, A-02, A-05; matches Sensibull's per-leg strike arrows | — | — | 2 legs | New (builder) |
| A-07 | **Re-centre / reset** | Close all legs, re-open the same structure around the current spot | Range trades (iron fly, straddle) after a clear move, when the view is still "range" | More than 1 reset per expiry; trending market | Resets delta to ~0; realises the loss; new credit | All legs | Spec'd ("re-centre") |

### 2b. Converts (change the structure)

| ID | Action | From → To | Typical use | When NOT to | State |
|---|---|---|---|---|---|
| A-08 | **Straddle-ise a strangle** | Short strangle → short straddle (move untested short to the tested strike) | Market moved to one short strike; maximise credit and delta-neutrality | Low days left with high gamma; the move looks like a trend | New |
| A-09 | **Add wings (buy hedges)** | Naked short → defined risk: strangle → iron condor, straddle → iron fly, naked call → bear call spread, ratio → butterfly/ladder | Before an event, overnight carry, a gap risk, or to cut margin | Wings so far they protect nothing (buy at a strike that caps loss at a number the user accepts) | Spec'd ("add hedge") |
| A-10 | **Inverted strangle** (untested short rolled past the tested one) | Strangle → inverted strangle | Last-resort for a strongly tested strangle, keeps collecting credit | Almost always: it locks in a loss of (strike gap) and is easy to misunderstand. Show only with a strong warning, never in a default playbook | New (warning-only) |
| A-11 | **Iron condor → iron butterfly** | Move both shorts to ATM | Market pinned near one side; collects much more credit | Trending market | New |
| A-12 | **Credit spread → butterfly / broken-wing butterfly** | Sell another short at the breached area, buy a further wing | Tested credit spread, to create a profit tent where spot now is | Far from expiry (butterflies need time to pay) | New |
| A-13 | **Add a jade lizard / no-upside-risk structure** | Short put + short call spread whose credit exceeds the call width | When the view turns mildly bullish on a short put | Credit < call-spread width (then upside risk remains) | New |
| A-14 | **Calendar / diagonal conversion** | Buy the same or nearby strike in the next expiry against the tested short | Tested short near expiry; vega is cheap | Next-expiry IV much higher than this expiry (buying expensive vol) | New |
| A-15 | **Ratio fix**: buy back the extra short lot, or add a long further out | Ratio spread → vertical, or → ladder/butterfly | Ratio's naked side tested | — | New |
| A-16 | **Long option → debit spread** (sell a further strike against a winning long) | Buy call → bull call spread | Long option in profit; lock part of it and cut theta/IV crush | Strong trend (caps the upside) | New |
| A-17 | **Long option roll-up** (take profit, buy a further strike with part of it) | Buy 24,000 CE → sell it, buy 24,200 CE | Winning long; keep exposure, take capital off the table | — | New |
| A-18 | **Gamma scalp a long straddle/strangle** | Sell/buy futures (or the profitable leg) as spot moves, to lock moves in | Long vol positions when realised moves are larger than the IV paid | Choppy, low-volume days (each scalp costs charges) | New |
| A-19 | **Convert calendar to double calendar** | Add a second calendar at the new spot | Spot moved away from a single calendar's tent | Close to near expiry | New |

### 2c. Hedge with futures or delta

| ID | Action | What it does | When | State |
|---|---|---|---|---|
| A-20 | **Delta-hedge with futures** | Buy/sell NIFTY or SENSEX futures lots to bring net delta near 0 | Large, short-dated delta imbalance on a big position; fast. One NIFTY future ≈ delta 1 per unit, so it neutralises the delta of ~2-4 short 0.25-0.50 delta lots | Spec'd under "add hedge or leg" (no futures detail) |
| A-21 | **Delta-hedge with a synthetic future** | Buy ATM CE + sell ATM PE (or the reverse) | Same as A-20 when futures margin or availability is a problem | New |
| A-22 | **Add a debit spread in the direction of the breach** | E.g. bull call spread on an upside breach of a strangle | Cheaper than futures, defined cost; partly offsets the losing side | New |
| A-23 | **Delta-neutral helper** | "To reach net delta ±X, buy N lots of strike K or N futures" calculator | Any time the user wants delta balance | New (feature F-10) |

### 2d. Size and exit

| ID | Action | What it does | When | State |
|---|---|---|---|---|
| A-24 | **Take profit, whole strategy** | Close all | Target hit (e.g. 50-60% of max profit for sellers) | Spec'd ("take profit") |
| A-25 | **Partial profit / scale out** | Close X% of lots | Profit reached early; reduce exposure into an event | Spec'd ("change quantity") |
| A-26 | **Close the untested side for profit** | Buy back the far short when it has decayed 80-90% | Frees margin, removes the "forgotten" tail; often paired with A-01 | New (explicit) |
| A-27 | **Buy back cheap shorts** ("close for pennies") | Buy back any short whose premium < ₹X (e.g. ₹2-3 NIFTY) | Before expiry day or before an event: tiny reward left, tail risk remains | New |
| A-28 | **Close the tested side, keep the rest** | Exit only the threatened leg/spread | Defined loss on one side, keep theta on the other | Spec'd ("close leg") |
| A-29 | **Reduce quantity on the tested side** | Close some lots of the threatened leg | Middle ground before a full roll | Spec'd ("change quantity") |
| A-30 | **Add quantity / average** | Add lots to a leg | Only for long, defined-risk ideas; for shorts it violates P-11 | Spec'd ("change quantity"); show warning |
| A-31 | **Exit whole strategy (stop)** | Close all at the stop line | Loss line, time stop, or view changed | Spec'd ("exit") |
| A-32 | **Leg stop-loss** | A per-leg stop at X% above a short's entry premium | Common Indian intraday style (09:20 straddle with 25-30% leg SL) | New (needs order-type research, M-facts) |
| A-33 | **Move stop to cost after one leg stops** | After one short leg stops out, move the other leg's stop to its entry price | Pairs with A-32 | New |
| A-34 | **Re-entry after a stop** | Re-sell the stopped leg when its premium returns to the entry price | Intraday straddles in choppy markets | New |
| A-35 | **Time exit** | Close at a set clock time (e.g. 15:15 intraday, or N days before expiry positional) | Intraday strategies; positional sellers avoiding expiry-day gamma | New |

### 2e. Non-trade approaches

| ID | Action | When | State |
|---|---|---|---|
| A-36 | **No change** (show the risk of doing nothing next to each alternative) | Every opportunity | Spec'd ("no-trade proposal") |
| A-37 | **Alert only / watch** (set a level to re-check) | Early warnings | Spec'd ("alert only") |
| A-38 | **Pause monitoring until a time** (e.g. until 09:30 after a gap) | Opening noise | New |

---

## Part 3 — Catalogue of triggers

REQ-045 AC-3 already lists: underlying move/level, distance from short strike/breakeven, leg profit threshold, strategy
max-profit/max-loss thresholds, Greek thresholds, IV change/percentile, DTE, premium, P&L, AND/OR. Built today:
distance of spot to short strikes and breakevens in percent (`backend/ofo/adjustment/detection.py`), and the rules
condition engine (`backend/ofo/rules/conditions.py`). New triggers an expert uses daily are marked **New**.

| ID | Trigger | Example threshold (starting point) | Why an expert watches it | State |
|---|---|---|---|---|
| T-01 | Spot within X% (or X points) of a short strike | 0.5% (≈120 NIFTY points at 24,000) | The classic "tested side" alarm | Built (percent) |
| T-02 | Spot beyond a breakeven | breakeven crossed | Expiry P&L now negative at this level | Built |
| T-03 | Short-leg delta ≥ X | 0.30 positional, 0.40 intraday | Delta ≈ rough chance of finishing ITM; normalises across DTE and IV better than distance | Spec'd (Greek thresholds) |
| T-04 | Net position delta beyond ±X per lot | ±0.15 × lot size per lot of strategy | Overall directional exposure grew | Spec'd |
| T-05 | **Premium imbalance**: one short side's premium ≥ R × the other side's | R = 2 (positional), 1.5 (intraday straddle) | The most common Indian strangle/straddle adjustment signal; easy for users to understand | **New** |
| T-06 | Loss ≥ K × credit received | K = 1.5-2 for strangles, 1 for condors (of max loss %) | Stop line for sellers | Spec'd (P&L) |
| T-07 | Profit ≥ X% of max profit | 50-60% sellers; 80% before expiry day | Take-profit; rest of the profit has bad risk/reward | Spec'd |
| T-08 | Leg premium ≥ (1 + X) × entry | X = 25-30% intraday, 100% positional | Leg stop-loss | Spec'd (leg profit threshold) partly |
| T-09 | Short premium ≤ ₹X | ₹2-3 NIFTY, ₹5-8 SENSEX | Close-for-pennies (A-27) | **New** |
| T-10 | DTE ≤ N / time of day ≥ H:M | DTE ≤ 1; 14:30 on expiry day; 15:15 intraday | Gamma risk and time exits | Spec'd (DTE) / **New** (clock) |
| T-11 | IV / India VIX jump ≥ X% intraday | VIX +10% intraday | Vega loss for sellers; possible event | Spec'd (IV change) / **New** (VIX) |
| T-12 | Spot move ≥ expected move (1 SD from IV over the holding period) | 1 SD | Move is outside what the option prices implied | **New** |
| T-13 | Gap open ≥ X% vs previous close | 0.75% | Overnight positions need a morning review | **New** (needs previous close, video row 20) |
| T-14 | Gamma risk: net gamma × (1% move)² large vs capital | rupee loss for a 1% move ≥ 2% of margin | Expiry-day danger in one number | **New** |
| T-15 | Margin utilisation ≥ X% | 80% of available | Risk of margin shortfall / forced exits; enables "add hedge to cut margin" | **New** (data row 27) |
| T-16 | Loss as % of capital (margin blocked) ≥ X% | 2% intraday, 4-5% positional (owner video row 28) | Capital-based stop | Spec'd (row 28 reading) |
| T-17 | Event ahead within N sessions (calendar) | 1 session | P-09 | **New** |
| T-18 | Adjustment count reached max | 2 | P-03: after this, exit/reduce only | **New** |
| T-19 | Remaining premium to earn < adjustment cost | cost ≥ 50% of premium left | P-04 | **New** |
| T-20 | Spot crosses a user level (support/resistance the user typed) | user-entered | The user's own technical view without us storing history | Spec'd (underlying level) |
| T-21 | Stale or missing data | no tick for N seconds | Never suggest on stale prices; say "data stale" instead | likely Built (check before build) |

Compound triggers (AND/OR) are Spec'd. An expert's favourite compound, as an example default: *"T-01 within 0.5%
AND T-10 DTE ≥ 2 → roll approaches; T-01 AND DTE ≤ 1 → close/hedge approaches only"*.

---

## Part 4 — Situations: what the expert checks, and possible approaches

| ID | Situation | What the expert checks first | Possible approaches (from Part 2) | App support needed |
|---|---|---|---|---|
| S-01 | **Gap up/down at the open** (overnight positional) | Size of gap vs short strikes; did IV jump? Is it an event day? | Wait 15 min (A-38) unless a short is ITM; then A-02/A-04, A-09, A-20; on a big gap through a strike, A-31 | Morning summary at 09:08-09:15 (F-14), pre-open price if available (M-facts), gap trigger T-13 |
| S-02 | **Trending day, intraday** | Net delta growing; premium imbalance T-05; is the move > 1 SD? | A-01, A-02, A-08 early; A-20/A-22 for size; stop at T-06 | Live triggers, one-click builders, Before/After |
| S-03 | **Range day** | Theta working; no action | A-36 / A-24 at target | Profit-target trigger T-07 |
| S-04 | **IV spike without a big move** (fear, global news) | Loss from vega vs from delta (P&L attribution) | Mostly A-36 (it reverts) unless near an event; A-09 for naked | F-13 P&L attribution, VIX trigger T-11 |
| S-05 | **IV crush after event** | Long-vol positions lose | A-24/A-31 for longs; sellers take profit A-24 | IV change trigger |
| S-06 | **Afternoon / closing (14:30-15:30), positional carry** | Will the position survive an overnight gap? Margin overnight? | A-09 add wings before 15:20 (cuts margin + gap risk), A-27, A-25; remove wings next morning | "Carry check" at 15:00 (F-15) |
| S-07 | **Expiry day** | Gamma, ELM on shorts, broker square-off time, STT on ITM longs, settlement price rule | A-27, A-28, A-35 (exit by 14:30-15:00), A-04 roll to next week; avoid opening new risk late | Expiry-day mode (F-16) |
| S-08 | **Day before a known event** | Event in calendar | A-09, A-25, A-27 or exit | Event calendar F-09 |
| S-09 | **Weekend / long holiday** | Theta for sellers vs gap risk | Hold with wings, or reduce | Holiday calendar (have `market_calendar.json`), F-15 |
| S-10 | **Broker/data outage while positions are open** | Can I still exit? | Show last good data with age; never suggest on stale data | REQ on stale data (check), F-21 |
| S-11 | **Position already adjusted twice** | Max adjustments | Exit / reduce only | T-18 |
| S-12 | **Big win early** (50% of max profit on day 1) | Risk left vs reward left | A-24 / A-25 | T-07 |

---

## Part 5 — Supporting features

### 5a. Suggest-only features (in scope now)

| ID | Feature | What the user gets | Built on | State |
|---|---|---|---|---|
| F-01 | Adjustment Opportunity panel, four layers + "Why am I seeing this?" | Why, current state, possible approaches, Before/After | REQ-046 | Spec'd, partly built (detection line) |
| F-02 | **One-click adjustment builders** for A-01..A-35 | Pick an approach → the exact legs are prepared (strike by delta, by points, by premium or by N strikes) and shown in Before/After | REQ-045 AC-5 / REQ-046 AC-4 | New (the core) |
| F-03 | **Side-by-side compare of every applicable approach** + "No change" (ADR-214 (2a)) | Table and overlaid payoffs on named criteria (money now, risk after, reward after, Greeks after, practical). Each criterion marks its leader ("Lowest max loss"); each option shows how many criteria it leads; no overall winner | REQ-046 AC-4 extended | New |
| F-04 | **Adjustment cost line** | Charges (brokerage, STT, exchange, GST, stamp), estimated bid-ask cost, credit/debit, change in max profit, cost as % of premium left (P-04) | charges module exists (`backend/ofo/charges/`) | New |
| F-05 | **What-if on the After** (spot, IV, date sliders) | See the adjusted position at different spots/days/IV before acting | builder what-if (B6/B7) | Partly built (builder); New on adjustment |
| F-06 | **Strategy lineage** | Original vs every adjustment: legs in/out, booked (realised) P&L running total (video row 9), adjustment count (row 29), total credit collected, "premium still left to earn" (row 10), adjusted breakevens including booked P&L | timeline REQ-040, REQ-112 | New (display); data partly exists |
| F-07 | **Playbook editor** | Global defaults + per-strategy overrides: triggers, allowed/forbidden actions, `max_adjustments`, `stop_line`, `profit_target`, `time_exit`, DTE buckets | REQ-045 AC-7, `backend/ofo/rules/defaults.py` | Spec'd, partly built |
| F-08 | **Entry plan prompt** | When a strategy starts tracking, ask once: target, stop, max adjustments, time exit (pre-filled from playbook) | P-03 | New |
| F-09 | **Event calendar** | RBI, Budget, election results, Fed, US CPI, expiry days, holidays; flags held positions N sessions before | Needs a data source (D-07) | New |
| F-10 | **Delta-neutral helper** | "N lots of futures / strike K to reach net delta ±X" | engine Greeks | New |
| F-11 | **Safe order sequencing** | Hedge-first, short-buyback-before-long-sale ordering; freeze-quantity slicing; margin check before | basket (exists), REQ-055/056 | Partly built (basket); New (ordering rule) |
| F-12 | **Liquidity guard on adjustment strikes** | Flag/hide strikes with wide spread or low OI | chain depth (exists) | New |
| F-13 | **P&L attribution** (delta / gamma / theta / vega / residual since entry and today) | "You lost ₹6,400: ₹5,900 from volatility, ₹900 from movement, +₹400 from time" (owner video row 26) | engine + IV history of the position (own data, REQ-047 tier) | New |
| F-14 | **Morning summary for carried positions** (09:00-09:15) | Overnight change, gap, IV change, which triggers are near, events today | T-13, F-09 | New |
| F-15 | **Carry check at 15:00** | For each positional strategy: overnight margin, gap-risk loss at ±2%, suggested wings cost | P-06, A-09 | New |
| F-16 | **Expiry-day mode** | Countdown to broker square-off, ELM on shorts, ITM long STT warning, positions near strikes, "close for pennies" list | M-facts | New |
| F-17 | **Grouped alerts by channel** | In-app now; WhatsApp/Telegram/email later through the shared Notifier gateway | REQ-045 AC-8, notification REQs | Spec'd (in-app); channels per existing open questions |
| F-18 | **Adjustment journal + effectiveness** | For each suggestion: outcome (REQ-112) and what happened after (P&L of Before vs After at expiry or N days, computed from own data) → "your rolls this month: 7, helped 4" | REQ-112 + own snapshots | Spec'd (outcomes) / New (effectiveness) |
| F-19 | **Paper-adjust a real position** | Try an adjustment on a paper copy of an imported real strategy and watch it before acting | ADR-206 paper tracking | New |
| F-20 | **Explainers per action** | Short "what this does, when it hurts" for each A-xx, decision-support wording | ADR-003 | New |
| F-21 | **Data-state honesty** | Every suggestion carries data time and freshness; none on stale data | REQ-046 AC-5 | Spec'd |
| F-22 | **Playbook backtest** | Run a playbook over past expiries to see how it would have done | Needs licensed historical option data (REQ-047 AC-1, Q210) | New, blocked on data licence |

### 5b. Automatic features — `SPEC CHANGE / later` (owner answer 1)

Listed so nothing is lost. None is in scope; each conflicts with ADR-003/ADR-206 today and needs legal review (Q211)
and, for API-placed orders, the broker's and SEBI's algo rules (see M-facts).

| ID | Automatic feature | What it would do |
|---|---|---|
| F-A1 | Auto stop-loss (strategy MTM or per leg) | Exit when the stop line is hit |
| F-A2 | Auto trailing stop | Move the stop as profit grows |
| F-A3 | Auto time exit | Close at 15:15 / N days before expiry |
| F-A4 | Auto re-entry after a leg stop | Re-sell when premium returns to entry |
| F-A5 | Auto delta hedge | Keep net delta within ±X with futures |
| F-A6 | Auto roll by rule | Execute A-01/A-02 when T-03/T-05 fires |
| F-A7 | Kill switch | Square off everything at a daily loss limit |
| F-A8 | Auto-hedge overnight | Add wings at 15:20, remove at 09:20 |

---

## Part 6 — Draft playbooks (DRAFT: numbers are common-practice starting points, not proven)

Honest caveat: these numbers are what experienced Indian index-option traders commonly use. They are **not proven on
our data**. Before any becomes a shipped default, each needs (a) owner approval and (b) a check on past expiries,
which needs historical option data we do not have licensed yet (REQ-047 AC-1). Until then they are editable defaults
the user owns, shown with ADR-003 wording.

Common fields of every playbook: `entry_hint` (shown, not enforced), `triggers` (T-ids with thresholds per DTE
bucket), `approaches` (ordered A-ids, shown as possible approaches, never one "best"), `profit_target`, `stop_line`,
`max_adjustments`, `time_exit`, `expiry_day_rule`, `event_rule`.

DTE buckets: **far** (≥ 5 days), **near** (2-4 days), **last** (expiry day and the day before, if it is the last
session).

"Tested side" = the short leg spot is moving toward. Worked numbers use NIFTY at 24,000 and lot 65 (M-03).

### PB-01 Short strangle, positional (weekly or monthly) — `short_strangle`

| Field | Draft value |
|---|---|
| Entry hint | Shorts near 0.15-0.20 delta (about 1 SD), entered with ≥ 4 days left; avoid the session before a known event |
| Triggers | **far**: T-03 tested short delta ≥ 0.30, or T-05 premium ratio ≥ 2, or T-01 spot within 0.75%. **near**: delta ≥ 0.35, or ratio ≥ 2, or within 0.5%. **last**: within 0.3%, or delta ≥ 0.40 |
| Approaches (order shown) | **far/near**: A-01 roll the untested side to about the tested side's current premium · A-02 roll the tested side out to 0.20 delta · A-09 add wings (→ iron condor) · A-36 no change · A-31 exit. **last**: A-28 close the tested side · A-04 roll to next week · A-27 buy back cheap shorts · A-31 exit |
| Profit target | T-07 at 50% of the credit received; 80% if expiry day is next |
| Stop line | T-06 loss ≥ 2 × the credit received, or T-16 loss ≥ 4% of margin blocked |
| Max adjustments | 2 (T-18), then only exit or reduce is offered |
| Time exit | Positional weekly: close or roll by 14:30 on the last day if any short is within 0.5% |
| Expiry-day rule | A-27 for shorts ≤ ₹3; the ITM warning (M-08) does not apply to shorts, but ELM does (M-05) |
| Event rule | T-17 one session before: show A-09 and A-25 |
| Worked example | Sold 23,500 PE @ ₹40 and 24,500 CE @ ₹38 (credit ₹78 × 65 = ₹5,070). NIFTY rises to 24,300: CE @ ₹95, PE @ ₹14, so ratio 6.8 → T-05 fires. A-01: buy 23,500 PE @ ₹14, sell 23,900 PE @ ₹55, which adds ₹41 credit and brings net delta back from about -0.35 to about -0.05 per lot. Before/After shows max loss on the downside is now nearer (23,900) and the new breakevens |

### PB-02 Short straddle / strangle, intraday (enter after the open, flat by close) — `short_straddle`, `short_strangle`

| Field | Draft value |
|---|---|
| Entry hint | ATM straddle after 09:20 (after the opening noise); weekly expiry contract |
| Triggers | T-08 a leg's premium ≥ 1.25-1.30 × its entry (leg stop); T-05 ratio ≥ 1.5; T-16 day loss ≥ 1% of margin; T-10 clock 15:10 |
| Approaches | A-32 close the stopped leg · A-33 move the other leg's stop to its entry · A-34 re-sell the stopped leg if its premium comes back to entry (max 1 re-entry) · A-08/A-07 re-centre once · A-35 time exit |
| Profit target | 30-40% of the combined premium, or the day target in rupees |
| Stop line | Combined loss ≥ 1% of margin, or both legs stopped |
| Max adjustments | 2 (one re-centre + one re-entry) |
| Time exit | 15:10, before the 15:26 MIS square-off (M-14) and its ₹50 + GST per order charge |
| Note | This style is mostly done automatically elsewhere (C-07). In our suggest-only scope it is a set of alerts + prepared baskets; the user must be watching. That limits its value until 5b. **Honest:** a suggest-only intraday straddle with a 25% leg stop will often fire faster than a person can act |

### PB-03 Short straddle, positional — `short_straddle`

| Field | Draft value |
|---|---|
| Triggers | T-01 spot beyond ± (0.6 × combined premium) from the strike; T-05 ratio ≥ 2.5; T-11 VIX +10% intraday |
| Approaches | A-07 re-centre (once per expiry) · A-01 roll the untested leg toward spot (the straddle becomes a strangle) · A-09 add wings (→ iron fly) · A-20 futures hedge for large size · A-36 · A-31 |
| Profit target | 25-35% of credit (straddles keep high gamma; take profit earlier than strangles) |
| Stop line | Loss ≥ 1 × credit, or 4% of margin |
| Max adjustments | 2 |
| Expiry-day rule | Re-centring on the last day is not offered after 13:00; close / roll only |

### PB-04 Iron condor — `iron_condor` (owner's reference video strategy, REQ-071)

| Field | Draft value |
|---|---|
| Entry hint | Shorts 0.15-0.20 delta, wings 200-400 NIFTY points beyond (video row 7 used a 400-point gap); entry with ≥ 5 days left; not in a strongly trending market (video row 25, out of V1 as data) |
| Triggers | T-03 tested short delta ≥ 0.30 · T-01 spot within 0.5% of a short · T-19 premium still left < adjustment cost (video row 14) · T-06 loss ≥ 50% of max loss |
| Approaches | A-01 roll the untested spread toward spot (credit) · A-05 roll the tested spread out (keep width) · A-11 convert to iron fly (only if days left ≥ 3) · A-28 close the tested spread · A-36 · A-31 |
| Profit target | 50% of max profit |
| Stop line | Loss ≥ 50% of max loss, or 4% of margin (video row 28: "almost 4%") |
| Max adjustments | 2 (video row 29) |
| Expiry-day rule | Close any spread whose short is within 0.3% by 14:30; A-27 the far side for ≤ ₹2 |

### PB-05 Iron butterfly — `iron_butterfly`

| Field | Draft value |
|---|---|
| Triggers | T-01 spot beyond 50% of the distance from the shorts to a wing · T-07 profit ≥ 25% of max profit (flies are hard to hold) |
| Approaches | A-07 re-centre the body · A-05 roll the tested wing pair · A-25 take partial profit · A-36 · A-31 |
| Profit target | 25% of max profit |
| Stop line | 50% of max loss |
| Max adjustments | 1 |

### PB-06 Credit spreads — `bull_put_spread`, `bear_call_spread`

| Field | Draft value |
|---|---|
| Triggers | T-03 short delta ≥ 0.35 · T-02 breakeven crossed |
| Approaches | A-05 roll the spread away and/or out for credit · A-12 convert to a (broken-wing) butterfly · A-22 add an opposite credit spread (makes an iron condor and adds credit) · A-28/A-31 close |
| Profit target | 50-60% of credit |
| Stop line | Loss ≥ 1.5-2 × credit, or short ITM with ≤ 1 day left |
| Max adjustments | 1 |

### PB-07 Debit spreads — `bull_call_spread`, `bear_put_spread`

| Field | Draft value |
|---|---|
| Triggers | T-07 value ≥ 70% of max value · T-02 against you by more than the debit paid's breakeven distance · T-10 DTE ≤ 1 |
| Approaches | A-24 take profit · A-05 roll the spread up (lock some profit, keep exposure) · A-31 exit · A-36 |
| Profit target | 70-80% of max value (the last 20% needs the expiry pin) |
| Stop line | 50% of debit |
| Max adjustments | 1 |

### PB-08 Single long option — `buy_call`, `buy_put`

| Field | Draft value |
|---|---|
| Triggers | T-07 premium +50% / +100% · T-08 premium -40% · T-11 IV falls ≥ 15% (vega loss; owner video row 26) · T-10 DTE ≤ 1 and OTM |
| Approaches | A-17 roll up and take capital out · A-16 sell a further strike against it (→ debit spread) · A-25 sell half · A-31 exit |
| Profit target | +100% → sell half (A-25) |
| Stop line | -40 to -50% of premium |
| Expiry-day rule | If ITM near the close, show the STT-on-exercise warning (M-08) and offer to sell before 15:30 |

### PB-09 Long volatility — `long_straddle`, `long_strangle`, `reverse_iron_condor`

| Field | Draft value |
|---|---|
| Triggers | T-12 spot moved ≥ 1 SD · T-04 net delta beyond ±0.30 per lot · T-11 IV crush after an event |
| Approaches | A-18 gamma scalp with futures or close the winning leg · A-25 take partial profit · A-31 exit after the event |
| Profit target | 30-50% of debit |
| Stop line | 30-40% of debit, or the event has passed |
| Time exit | The session after the event the trade was bought for |

### PB-10 Calendar / diagonal — `calendar_spread`, `diagonal_spread`

| Field | Draft value |
|---|---|
| Triggers | T-01 spot beyond the calendar's breakeven · T-10 near-leg DTE ≤ 1 |
| Approaches | A-19 add a second calendar at the new spot · A-03 roll the near leg to the next expiry (if the far leg has time) · A-31 close both |
| Profit target | 20-30% of debit |
| Stop line | 30-40% of debit |
| Expiry-day rule | Calendar margin benefit is removed on the near leg's expiry day (M-06): show the margin change |

### PB-11 Ratio spreads and back-spreads — `ratio_backspread_call`, `ratio_backspread_put`, ratio spreads

| Field | Draft value |
|---|---|
| Triggers | **Ratio spread (net short)**: T-01 spot within 0.5% of the short strike · T-14 gamma risk. **Back-spread (net long)**: T-07, T-10 |
| Approaches | Ratio: A-15 buy back the extra short, or add a long further out (→ ladder/butterfly) · A-09 · A-31. Back-spread: A-25 · A-31 |
| Stop line | Ratio: loss ≥ 2% of margin; this structure has unlimited risk on one side, so P-06 applies |
| Max adjustments | 1 |

### PB-12 Directional butterflies and condors — `butterfly_spread`, `bear_butterfly`, `bull_condor`, `bear_condor`

| Field | Draft value |
|---|---|
| Triggers | T-01 spot past the body by > half the wing width · T-07 profit ≥ 40% of max |
| Approaches | A-05 move the whole fly toward spot · A-24 · A-31 |
| Profit target | 40-50% of max profit |
| Stop line | 50% of debit |
| Max adjustments | 1 |

### PB-13 Naked single shorts, jade lizard, covered call / cash-secured put, futures and synthetics — `sell_call`, `sell_put_atm`, `jade_lizard`, `covered_call`, `cash_secured_put`, `buy_future`, `sell_future`, `synthetic_long`, `synthetic_short`

| Field | Draft value |
|---|---|
| Triggers | Naked short: T-03 delta ≥ 0.35, T-06 loss ≥ 2 × credit. Futures/synthetics: T-16 loss ≥ 2% of margin, T-01 user level |
| Approaches | Naked short: A-09 add a wing (→ credit spread) · A-02 · A-04 · A-31. Jade lizard: keep credit > call-spread width (A-13 check). Futures: A-21/A-22 protective option · A-31 |
| Note | Covered call / CSP need the underlying or full cash; for index options in India "covered" means a long future. The app should label that honestly |

### Coverage check

Every strategy in `backend/ofo/strategy/catalogue.yaml` that was read on 2026-10-30 maps to a playbook: PB-01/02
strangle, PB-02/03 straddle, PB-04 condor, PB-05 fly, PB-06 credit spreads, PB-07 debit spreads, PB-08 singles,
PB-09 long vol, PB-10 calendar/diagonal, PB-11 ratios, PB-12 directional flies/condors, PB-13 the rest. Imported real
positions that don't match a shape (Sensibull's "UN_KNOWN", C-01) get **generic triggers only** (T-01, T-04, T-06,
T-16) and the generic approaches (REQ-045 AC-5).

---

## Part 7 — Data needed (mapped to the adjustment data contract)

Rows the contract (30 values from the owner's video) already has are referenced by number; new ones are D-ids.

| ID | Data | Used by | In contract? | Source | Feasibility note |
|---|---|---|---|---|---|
| — | Spot, chain, LTP, per-leg delta, IV, distances, P&L, booked P&L, premium left, margin, lots, DTE, clock, fills, adjustment count, charges | most triggers and F-01..F-06 | rows 1-11, 14-19, 26-30 | existing | as in the contract |
| D-01 | Bid/ask and OI per strike | F-12 liquidity guard, F-04 spread cost | No | Kite quote/depth (already used for the chain) | pass (raw, live) |
| D-02 | NIFTY / SENSEX futures price and lot | A-20, F-10 | No | Kite feed | pass |
| D-03 | Next-expiry chain | A-03, A-04, A-14 rolls | Partly (row 2) | Kite feed | pass |
| D-04 | Previous close of the index | T-13 gap, F-14 | row 20 "unknown" | Kite quote `ohlc.close` — one value per day, not a history | likely pass (a single field, not stored history); confirm against REQ-047 AC-1 |
| D-05 | India VIX live | T-11, S-04 | No (owner: "later, not V1" Q246) | Kite feed (index token) | pass technically; owner said not V1 → `SPEC CHANGE` if wanted now |
| D-06 | Expected move (1 SD) | T-12 | No | derived: spot × ATM IV × √(days/365) | pass (derived) |
| D-07 | Event calendar (RBI, Budget, Fed, CPI, results) | F-09, T-17 | No | manual admin list (cheapest) or a licensed feed | pass if admin-maintained |
| D-08 | Position IV / Greeks snapshots since entry | F-13 attribution, F-18 | Partly (REQ-047 own history) | own snapshots | pass (own data) |
| D-09 | Broker square-off times, ELM %, freeze qty, lot size, expiry weekday | F-16, F-11 | row 19 "unknown" | exchange/broker published rules (Part 1) | pass as admin config, re-checked when rules change |

---

## Part 8 — What competitors offer

Sources: the local Sensibull study (`D:\Abhay\Ventures\competitors\sensibull\2026-10-21\`, cited by file and screen;
no images copied) and web pages opened or found on 2026-10-30. Web evidence for Indian products other than Sensibull
was thin, so several rows are UNVERIFIED.

| ID | Product | Adjustment-related feature | Evidence | What it means for us |
|---|---|---|---|---|
| C-01 | Sensibull | **Shift / Width / Hedge steppers**: move all strikes one step, widen the shorts, move the wings. Only for 16 recognised shapes | catalogue-raw.md screens 010-039, 108-110; bundle-findings.md §7.2 | Matches A-05/A-06 for the builder; we need the same on a *live* position, with Before/After |
| C-02 | Sensibull | What-if sliders (spot target, date) and per-leg IV edit / offset | catalogue-raw.md screen 020, 012, 122-123 | The builder already has this (B6/B7). We need it on the adjusted position (F-05) |
| C-03 | Sensibull | Include existing positions in margin; **Manual P&L** field so booked P&L from earlier adjustments can be typed into the payoff | catalogue-raw.md screens 241, 242 | Evidence that Sensibull has **no adjustment history**. F-06 lineage does this automatically, which is a clear edge |
| C-04 | Sensibull | Conditional Exit: exit everything when the index crosses a level (Zerodha ATO, NSE/BSE indices, max 20 trades); stop-loss orders per position | catalogue-raw.md "What's New" (Jun 2025); bundle-findings.md §7.4 | An exit only, not an adjustment. Not observed live |
| C-05 | Sensibull | Insights chip "No stop loss, unhedged" → suggests buying a lower put | catalogue-raw.md builder pass 2 | A nudge with no one-click build; our A-09 + F-02 goes further |
| C-06 | Sensibull | Adjusting a **real open** position was **not covered** by the study | catalogue-raw.md ~l.324; preset-matrix.md ~l.239 | Unknown, not proven absent. A 2023 Sensibull blog called a payoff of trades already taken "planned" |
| C-07 | AlgoTest | Trailing SL ("all legs" moves the other legs' SL to cost when one hits); leg-wise and overall re-entry (cost / ASAP / reverse); single-leg square-off | algotest.in blog pages | Matches A-32..A-34. Theirs is automatic (backtest/algo); ours would be suggest-only (or 5b later) |
| C-08 | Fyers, Kotak Neo | Re-entry / re-execute, "move SL to cost", strategy bot with overall SL and target | support.fyers.in; kotakneo.com support | Same idea as C-07 |
| C-09 | Zerodha Kite | GTT OCO (SL + target), trailing checkbox, baskets | Zerodha Z-Connect, support | Per instrument only. No strategy-level stop exists, so a strategy-level stop line (F-07) is a gap we can fill |
| C-10 | Dhan | Super Order / Super Trail (target + SL both trailing), multi-target split, "Cover your risk" nudge | dhan.co support | Per instrument |
| C-11 | Tradetron | Entry / **Repair** / Exit conditions, checked continuously (automatic) | app-store listing only | UNVERIFIED. The closest Indian product to "rule → adjustment", and it is automatic |
| C-12 | Opstra, Quantsapp, Stratzy | Nothing adjustment-specific found | — | UNVERIFIED (docs not reached) |
| C-13 | thinkorswim (US) | **Analyze tab**: add simulated trades on top of real positions; risk profile today vs expiry; shift the date; theoretical POP | toslc.thinkorswim.com Analyze | The model for F-02 + F-03 + F-05 |
| C-14 | OptionNet Explorer (US) | What-if adjustment with before/after (a reviewer's example cut delta 16.2 → 7.3); **cumulative P&L across adjustments**; copy a trade and test alternatives | reviews (not opened) | The model for F-03 + F-06 + F-19 |
| C-15 | Quantcha (US) | **Adjustment search**: finds the single change that moves the book toward a target (e.g. delta-neutral) within constraints, and adds it to the pending book in one click | docs.quantcha.com/?p=25858 | The only "find an adjustment for me" feature found; it is the model for F-10, extended. Wording must stay ADR-003 ("possible approaches") |

**Gaps where no Indian product clearly leads (opinion, thin evidence):**
1. Before/After of an adjustment on a **real open** multi-leg position (C-06, C-13). This is our core, F-02/F-03.
2. **Adjustment history**: booked P&L, adjustment count and credit collected carried through every adjustment (C-03, C-14). F-06.
3. **Strategy-level** stop line and target, not per instrument (C-09, C-10). F-07 plus T-06/T-07 on the whole strategy.
4. Trust in the payoff after an adjustment: TradingQnA users report Sensibull's payoff not matching their own P&L after
   adjusting a leg (tradingqna.com/t/.../92019; anecdotes). Our ADR-008 single engine and Zerodha-authority rule make
   this a visible strength if Before/After reconciles with fills.
5. "Why is this happening": P&L attribution (F-13) was found in no product.

---

## Part 9 — Suggested build order and open owner decisions

### 9a. Build order (prove the core first)

**Core:** turn a live strategy plus one chosen action (for example "A-01 roll the untested put to the tested call's
premium") into exact legs, and an After that the one engine (ADR-008) prices, using real chain data.
**Proof:** take one real paper strategy on a live NIFTY chain, run A-01, A-02 and A-09, and show the
Before/After numbers matching a hand check of the same legs in the builder.

| Step | What | Items | Depends on |
|---|---|---|---|
| 1 | **Core**: action → legs → Before/After, for the 8 most-used actions | A-01, A-02, A-04, A-05, A-06, A-09, A-28, A-31 + A-36 "no change"; F-02 | builder engine, chain (exist) |
| 2 | Cost and honesty on every Before/After | F-04 cost line, F-12 liquidity guard, M-15 low-OI warning, P-02 "as a fresh trade" view | 1 |
| 3 | The triggers experts use daily | T-03, T-05, T-06, T-07, T-09, T-10 (clock), T-18, T-19 on top of the built T-01/T-02 | rules engine (exists) |
| 4 | Draft playbooks as editable defaults | PB-01, PB-04, PB-06 first (most traded sellers), then the rest; F-07, F-08 | 1-3 + owner approval of the numbers |
| 5 | Lineage and journal | F-06, F-18 (on REQ-112) | 1 |
| 6 | Compare approaches and What-if on the After | F-03, F-05, F-19 | 1 |
| 7 | Time-of-day help | F-14 morning summary, F-15 carry check, F-16 expiry-day mode, F-09 event calendar (admin list) | 3 |
| 8 | Deeper analysis | F-10 delta helper, F-13 P&L attribution, remaining A-ids | 1, own snapshots |
| later | Backtest (F-22, needs a data licence); automatic 5b (needs SPEC CHANGE, legal Q211, M-22 research) | | |

### 9b. Owner decisions still open (business)

Asked one at a time, when the step that needs them comes up, not all now:
1. Approve the playbook numbers (Part 6), or name the ones to change. These are what users see by default.
2. India VIX (D-05): the owner said "later, not V1" (Q246). T-11 and S-04 are better with it. Is it a `SPEC CHANGE` now?
3. Event calendar (F-09): is an admin-maintained list acceptable for V1?
4. Should the intraday leg-stop playbook (PB-02) ship in suggest-only form, given the honest limit stated in PB-02?
5. Inverted strangle (A-10) and add-to-loser (A-30): show them with a warning, or hide them entirely?

### 9c. Technical calls made here (information, not questions)

- Playbook numbers are config data per playbook (editable rows), not code constants, so the owner and users can
  change them without a release.
- Market facts M-01..M-21 go into admin config with a "last checked" date, because three of them changed in the last
  12 months.
- Order sequencing (P-07) is enforced in the one basket-building path, which is a structural guarantee rather than a
  check run afterwards.
