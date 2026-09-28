# Indian Index Options Strategy Platform — Master Product Handoff
Version: 2026-09-15

## PURPOSE
Portable, model-agnostic handoff of the product-definition discussion. Upload this file to another ChatGPT session or another AI/model so it can continue without losing decisions, constraints, calculations, UX requirements, or unresolved questions.

CONTINUATION RULES
- Continue requirements clarification until >=95% confidence.
- Ask ONE question at a time.
- Every question must include the assistant's recommendation.
- Do not re-ask locked decisions.
- Do not jump to final architecture/build prompts until requirements are sufficiently complete.
- User is non-technical and prefers practical explanations and later copy-paste-ready prompts.

---

# 1. PRODUCT VISION

Public SaaS web platform for Indian index derivatives. Primary focus is making strategy-based option trading, especially option selling, easy for beginners and useful for intermediate/advanced users.

V1 underlyings:
- NIFTY
- SENSEX

V1 instruments:
- Call Buy
- Call Sell
- Put Buy
- Put Sell
- Futures Buy
- Futures Sell

V1 broker:
- ZERODHA ONLY.

The product is NOT a Zerodha/Kite clone or an unrestricted trading terminal.

Core philosophy:
> Plan the trade. Follow the strategy. Then execute.

Another core principle:
> You can change your strategy, but you cannot bypass the strategy.

Every trade executed through the platform belongs to a strategy. No unrestricted standalone orders.

Positioning:
> Your Zerodha account. Your strategy. Your decision. Our technology.

The product can help users avoid impulsive/unplanned decisions by enforcing strategy context, risk visibility, predefined conditions, and controlled execution. Do not promise guaranteed returns or that losses will always be reduced.

---

# 2. TARGET USERS AND UX LEVELS

Primary:
- Beginners/newer options users
- Intermediate traders

Advanced users are supported.

Principle:
> Simple on the surface, sophisticated underneath.

Three UX levels:
1. Guided
   - plain language
   - education
   - strong risk visibility
   - guided decisions
   - hide unnecessary Greeks by default
2. Standard
   - more control
   - Greeks
   - payoff
   - conditions
   - adjustments
3. Advanced
   - full strategy controls
   - detailed Greeks/IV/expected move
   - advanced conditions
   - detailed execution controls

Users can switch levels at any time.

Advanced mode cannot bypass strategy-only trading, safety controls, margin checks, or broker restrictions.

---

# 3. CORE DOMAIN MODEL

Central object = STRATEGY, not ORDER.

Strategy
-> Legs
-> Entry conditions
-> Risk
-> Adjustments
-> Exit plan
-> Execution plan
-> Orders
-> Monitoring
-> Completion

Execution:
Strategy
-> Execution Plan
-> Leg Dependencies
-> Execution Sequence
-> Orders

---

# 4. HOME

Action-first, not terminal-first.

Primary actions:
- Create a Strategy
- My Strategies
- Alerts
- Market
- Learn

Small live market strip may be shown.

Product should feel like a strategy operating system, not Bloomberg/Kite.

---

# 5. STRATEGY CREATION

Locked:
- Strategy-first + Manual Builder.
- Strategy-first is default.
- Manual Builder for experienced users.
- Guided/conversational structured builder plus Advanced Manual Builder.

Guided flow:
1. What are you trying to achieve?
2. Market/view/risk/capital
3. Strategies to consider
4. Configure
5. Show max profit, max loss, breakevens, margin, charges, payoff, risk
6. Entry/exit/adjustment conditions
7. Review
8. Prepare/execute

Desired outcomes:
- Earn premium
- Limit risk
- Benefit if market rises
- Benefit if market falls
- Trade a big move
- I already know my strategy

Experienced users can choose known strategy directly.

---

# 6. STRATEGY DISCOVERY

Guided strategy discovery is allowed.

System can surface strategies to evaluate based on intent.

Use wording such as:
> Strategies you could consider

Not:
> This is the trade you should take.

V1 is NOT an AI investment-advisory chatbot and should not directly recommend trades.

---

# 7. STRATEGY ENGINE

Support generic combinations of:
- Call Buy
- Call Sell
- Put Buy
- Put Sell
- Futures Buy
- Futures Sell

Unlimited multi-leg combinations.

Use templates for common strategies but do not build dozens of separate hard-coded strategy engines.

---

# 8. BROKER

V1 = Zerodha only.

Do not build Angel One, Upstox, Dhan, Groww, or Paytm Money in V1.

Internal broker abstraction may exist only if it does not complicate V1.

Each user connects their own Zerodha account. Strategies belong to that user's connected account.

---

# 9. ACCOUNT BOUNDARIES

Locked:
- own Zerodha account only
- no managing other accounts
- no pooled money
- no copy trading
- no discretionary management
- no shared broker credentials

---

# 10. STRATEGY-ONLY EXECUTION

Locked:
Every trade placed through the platform must belong to a strategy.

No unrestricted individual orders.

Messaging:
> Every trade follows a strategy. No impulsive standalone orders.

> You can change your strategy, but you cannot bypass the strategy.

---

# 11. CONTROLLED STRATEGY MODIFICATION

Users can modify live strategies but cannot modify a leg as a standalone trade.

Flow:
Modify Strategy
-> proposed leg changes
-> recalculate max profit/loss, breakevens, current P&L, margin, charges, risk
-> Before/After comparison
-> prepare adjustment orders
-> user confirms
-> execute

---

# 12. AUTOMATION

V1:
## Alert + Prepare Orders

Condition met:
-> alert
-> prepare exact multi-leg orders
-> user reviews
-> user executes

Architecture should allow future controlled automation.

No unrestricted autonomous trading in V1.

---

# 13. ENTRY CONDITIONS

V1 simple conditions:
- immediate
- market reaches level/range
- premium target
- volatility condition
- time window

Advanced compound rule builder later.

Same rule-engine concept should power entry, adjustment, exit, and future automation.

---

# 14. EXIT

V1:
- Profit target
- Max loss
- Time exit
- Underlying level

Action:
- alert
- prepare exit orders

Every strategy has explicit exit plan.

---

# 15. STRIKE SELECTION

Choices:
- Conservative
- Balanced
- Aggressive
- Manual Custom

Suggestions may use:
- spot
- expiry
- premiums
- IV
- expected move
- capital
- max loss
- desired premium

Call it a "Suggested setup", not a "Recommended trade".

Manual override required.

---

# 16. HISTORICAL SIMULATION

V1 simple historical strategy simulation, not full quant backtesting.

Possible metrics:
- best/worst outcome
- winning days
- drawdown
- historical behavior

Clearly label as simulation/historical behavior, not future guarantee.

---

# 17. MARKET DATA

Preferred architecture:
Centralized licensed market-data provider + Zerodha APIs for account/order/execution.

Central market-data engine feeds website, option chain, strategy engine and alerts.

Zerodha handles authentication, account, positions, orders and execution.

Do not scrape NSE.

Zerodha should be the authority for current contract/order eligibility wherever possible.

---

# 18. ZERODHA CONTRACT/ORDER ELIGIBILITY

Do not recreate all Zerodha RMS/risk rules.

Distinguish:
1. Contract catalogue = what exists
2. Current eligibility = what Zerodha currently permits

Strategy builder should avoid currently unplaceable contracts where Zerodha information permits.

Do not permanently delete contracts because availability can change.

At execution:
## Zerodha is final authority.

There may not be one universal Zerodha API endpoint saying whether every order is allowed. Therefore use:
- instrument master
- available pre-checks/data
- broker response as final authority
- no attempt to replicate full RMS

---

# 19. ZERODHA ORDER RESTRICTIONS

Previously researched:
- options are not universally limit-only
- market orders are restricted for certain option contracts based on liquidity/OI/expiry/deep ITM etc.
- SL-M is not allowed for index option derivatives
- theoretical-price/freak-trade protections can reject orders
- fresh F&O orders can be blocked by OI restrictions
- some NIFTY/SENSEX strikes can be restricted
- Zerodha option chain has expiry, strikes, OI, Greeks, market depth
- Zerodha supports basket execution

Do not hard-code generic assumptions like "options = limit only".

Final execution authority is Zerodha.

---

# 20. MARGIN

Before orders:
1. Fetch available margin/funds from Zerodha.
2. Calculate/obtain required margin for the execution sequence.
3. Verify enough margin.
4. Submit only if sufficient.

After each fill:
- re-fetch broker state
- re-check margin
- continue only when dependency conditions are satisfied

Our margin estimate is planning information. Zerodha is authority.

If insufficient:
- stop
- show available vs required
- offer quantity modification/add funds/review

---

# 21. MULTI-LEG EXECUTION

Protective/buy legs can establish protection and margin benefit before dependent shorts.

Preferred:
## protective/buy legs first, then dependent sell legs.

Do not hard-code "all buys first" universally. Execution engine should understand dependencies and margin impact.

User gets one:
> Execute Strategy

button.

If protective leg fails, dependent sell should not be submitted.

---

# 22. PARTIAL FAILURE

If 4-leg strategy has 3 filled and 1 failed:

Priority:
1. Complete Strategy
2. Retry Failed Leg
3. Review Manually
4. Close Partial Strategy

Do not automatically unwind successful legs.

Before completion:
- re-fetch Zerodha positions
- re-fetch order status
- recalculate remaining strategy
- re-check margin
- verify missing leg
- submit only required order(s)

Principles:
> Never unnecessarily undo a successfully executed strategy leg. First try to complete the user's intended strategy.

> Never assume strategy is complete merely because orders were submitted. Confirm actual broker execution.

---

# 23. EXISTING POSITIONS

On Zerodha connection:
- fetch open positions
- identify possible multi-leg structures

User choices:
- add to existing strategy
- create new strategy
- leave standalone

Once grouped, monitor them.

---

# 24. LIVE MONITORING

Monitor:
- P&L
- underlying
- distance from breakevens
- distance from short strikes
- time to expiry
- IV changes
- Greeks
- margin utilization
- entry/adjustment/exit conditions

Translate into:
- Green = Healthy
- Yellow = Watch
- Orange = Adjustment opportunity
- Red = Exit condition reached

Avoid predictive monitoring in V1.

Potential UX:
> What should I do now?

---

# 25. INFORMATION DENSITY

Default:
- strategy status
- P&L
- target
- risk
- current underlying
- range/condition
- next thing to watch

Drill-down:
- Overview
- P&L
- Risk
- Payoff
- Legs
- Greeks
- Conditions
- Orders

Advanced exposes terminal-like detail.

---

# 26. NOTIFICATIONS

Locked:
## In-app + Push + Email + WhatsApp in V1

Priority:
- Info -> in-app
- Watch -> in-app + push
- Action opportunity -> push + in-app + possibly WhatsApp
- Exit/risk/order failure -> push + email + WhatsApp + in-app

Avoid alert fatigue.

WhatsApp opt-in/provider/compliance details remain to be defined.

---

# 27. DEVICE

Responsive web from Day 1.

Desktop:
- strategy construction
- option chain
- analysis
- wide tables
- payoff visualization

Mobile:
- alerts
- monitoring
- P&L
- review
- execution

No native mobile app initially.

---

# 28. CALCULATION ENGINE

Dedicated strategy/risk engine.

One engine powers:
- builder
- order preview
- live strategy
- adjustment simulator
- exit

Understands:
- underlying
- expiry
- contract
- legs
- quantity
- premium
- Greeks
- payoff
- margin
- charges
- current market value
- strategy P&L

Can use established libraries/formulas for Black-Scholes, Greeks and IV, but domain logic belongs to the product.

Avoid false precision.

---

# 29. CORE STRATEGY OUTCOME VIEW

Every user should see a strategy outcome view, including beginners.

Purpose:
> Let users see what can happen to their money at different market levels.

Example current NIFTY = 23,000.

Scenario levels:
22,000, 22,100, ..., 22,900, 23,000 CURRENT, 23,100, ..., 24,000.

Default gap = ₹100.

Payoff graph and scenario table must use the same calculation engine.

---

# 30. SINGLE TABLE — LOCKED

The user explicitly wants ONE horizontally scrollable table.

Column order:

1. Leg
2. Action
3. Instrument
4. Expiry
5. Strike
6. Quantity
7. Entry Price
8. LTP
9. Entry Value
10. Current Value
11. Unrealized P&L
12. P&L %
13. IV
14. Delta
15. Gamma
16. Theta
17. Vega
18+. Market-level scenario columns
Then:
- Lower Breakeven
- Upper Breakeven
- Status

Market-level columns come immediately after Vega.

Example:
22,000 | 22,100 | ... | 22,900 | 23,000 CURRENT | 23,100 | ... | 24,000

Table remains one table, not two.

Recommended UX:
- sticky/frozen left-side columns
- horizontal scrolling
- current market level visually highlighted

---

# 31. SCENARIO CELL CALCULATIONS — LOCKED

Every market-level cell must be populated for every leg.

Do NOT leave blanks.

Expiry P&L formulas:

BUY CALL:
[MAX(Market - Strike, 0) - Entry Price] * Quantity

SELL CALL:
[Entry Price - MAX(Market - Strike, 0)] * Quantity

BUY PUT:
[MAX(Strike - Market, 0) - Entry Price] * Quantity

SELL PUT:
[Entry Price - MAX(Strike - Market, 0)] * Quantity

Strategy scenario P&L = sum of all leg scenario P&Ls.

Current LTP is NOT used for expiry scenario payoff.
Entry premium is used.

Current LTP is used for live/current P&L.

Breakevens are strategy-level properties. Individual legs do not need breakeven values.

---

# 32. IRON CONDOR EXAMPLE

Leg 1:
BUY NIFTY PE, strike 22,800, entry ₹42.50, qty 75, LTP ₹38.20

Leg 2:
SELL NIFTY PE, strike 23,000, entry ₹86.00, qty 75, LTP ₹72.50

Leg 3:
SELL NIFTY CE, strike 23,400, entry ₹91.50, qty 75, LTP ₹78.00

Leg 4:
BUY NIFTY CE, strike 23,600, entry ₹44.00, qty 75, LTP ₹39.50

Live illustrative P&L:
- Leg 1: -₹322.50
- Leg 2: +₹1,012.50
- Leg 3: +₹1,012.50
- Leg 4: -₹337.50
- Strategy current P&L: +₹1,365

Net credit:
86 + 91.50 - 42.50 - 44 = ₹91/unit
x 75 = ₹6,825

Max profit = ₹6,825
Max loss = ₹8,175
Approximate lower BE = 23,000 - 91 = 22,909
Approximate upper BE = 23,400 + 91 = 23,491

Production engine must calculate dynamically.

---

# 33. SCENARIO EXAMPLE

Leg 1 BUY 22,800 PE @ 42.50 x 75:
22,000 = +₹56,812.50
22,100 = +₹49,312.50
22,200 = +₹41,812.50
22,300 = +₹34,312.50
22,400 = +₹26,812.50
22,500 = +₹19,312.50
22,600 = +₹11,812.50
22,700 = +₹4,312.50
22,800 = -₹3,187.50
22,900 and above = -₹3,187.50

Leg 2 SELL 23,000 PE @ 86 x 75:
22,000 = -₹68,550
22,100 = -₹61,050
22,200 = -₹53,550
22,300 = -₹46,050
22,400 = -₹38,550
22,500 = -₹31,050
22,600 = -₹23,550
22,700 = -₹16,050
22,800 = -₹8,550
22,900 = -₹1,050
23,000 and above = +₹6,450

Leg 3 SELL 23,400 CE @ 91.50 x 75:
22,000 through 23,400 = +₹6,862.50
23,500 = -₹637.50
23,600 = -₹8,137.50
23,700 = -₹15,637.50
23,800 = -₹23,137.50
23,900 = -₹30,637.50
24,000 = -₹38,137.50

Leg 4 BUY 23,600 CE @ 44 x 75:
22,000 through 23,600 = -₹3,300
23,700 = +₹4,200
23,800 = +₹11,700
23,900 = +₹19,200
24,000 = +₹26,700

Strategy total:
22,000 to 22,800 = -₹8,175
22,900 = -₹675
23,000 to 23,400 = +₹6,825
23,500 = -₹675
23,600 to 24,000 = -₹8,175

---

# 34. LIVE PRICING

First-class columns:
- Entry Price
- LTP

Also:
- Entry Value
- Current Value
- Unrealized P&L
- P&L %

These update live.

Bid/Ask may be Advanced Details rather than default.

---

# 35. GREEKS

Columns:
- IV
- Delta
- Gamma
- Theta
- Vega

These occur after P&L % and immediately before market-level scenario columns.

---

# 36. RISK ACKNOWLEDGEMENT

Avoid repetitive generic "I understand the risks" checkboxes.

Use contextual risk UX:
- normal -> explain
- elevated -> warn
- exceptional -> explicit acknowledgement

Execution review should show:
- strategy
- margin
- max loss
- max profit
- current P&L
- leg count
- execution sequence
- broker

---

# 37. REMAINING QUESTIONS

Not yet locked:
1. Scenario columns: expiry P&L vs estimated current P&L vs both.
2. Scenario range: fixed ±1,000, ±2,000, intelligent, custom.
3. Scenario level anchoring: exact spot vs rounded ₹100 center.
4. Option-chain role: primary workflow vs builder tool.
5. Direct leg selection from option chain.
6. Quantity/lot-size UX and lot-size changes.
7. Zerodha product type such as MIS/NRML.
8. Execution pricing / limit-order handling.
9. Partial-fill behavior in detail.
10. Zerodha connection/authentication UX.
11. Existing-position grouping UX.
12. Notification configuration and WhatsApp opt-in/provider.
13. Strategy lifecycle/status model.
14. Historical simulation detail.
15. Margin/risk presentation detail.
16. Compliance boundaries.
17. Pricing/business model.
18. Admin/operations.
19. Security/audit/data retention.
20. Final technical architecture/stack.

Ask only one question at a time.

---

# 38. MOST RECENT UNANSWERED QUESTION

Question 33A:

What should market-level scenario P&L represent?

A. Expiry P&L only
B. Estimated current P&L only
C. Both, with Expiry P&L as default

Assistant recommendation:
C — Both, with Expiry P&L as default.

Reason:
- expiry payoff is deterministic
- current estimate is useful for active management
- current estimate requires time/IV/pricing assumptions

---

# 39. NEXT-AI BEHAVIOR

Treat LOCKED decisions as already decided.

Do not re-open them.

Ask one question at a time.

Give a recommendation with each question.

When requirements reach >=95% confidence:
- produce final PRD
- produce architecture recommendation
- produce data model
- produce UX flows
- produce execution-state model
- research current Zerodha/SEBI/NSE/BSE/API requirements
- then create implementation prompts for the user's preferred coding tools.

If current/fresh factual claims about Zerodha, SEBI, APIs, market data, or regulations are needed, use current authoritative web sources before making the claim.

END OF HANDOFF
