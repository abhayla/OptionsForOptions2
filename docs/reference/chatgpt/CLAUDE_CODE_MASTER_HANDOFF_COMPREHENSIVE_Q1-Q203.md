# Indian Index Options / F&O SaaS Platform --- COMPREHENSIVE MASTER HANDOFF FOR CLAUDE CODE

Version: 2026-09-28 Coverage: Product decisions and implementation
constraints finalized through Q203 Purpose: Single source of truth for
Claude Code implementation

------------------------------------------------------------------------

## 0. HOW TO USE THIS FILE

This is the implementation handoff for the project.

It consolidates: 1. The original Master Product Handoff. 2. The later
Latest Handoff. 3. The finalized product/architecture decisions carried
forward through Q203 in the continuing product-design discussion.

Important: - This document is an implementation handoff, not a request
to reopen product discovery. - Locked decisions must not be silently
changed. - If implementation reveals a genuine contradiction or a
missing business/product decision, stop at that boundary and surface it
clearly. - Do not invent product decisions. - Do not replace a locked
product decision with a technically convenient alternative. -
Current/fresh facts about Zerodha, SEBI, exchange rules, APIs,
licensing, or vendors must be verified from authoritative current
sources before being encoded as facts. - Production deployment always
requires explicit owner authorization.

The product-design phase has reached Q203. Implementation starts now.
Next product question, if needed later, is Q204.

------------------------------------------------------------------------

# 1. PRODUCT VISION

Public SaaS web platform for Indian index derivatives/F&O.

V1 underlyings: - NIFTY - SENSEX

V1 broker: - Zerodha only.

V1 supported instruments/legs: - Call Buy - Call Sell - Put Buy - Put
Sell - Futures Buy - Futures Sell

Core promise:

> Plan the trade. Follow the strategy. Then execute.

Core principle:

> You can change your strategy, but you cannot bypass the strategy.

Positioning:

> Your Zerodha account. Your strategy. Your decision. Our technology.

The product is NOT: - a Zerodha/Kite clone - an unrestricted trading
terminal - an unrestricted standalone-order interface - an AI
investment-advisory chatbot - an autonomous unrestricted trading bot

Every trade executed through the platform belongs to a strategy.

------------------------------------------------------------------------

# 2. PRODUCT PHILOSOPHY

The product should help users structure decisions before execution: -
strategy context - risk visibility - P&L visibility - predefined
conditions - controlled execution - monitoring - auditable changes

Do not promise: - guaranteed returns - guaranteed loss reduction -
guaranteed profitability - certainty about future market movement

Preferred language: - Strategies you could consider - Suggested setup -
Adjustment opportunity detected - Possible adjustment - Review
adjustment - Your rule was triggered

Avoid: - You should take this trade - Best trade - Guaranteed -
Risk-free - Certain profit

Personalized adjustment logic may require legal/SEBI review. Keep the
product positioned as decision-support and strategy tooling, not
individualized investment advice.

------------------------------------------------------------------------

# 3. TARGET USERS AND UX LEVELS

Primary users: - Beginners/newer options users - Intermediate traders

Advanced users are supported.

Principle:

> Simple on the surface, sophisticated underneath.

Three UX levels:

### Guided

-   Plain language
-   Education
-   Strong risk visibility
-   Guided decisions
-   Hide unnecessary Greeks by default

### Standard

-   More control
-   Greeks
-   Payoff
-   Conditions
-   Adjustments

### Advanced

-   Full strategy controls
-   Detailed Greeks/IV/expected move
-   Advanced conditions
-   Detailed execution controls

Users can switch levels at any time.

Advanced mode cannot bypass: - strategy-only trading - safety controls -
margin checks - broker restrictions - reconciliation blocks

------------------------------------------------------------------------

# 4. PRODUCT SHAPE

The product should feel like a strategy operating system, not
Bloomberg/Kite.

Home/dashboard is action-first, not terminal-first.

Primary actions: - Create a Strategy - My Strategies - Alerts - Market -
Learn

A small live market strip may be shown.

Responsive web from Day 1: - Desktop: strategy construction, Option
Chain, analysis, wide tables, payoff - Mobile: alerts, monitoring, P&L,
review, execution - No native mobile app initially

------------------------------------------------------------------------

# 5. CORE DOMAIN PRINCIPLE

Central domain object:

> STRATEGY, not ORDER.

Conceptual model:

Strategy → Legs → Entry Conditions → Risk → Adjustment Plan → Exit Plan
→ Execution Plan → Orders → Monitoring → Completion

Execution:

Strategy → Execution Plan → Leg Dependencies → Execution Sequence →
Orders

Orders are execution artifacts belonging to a strategy.

------------------------------------------------------------------------

# 6. STRATEGY CREATION

Strategy-first + Manual Builder is locked.

Default: - Strategy-first

For experienced users: - Advanced Manual Builder

Guided/conversational structured builder plus Advanced Manual Builder.

Guided flow:

1.  What are you trying to achieve?
2.  Market/view/risk/capital
3.  Strategies to consider
4.  Configure
5.  Show:
    -   max profit
    -   max loss
    -   breakevens
    -   margin
    -   charges
    -   payoff
    -   risk
6.  Entry/exit/adjustment conditions
7.  Review
8.  Prepare/execute

Objectives: - Earn premium - Limit risk - Benefit if market rises -
Benefit if market falls - Trade a big move - I already know my strategy

Experienced users can directly choose a known strategy.

------------------------------------------------------------------------

# 7. STRATEGY ENGINE

Use a generic strategy engine.

Supported leg types: - Call Buy - Call Sell - Put Buy - Put Sell -
Futures Buy - Futures Sell

The engine must support unlimited combinations.

Common strategy templates sit above the generic engine.

Do NOT build dozens of hard-coded strategy engines.

The strategy engine should be capable of representing: - custom
combinations - multi-leg strategies - multi-expiry strategies - strategy
modifications - adjustment proposals - exits - execution plans

------------------------------------------------------------------------

# 8. STRATEGY DISCOVERY

Guided strategy discovery is allowed.

The system may surface strategies to evaluate based on: - objective -
market view - risk preference - capital - expected range - selected
constraints

Use: \> Strategies you could consider

Not: \> This is the trade you should take.

V1 is not an AI investment-advisory chatbot.

------------------------------------------------------------------------

# 9. STRATEGY-ONLY EXECUTION

Locked:

Every trade placed through the platform must belong to a strategy.

No unrestricted individual orders.

The product should reinforce:

> Every trade follows a strategy. No impulsive standalone orders.

and:

> You can change your strategy, but you cannot bypass the strategy.

This constraint applies to all UX levels.

------------------------------------------------------------------------

# 10. STRATEGY MODIFICATION

Users may modify a live strategy.

They may not treat a leg as an unrelated standalone trade.

Flow:

Modify Strategy → Proposed leg changes → Recalculate: - max
profit/loss - breakevens - current P&L - margin - charges - risk →
Before/After comparison → Prepare adjustment orders → User confirms →
Execute

Strategy versions must be preserved.

------------------------------------------------------------------------

# 11. STRATEGY DEFINITION VS LIVE MARKET STATE

This is a critical domain boundary.

## Strategy Definition

Relatively stable/immutable versioned information: - underlying -
expiry - legs - strikes - Buy/Sell - quantities - entry rules -
adjustment rules - exit rules - risk limits - user
preferences/constraints

## Live Market State

Continuously changing information: - spot - futures - LTP - bid/ask -
volume - OI - OI change - IV - Greeks - current P&L - margin - charges -
distances - trigger state - timestamps - data health

Do not mix these into one mutable object.

Preserve strategy versions.

------------------------------------------------------------------------

# 12. ACTIVE VS PROPOSED STRATEGY VERSION

A proposed strategy version is not active merely because it was
calculated.

Rules: - Active version is the currently accepted strategy state. -
Proposed version is separate. - Proposed version becomes active only
after user confirmation and successful execution/reconciliation. -
Partial execution creates an explicit exception/reconciliation state. -
Broker actual state wins when actual execution differs from intended
state.

------------------------------------------------------------------------

# 13. AUTOMATION

V1 automation model:

> Alert + Prepare Orders

When a condition is met: → alert → prepare exact multi-leg orders → user
reviews → user executes

No unrestricted autonomous trading in V1.

Architecture should permit controlled future automation without
redesigning the domain.

------------------------------------------------------------------------

# 14. RULE ENGINE

Use one reusable rule-engine concept for: - entry - adjustment - exit -
future controlled automation

V1 entry conditions: - immediate - market reaches level/range - premium
target - volatility condition - time window

The engine should later support compound conditions such as AND/OR.

Example trigger inputs: - underlying level - underlying movement -
distance from strike - distance from breakeven - premium - P&L - DTE -
IV - IV percentile - Greeks - strategy-level thresholds

------------------------------------------------------------------------

# 15. EXIT

Exit conditions: - profit target - max loss - time exit - underlying
level

Action: - alert - prepare exit orders

Important later clarification: Exit and adjustment plans are optional at
strategy-definition level. The platform must support strategies without
predefined exit/adjustment rules while still allowing monitoring and
opportunity detection.

------------------------------------------------------------------------

# 16. STRIKE SELECTION

Modes: - Conservative - Balanced - Aggressive - Manual Custom

Potential inputs: - spot - expiry - premiums - IV - expected move -
capital - max loss - desired premium

Use:

> Suggested setup

not:

> Recommended trade

Manual override remains available.

------------------------------------------------------------------------

# 17. EXPIRY RANGE INPUT / MARKET OUTLOOK

When the user says they are not sure about market outlook, the product
can ask for expected market expiry level/range for a selected timeframe,
for example: - this month end - this weekend by selected expiry -
upcoming expiry - monthly expiry - next monthly expiry

User selects: - lower expected market level - higher expected market
level

Range pick lists: - based around current market price - 100-point
increments - lower list contains current and below - upper list contains
current and above - lower cannot exceed current - upper cannot be below
current

The selected range can be used by the strategy-selection/risk engine to
identify strategies and risk characteristics.

Ask additional questions only where required data cannot be inferred.

------------------------------------------------------------------------

# 18. USER STRATEGY PREFERENCES

User can specify preferred strategy types.

Example: - prefers Iron Condor - prefers Iron Condor + Short Call

The product should use preferences to surface currently valid strategies
matching: - user preference - selected market range - current market
conditions - other constraints

Do not silently force a strategy.

------------------------------------------------------------------------

# 19. OPTION CHAIN --- Q43--Q57

These decisions are locked.

### Q43

Same contract with opposite actions remains separate strategy legs.

No auto-netting.

### Q44

Unavailable contract: - remains visible - valid alternatives may be
suggested - user explicitly chooses - no silent substitution

### Q45

Clean default + Advanced Details.

Default: - Strike - LTP - Change - IV - OI - Volume

Advanced: - Bid/Ask - Delta - Gamma - Theta - Vega - OI Change - other
advanced fields

### Q46

Hybrid live-data architecture: - LTP/bid/ask streaming - OI/IV
lower-frequency

### Q47

Persistent Selected Legs summary while scrolling.

Add to Strategy.

### Q48

Duplicate contract: ask whether to: - increase quantity - keep
separate - cancel

### Q49

Validate before import. - Block serious errors. - Warn on legitimate
cases such as mixed expiries.

### Q50

Selections persist across expiry tabs.

Multi-expiry strategies are supported.

### Q51

Identify matching strategy templates but never auto-convert or
auto-execute.

### Q52

Unmatched combinations are allowed as Custom Strategy.

### Q53

Explicit Buy/Sell per contract.

Never infer action.

### Q54

+/- lot stepper using broker-valid lot size. Exact quantity available in
Advanced.

### Q55

Compact live Strategy Preview: - net premium - max profit/loss -
breakevens - mini payoff

Full scenario table in Builder.

### Q56

Immediate remove + short Undo.

### Q57

Adjustment rules: - global defaults - per-strategy overrides

------------------------------------------------------------------------

# 20. OPTION CHAIN ROLE

Option Chain is both: - a market exploration tool - a
strategy-construction tool

Users can select legs from the chain and add them to a strategy.

It must not become an unrestricted order-entry surface.

------------------------------------------------------------------------

# 21. P&L / PAYOFF / SCENARIO ENGINE

Dedicated calculation engine.

One engine should power: - builder - order preview - live strategy -
adjustment simulator - exit analysis - payoff graph - scenario table

Inputs may include: - underlying - expiry - contract - legs - quantity -
premium - LTP - Greeks - IV - margin - charges - current market value

Established libraries/formulas may be used for Black-Scholes, IV,
Greeks, etc., but product-domain logic belongs in the platform.

Avoid false precision.

------------------------------------------------------------------------

# 22. STRATEGY OUTCOME VIEW

Every user, including beginners, should see an outcome view.

Purpose:

> Let users see what can happen to their money at different market
> levels.

Scenario table and payoff graph must use the same calculation engine.

Default scenario levels: - centered around current underlying -
100-point increments for NIFTY-style examples - approximately
1,000--2,000 points of useful range where appropriate - current level
visibly highlighted

------------------------------------------------------------------------

# 23. SINGLE TABLE --- LOCKED

One horizontally scrollable table.

Column order:

1.  Leg
2.  Action
3.  Instrument
4.  Expiry
5.  Strike
6.  Quantity
7.  Entry Price
8.  LTP
9.  Entry Value
10. Current Value
11. Unrealized P&L
12. P&L %
13. IV
14. Delta
15. Gamma
16. Theta
17. Vega 18+. Market-level scenario columns Then:

-   Lower Breakeven
-   Upper Breakeven
-   Status

Market-level columns come immediately after Vega.

UX: - sticky/frozen left columns - horizontal scrolling - current market
level highlighted

One table, not two.

------------------------------------------------------------------------

# 24. SCENARIO CELL CALCULATIONS --- LOCKED

Every market-level cell is populated for every leg.

No blanks.

Expiry formulas:

BUY CALL: \[MAX(Market - Strike, 0) - Entry Price\] × Quantity

SELL CALL: \[Entry Price - MAX(Market - Strike, 0)\] × Quantity

BUY PUT: \[MAX(Strike - Market, 0) - Entry Price\] × Quantity

SELL PUT: \[Entry Price - MAX(Strike - Market, 0)\] × Quantity

Strategy scenario P&L = sum of all leg scenario P&Ls.

Current LTP is NOT used for expiry scenario payoff.

Entry premium is used.

Current LTP is used for live/current P&L.

Breakevens are strategy-level properties.

Individual legs do not need breakeven values.

------------------------------------------------------------------------

# 25. IRON CONDOR REFERENCE CALCULATION

Illustrative strategy:

-   Buy 22,800 PE @ 42.50 × 75; LTP 38.20
-   Sell 23,000 PE @ 86 × 75; LTP 72.50
-   Sell 23,400 CE @ 91.50 × 75; LTP 78
-   Buy 23,600 CE @ 44 × 75; LTP 39.50

Live illustrative P&L: - Leg 1: -₹322.50 - Leg 2: +₹1,012.50 - Leg 3:
+₹1,012.50 - Leg 4: -₹337.50 - Strategy current P&L: +₹1,365

Net credit: ₹91/unit × 75 = ₹6,825

Max profit: ₹6,825

Max loss: ₹8,175

Approximate lower BE: 22,909

Approximate upper BE: 23,491

Scenario: - 22,000--22,800 = -₹8,175 - 22,900 = -₹675 - 23,000--23,400 =
+₹6,825 - 23,500 = -₹675 - 23,600--24,000 = -₹8,175

Production calculations must be dynamic, not hard-coded.

------------------------------------------------------------------------

# 26. LIVE PRICING

First-class fields: - Entry Price - LTP - Entry Value - Current Value -
Unrealized P&L - P&L %

These update live.

Bid/Ask can remain Advanced Details.

------------------------------------------------------------------------

# 27. GREEKS

Default strategy table fields: - IV - Delta - Gamma - Theta - Vega

These occur after P&L % and immediately before market-level scenario
columns.

Platform should calculate Greeks independently where feasible.

Vendor Greeks may be reference/comparison data.

------------------------------------------------------------------------

# 28. RISK UX

Avoid repetitive generic: "I understand the risks."

Use contextual risk UX: - Normal → explain - Elevated → warn -
Exceptional → explicit acknowledgement

Execution review should show: - strategy - margin - max loss - max
profit - current P&L - leg count - execution sequence - broker

------------------------------------------------------------------------

# 29. LIVE MONITORING

Monitor: - P&L - underlying - distance from breakevens - distance from
short strikes - DTE - IV - Greeks - margin utilization - entry
conditions - adjustment conditions - exit conditions - market-data
health

Statuses: - Green --- Healthy - Yellow --- Watch - Orange --- Adjustment
opportunity - Red --- Exit condition reached

V1 monitoring is rule-based, not predictive.

------------------------------------------------------------------------

# 30. POSITIONS ARE STRATEGY/RISK OBJECTS

A position is not merely a broker positions-table row.

Model:

Strategy + Current Market + Time + P&L + Greeks + Position Geometry +
User Rules → Trigger → Candidate Adjustment → Before/After Analysis →
User Decision

------------------------------------------------------------------------

# 31. ADJUSTMENT ENGINE

WHEN examples: - underlying moves X points - underlying reaches a
level - distance from short strike - distance from breakeven - leg
reaches profit threshold - strategy reaches max-profit threshold -
strategy reaches max-loss threshold - Greek threshold - IV change - IV
percentile - DTE - premium - P&L - compound AND/OR

DO examples: - take profit - close leg - roll leg - roll spread - move
strike - add hedge/leg - remove hedge/leg - change quantity -
re-center - convert strategy - exit - alert - no-trade proposal

The platform does not claim that one adjustment is universally correct.

Adjustments can increase risk.

------------------------------------------------------------------------

# 32. ADJUSTMENT OPPORTUNITIES WITHOUT USER RULES

The platform should still monitor and identify potential adjustment
opportunities even if the user has not predefined an adjustment rule.

Important distinction: - user-defined rule trigger - platform-detected
risk/attention area

Do not present a generic detection as a personalized instruction.

------------------------------------------------------------------------

# 33. ADJUSTMENT OPPORTUNITY UI --- LOCKED STRUCTURE

Use four layers:

### Layer 1 --- Why detected

Show: - exact market condition - relevant strike/breakeven - current
distance - trigger metric - rule/condition where applicable

### Layer 2 --- Current strategy state

Show: - P&L - max profit/loss - breakevens - net Delta - Gamma - Theta -
Vega - margin utilization - DTE - relevant option IV/OI/LTP

### Layer 3 --- Possible approaches

Show generic approaches with brief explanation.

No automatic recommendation.

### Layer 4 --- Next step

User selects an approach.

Platform then: - builds/analyzes proposed configuration - calculates
Before/After - shows P&L - risk - margin - Greeks - breakevens - payoff

User decides.

"Why am I seeing this?" must explain the detection.

------------------------------------------------------------------------

# 34. ADJUSTMENT DATA REQUIREMENTS

Adjustment engine can use: - individual-leg data - strategy-level
aggregated data - underlying-level data independently of option data

Data layer must be extensible.

New metrics must be addable without redesign.

Collect adjustment-relevant data even when users have no adjustment
rules because the platform can detect opportunities.

------------------------------------------------------------------------

# 35. DATA FEASIBILITY TEST

Every metric must pass:

1.  Raw data?
2.  Source?
3.  Can platform calculate it?
4.  Scale impact?
5.  Historical availability?
6.  Legal/licensing?
7.  Update frequency?
8.  Storage requirement?
9.  Calculation method?

Prefer: \> raw data first, derive metrics ourselves where practical

Do not buy every derived metric unnecessarily.

------------------------------------------------------------------------

# 36. HISTORICAL MARKET-DATA STORAGE TIERS

Do NOT store complete tick-by-tick history for every option contract.

Use tiers:

### Tier 1

Real-time data.

### Tier 2

Aggregated intraday data: - 1m/5m as appropriate.

### Tier 3

Daily data.

### Tier 4

Strategy snapshots.

Build historical data from live feeds where practical.

Shared market calculations are calculated once.

Do NOT duplicate shared market calculations per user.

Strategy-specific metrics are calculated per active strategy where
necessary.

------------------------------------------------------------------------

# 37. MARKET DATA ARCHITECTURE

Target architecture:

Vendor → Market Data Gateway → Normalization Layer → Redis / Fast Cache
→ Internal Event Stream → Option Chain / Strategy / Adjustment Engines →
WebSocket → Browser

Never let browsers connect directly to market-data vendors.

Keep market-data providers behind an abstraction.

------------------------------------------------------------------------

# 38. MARKET DATA PROVIDER STRATEGY

The market-data layer must be vendor-agnostic from Day 1.

Internal normalized model must allow: - one provider initially -
provider replacement - multiple providers - fallback/secondary
provider - exchange expansion

V1 currently uses Zerodha live market data as the interim implementation
direction, subject to actual commercial/API permissions and written
approval where required.

Longer-term authoritative commercial source: - licensed market-data
provider - NSE coverage - BSE coverage - commercial redistribution
rights for SaaS

The user specifically clarified that option data may come from BSE as
well as NSE.

V1 exchanges: - NIFTY → NSE - SENSEX → BSE

Future commercial provider should ideally support both exchanges.

------------------------------------------------------------------------

# 39. CURRENT ZERODHA DATA DIRECTION

Interim V1 direction: - use Zerodha live market data - guide users
step-by-step to connect Zerodha APIs - historical market data is
deferred for the current V1 implementation direction

Important: This is an implementation/business constraint, not permission
to ignore Zerodha licensing/API terms.

The architecture must remain provider-independent so a commercial
NSE+BSE provider can replace/add the source later.

Do not assume Zerodha can be used for public redistribution without
confirming current terms.

------------------------------------------------------------------------

# 40. MARKET DATA NORMALIZATION

Normalized fields should include, as applicable:

-   instrument identifier
-   underlying
-   exchange
-   segment
-   expiry
-   strike
-   CE/PE
-   LTP
-   bid
-   ask
-   volume
-   OI
-   OI change
-   IV
-   Greeks
-   timestamp
-   data-source metadata
-   market-data health

Vendor Greeks are reference data.

Platform should calculate independently where feasible.

------------------------------------------------------------------------

# 41. LIVE DATA ACCESS --- Q58/Q59

Q58: All real-time/detailed market data is behind login.

Q59: Unauthenticated public site is marketing/product only: - product
explanation - sample/static screenshots - clearly labelled
sample/historical payoff diagrams - pricing - FAQ - signup/login

No live market data on public unauthenticated pages.

------------------------------------------------------------------------

# 42. ZERODHA BROKER BOUNDARY

Zerodha is responsible for: - authentication - account - positions -
orders - execution

Zerodha is final authority for: - contract/order eligibility - margin -
order acceptance - actual execution state

Do not attempt to recreate all Zerodha RMS/risk rules.

Distinguish:

1.  Contract catalogue = what exists
2.  Current eligibility = what Zerodha currently permits

Do not permanently delete contracts because availability can change.

At execution: - use instrument master - use available pre-checks -
broker response is final authority - do not pretend the platform can
perfectly replicate broker RMS

------------------------------------------------------------------------

# 43. ZERODHA ORDER RESTRICTIONS

Previously researched examples included: - options are not universally
limit-only - some market orders are restricted based on
liquidity/OI/expiry/deep ITM etc. - SL-M restrictions for index option
derivatives - theoretical-price/freak-trade protections - OI
restrictions - strike restrictions - option-chain data including expiry,
strikes, OI, Greeks, market depth - basket execution

These details are implementation references, not eternal hard-coded
truths.

Before encoding current broker rules, verify current authoritative
Zerodha documentation.

Never implement: \> options = limit only

as a universal rule.

------------------------------------------------------------------------

# 44. MARGIN

Before execution: 1. Fetch available margin/funds from Zerodha. 2.
Calculate/obtain required margin for the planned sequence. 3. Verify
sufficiency. 4. Submit only when requirements are satisfied.

After fills: - re-fetch broker state - re-check margin - continue only
when dependencies are satisfied

Platform margin estimate is planning information.

Zerodha is authority.

If insufficient: - stop - show available vs required - allow quantity
modification/review/add-funds path

------------------------------------------------------------------------

# 45. MULTI-LEG EXECUTION

User sees one high-level action:

> Execute Strategy

Execution engine creates: - execution plan - leg dependencies -
execution sequence - orders

Protective/buy legs may need to be established before dependent shorts.

Do NOT blindly implement: \> all buys first

for every strategy.

Execution sequence must understand: - protection - margin impact -
dependencies - broker constraints

------------------------------------------------------------------------

# 46. ORDER LIFECYCLE VS STRATEGY LIFECYCLE

They are separate but linked.

Order states can include: - Prepared - Submitted - Pending - Partially
Executed - Executed - Rejected - Cancelled

Critical rule:

> Order submitted ≠ position changed.

Actual broker execution must be confirmed.

Strategy state is not changed merely because an order request was
submitted.

------------------------------------------------------------------------

# 47. PARTIAL EXECUTION

Example: 4-leg strategy: - 3 filled - 1 failed

Priority: 1. Complete Strategy 2. Retry Failed Leg 3. Review Manually 4.
Close Partial Strategy

Do not automatically unwind successful legs by default.

Before attempting completion: - re-fetch Zerodha positions - re-fetch
order status - calculate actual remaining strategy - re-check margin -
verify missing leg - submit only required order(s)

Never assume the strategy is complete merely because all intended orders
were submitted.

Never unnecessarily undo successfully executed strategy legs.

------------------------------------------------------------------------

# 48. RETRY POLICY

V1: - no automatic order retry

If a leg fails: - explicit exception state - user-visible reason - user
can choose next action - no hidden automatic resubmission

Future controlled automation may revisit this.

------------------------------------------------------------------------

# 49. RECONCILIATION

Actual broker state wins.

Continuously reconcile platform strategy state with Zerodha: - after
execution - after reconnect - when app starts/resumes - periodically for
active strategies - on relevant broker/order events

Detect external broker changes.

If a user changes positions directly in Zerodha: - detect mismatch -
record it - require reconciliation

Manual reconciliation is allowed: - explicit - auditable

While mismatch is unresolved: - block new execution - block new
adjustment execution

------------------------------------------------------------------------

# 50. EXISTING POSITIONS

When Zerodha connects: - fetch open positions - identify possible
multi-leg structures

User can: - add to existing strategy - create new strategy - leave
standalone

Once grouped, monitor as strategy.

The detailed grouping/reconciliation algorithm must remain explicit and
auditable.

------------------------------------------------------------------------

# 51. STRATEGY OPERATIONAL STATE MACHINE --- Q200

Explicit states include:

-   Draft
-   Ready for Validation
-   Validated
-   Active
-   Monitoring Paused
-   Adjustment Proposed
-   Execution in Progress
-   Partially Executed
-   Reconciliation Required
-   Completed
-   Exited
-   Archived

State transitions must be explicit.

Do not infer state only from order rows.

------------------------------------------------------------------------

# 52. EXCEPTION STATES --- Q201

Every important non-normal state must explain: - what happened -
timestamp - what is blocked - next action

No "something went wrong" black boxes.

------------------------------------------------------------------------

# 53. STRATEGY ACTIVITY TIMELINE --- Q202

Every strategy has an immutable chronological activity timeline.

Record important events such as: - created - modified - validated -
activated - rule triggered - adjustment proposed - order prepared -
order submitted - order filled - partial execution - rejection -
reconciliation required - external broker change - user
acknowledgement - exit - completion

Timeline is append-only/auditable.

------------------------------------------------------------------------

# 54. RULE-TRIGGER AUDIT --- Q203

Every triggered rule must show the exact values/conditions that caused
it.

Example: - current underlying - threshold - current P&L - threshold -
IV - DTE - relevant strike/breakeven - timestamp - data health/source

Users should be able to understand: \> Why did this trigger?

------------------------------------------------------------------------

# 55. MONITORING / EXIT / ADJUSTMENT PLACEMENT

Strategy screen is the strategy control center.

It should show: - current strategy - current live state - entry rules -
adjustment rules - exit rules - current alerts - proposed adjustments -
execution/reconciliation state - activity timeline

Position screen is useful for current broker-linked position
information, but strategy remains the controlling domain object.

------------------------------------------------------------------------

# 56. NOTIFICATIONS

V1 channels: - in-app - push - email - WhatsApp

Priority: - Info → in-app - Watch → in-app + push - Action opportunity →
push + in-app + possibly WhatsApp - Exit/risk/order failure → push +
email + WhatsApp + in-app

Avoid alert fatigue.

Provider/consent/quiet-hours/templates/escalation/dedupe/rate-limits/audit/retry
must remain configurable implementation areas where not yet finalized.

------------------------------------------------------------------------

# 57. HOME / DASHBOARD

Proposed home: - Welcome, \[Name\] - Create a Strategy - Explore Option
Chain - Learn - 7-day Pro trial status - "I already know my strategy"
quick path - Active strategies - Important alerts - Account status

No forced Zerodha connection.

Connect contextually when a broker-dependent function is selected.

------------------------------------------------------------------------

# 58. NAVIGATION --- Q78

Primary navigation:

1.  Home
    -   Overview
    -   Important alerts
    -   Active strategies
    -   Account status
2.  Strategies
    -   My Strategies
    -   Create Strategy
    -   Strategy Builder
    -   Live Strategies
    -   Adjustments
    -   Completed Strategies
3.  Positions
    -   Current positions
    -   Strategy-linked positions
    -   Adjustment opportunities
    -   P&L/risk
4.  Market
    -   Option Chain
    -   Underlying/index view
    -   Market context
5.  Orders
    -   Pending
    -   Executed
    -   Failed/partial
    -   Execution history
6.  Alerts
    -   Active
    -   History
    -   Notification settings
7.  Learn
    -   Strategy education
    -   Options concepts
    -   Platform guidance

Profile/avatar → Account & Settings: - Profile - Zerodha connection -
Subscription & Billing - Free Eligibility - Referrals - Notifications -
Security - Preferences

------------------------------------------------------------------------

# 59. ZERODHA CONNECTION --- Q79--Q80

Connection is completely optional until a broker-dependent function is
needed: - execution - live positions/orders/account data -
direct-customer eligibility

Contextual prompt:

> Connect your Zerodha account to continue. We'll use your Zerodha
> account to verify availability, check margin and prepare/execute your
> strategy.

After onboarding: - open Home/dashboard directly - no forced connection

Zerodha authorization/session: - approximately 24 hours according to the
project decision - requires daily reauthentication

Session expiry is not identity deletion.

Same Client ID reconnecting restores the same association and does not
create a new trial.

------------------------------------------------------------------------

# 60. CONNECTION IS NOT REQUIRED FOR STRATEGY CREATION --- Q185--Q188

Q185: Zerodha connection is NOT mandatory for strategy creation.

Q186: Without Zerodha: - allow draft creation/configuration - lock
live-data-dependent functionality

Q187: Connecting Zerodha never auto-activates a strategy.

Q188: When live data becomes available: - automatically recalculate
drafts - never redesign/rewrite the user's strategy silently

------------------------------------------------------------------------

# 61. IDENTITY / ENTITLEMENT MODEL

Identity layers:

1.  Platform User ID
2.  Google identity/email
3.  Mobile identity
4.  Zerodha Client ID
5.  Zerodha authorization/session
6.  Commercial entitlement

Persistent principle: - email can change - session can expire - Zerodha
authorization can expire - historical relationship between Client ID and
platform entitlement must not reset

Google Sign-In preferred.

Google-authenticated email is already verified.

No email OTP.

Mobile: - WhatsApp OTP - separate OTP system

Store separately: - number - country code - verification
status/timestamp - attempt/rate-limit metadata - email verification
status

Registration: Required: - first name - last name - Google-verified
email - WhatsApp-verified mobile - market experience - profession -
legal/consent acknowledgements

Optional: - DOB - city/location

No full address.

Market experience: - New to stock markets - Beginner - Intermediate -
Experienced - Advanced/Professional

Profession: - Salaried/Employee - Business Owner -
Self-employed/Freelancer - Trader - Investor - Finance Professional -
Student - Retired - Homemaker - Other

------------------------------------------------------------------------

# 62. IDENTITY / ANTI-ABUSE Q82--Q97

Q82: Same Zerodha Client ID on second Gmail/platform account: - block
normal second independent access - offer legitimate recovery/transfer -
no second trial

Q83: Hybrid transfer: - straightforward legitimate cases may
auto-complete after verification - suspicious/repeated cases go to Admin
review

Q84: One Zerodha Client ID → one platform account at a time in V1. No
family/business sharing in V1.

Q85: Email can change within same platform account. Preserve: - Platform
User ID - Zerodha association - trial - entitlements -
strategies/history - referrals

Q86: Old email immediately stops being login identifier. Retain only in
security/audit history.

Q87: V1 does not attempt to identify one human across multiple
legitimate Zerodha accounts. Basic anti-abuse only.

Q88: Trial begins at successful registration.

Q89: Active strategies continue monitoring after Pro expiry.

Q90: Paid Pro expiry uses same Limited/Read-Only model. No special V1
grace period.

Q91: Live/detailed Option Chain unavailable in Limited/Read-Only.

Q92: Option Chain may be shown behind Pro gate with static/sample
preview clearly labelled: - Sample - Not Live

Q93: Historical records/results accessible indefinitely. New simulations
remain Pro.

Q94: Disconnecting Zerodha does not delete/close a strategy.
Strategy/history remain. Live positions/orders/margin/execution
unavailable until reconnect.

Q95: Same Client ID reauthentication restores existing association. No
new trial/customer/entitlement.

Q96: Account deletion retains only minimal anti-abuse/entitlement record
needed to prevent trial reset, subject to privacy/retention policy. Do
not retain the whole deleted account solely for this.

Q97: If Zerodha was never connected: - trial history is tied to platform
account - another unlinked account may receive its own trial - no
aggressive fingerprinting

------------------------------------------------------------------------

# 63. COMMERCIAL MODEL

Everyone may register.

Trial: - 7-day full Pro - begins at successful registration

After trial, without another entitlement: - Limited/Read-Only

Limited users can: - see existing strategies - see history - see
settings - see eligibility/referrals/billing - continue monitoring
active strategies - receive important alerts

Limited users cannot: - create new Pro strategies - use live detailed
Option Chain - run new Pro simulations - execute new Pro functionality

Feature click: - contextual upgrade/eligibility message - Subscribe to
Pro - Check Free Eligibility

Avoid aggressive popups.

------------------------------------------------------------------------

# 64. ENTITLEMENT ENGINE

Do NOT model access as: free_user = true

Entitlement is event-based.

Sources: - Trial Pro - Direct Zerodha Customer Pro - Referral-earned
Pro - Paid Monthly Pro - Paid Annual Pro - Expired/Limited

Store: - source - start - expiry - status - reference - audit data

Entitlement must be composable and auditable.

------------------------------------------------------------------------

# 65. DIRECT QUALIFYING ZERODHA CUSTOMER

Admin maintains qualifying Zerodha Client IDs.

User: - authenticates through official Zerodha integration - platform
verifies Client ID against list

Match: - full Pro free indefinitely

UI: \> You're already on Pro 🎉

Show: - Complimentary qualifying Zerodha customer - Pro - ₹0 -
Complimentary/Active - Renewal not applicable - Payment disabled - No
upgrade prompt - No payment-method requirement

Internal state: - Plan = Pro - Price = 0 - Entitlement source = Direct
Zerodha Customer - Expiry = none

------------------------------------------------------------------------

# 66. ADMIN ELIGIBILITY --- Q70

Admin functionality: - CSV bulk import - manual Client ID management -
search/filter - verification status - user association - entitlement
status - import history - audit trail - export/reporting - duplicate
validation - malformed-data validation before applying changes

------------------------------------------------------------------------

# 67. REFERRAL --- Q61/Q63

Q61: One successful qualifying Zerodha referral earns: - 1 month Pro
free

Success requires: - account opening through user's referral -
attribution to the user

A click/application start alone does not count.

Q63: Stacking configurable. Initial default: - enabled

Example: active until Oct 10 + successful referral Sep 20 → Nov 9 when
stacking enabled

Rewards are entitlement events.

Admin-configurable: - reward duration - stacking - max accumulated free
days - validity - extension behavior - attribution - fraud controls

------------------------------------------------------------------------

# 68. PAID PRO --- Q64/Q66

Q64: - ₹600/month

Annual pricing/discount: - Admin-configurable

Q66: - Razorpay for V1

Keep payment abstraction replaceable.

Admin-configurable: - monthly price - annual price - discount - trial
duration - referral reward - stacking - promotions - grace period -
future plans

------------------------------------------------------------------------

# 69. FREE ELIGIBILITY LOOP

If user already has Zerodha: → Check eligibility / Refer someone

If user does not have Zerodha: → Open Zerodha through referral →
connect/authenticate → eligibility

Preferred positioning:

> Zerodha Partner Benefit

or:

> Zerodha customers may qualify for complimentary access.

Do not disguise broker acquisition.

------------------------------------------------------------------------

# 70. SECURITY / COMPLIANCE BOUNDARIES

Keep: - broker integrations behind adapters - market-data integrations
behind adapters - payment behind adapter - business rules outside UI -
shared calculations centralized - audit history append-only where
required

Never: - store broker credentials directly unless the official
integration requires a secure token mechanism - expose market-data
vendor credentials to browser - allow arbitrary order entry outside
strategy context - bypass reconciliation blocks - allow Advanced mode to
bypass safety checks

Compliance review is required for: - personalized adjustment logic -
advisory-like language - notification content - data
redistribution/licensing - exchange/vendor contracts - broker
integration terms

------------------------------------------------------------------------

# 71. MARKET DATA LICENSING / VENDOR REQUIREMENTS

The project previously evaluated: - TrueData - Global Datafeeds (GFDL)

The user contacted TrueData and was told commercial NSE data use may
require an NSE certificate/document.

Do not encode assumptions about this into product logic.

Vendor selection must verify: - raw data - historical data - intraday
resolution - Greeks/higher Greeks - option-chain fields -
underlying/futures - depth - timestamps - contract master - expiry -
contract events - API limits - WebSocket capacity - historical
retention - commercial redistribution rights - SaaS scale economics - 5k
→ 100k → 500k user scaling - NSE coverage - BSE coverage

Ideal commercial source: - authorized - NSE + BSE - commercial SaaS
redistribution rights - scalable WebSocket/API - appropriate historical
rights

------------------------------------------------------------------------

# 72. HISTORICAL DATA / SIMULATION PRIORITY

Simulation and historical data are lower priority for the immediate V1
implementation.

Historical simulation, when implemented: - simple historical strategy
simulation - not full quant backtesting - EOD default - intraday later -
clearly labelled historical/simulation

Do not let simulation architecture block core live product
implementation.

------------------------------------------------------------------------

# 73. DATA SCALABILITY

Architecture must be designed from the beginning for: - \~5,000--6,000
users - 100,000+ users - potentially 500,000 users

Key principle: Shared market calculations happen once.

Do not calculate identical market metrics independently for every user.

Strategy-specific calculations are performed only where required.

------------------------------------------------------------------------

# 74. SHARED VS USER-SPECIFIC COMPUTATION

Shared: - market data normalization - shared Greeks where possible -
underlying state - option-chain metrics - common contract metadata -
market-wide derived metrics

User/strategy-specific: - strategy P&L - strategy risk - rule
evaluation - strategy state - adjustment candidate analysis -
user-specific entitlement - user-specific alerts

------------------------------------------------------------------------

# 75. STRATEGY DATA MODEL --- IMPLEMENTATION EXPECTATION

Claude Code should design explicit entities/value objects for at least:

-   User
-   Identity
-   Mobile Verification
-   Zerodha Connection
-   Entitlement
-   Strategy
-   Strategy Version
-   Strategy Leg
-   Strategy Rule
-   Entry Rule
-   Adjustment Rule
-   Exit Rule
-   Strategy Risk Limits
-   Strategy Live State
-   Market Instrument
-   Contract
-   Market Tick/Quote
-   Aggregated Market Data
-   Order
-   Execution Plan
-   Execution Step
-   Broker Position
-   Strategy Position
-   Reconciliation Event
-   Adjustment Opportunity
-   Adjustment Proposal
-   Alert
-   Notification
-   Strategy Activity Event
-   Audit Event

Exact persistence technology is an implementation decision unless
constrained elsewhere.

------------------------------------------------------------------------

# 76. BROKER ABSTRACTION

V1 broker implementation: - Zerodha

Architecture: - Broker interface/adapter - Zerodha adapter

Do not over-engineer multiple brokers now.

The abstraction should be enough to: - authenticate - fetch account -
fetch margin - fetch positions - fetch orders - submit order - fetch
order status - reconcile

Do not build unused broker implementations.

------------------------------------------------------------------------

# 77. MARKET-DATA ABSTRACTION

Market-data provider interface should allow: - live quote stream -
option-chain snapshot - instrument/contract master - underlying quote -
futures quote - optional historical data later - health/status - source
metadata

Normalization occurs internally.

------------------------------------------------------------------------

# 78. ACCOUNT / POSITION RECONCILIATION

Reconciliation is not a UI afterthought.

It is a domain service.

It must detect: - missing platform position - unexpected broker
position - quantity mismatch - strike mismatch - side mismatch - expiry
mismatch - external broker modification - partially executed strategy

Every mismatch should have: - timestamp - broker state - platform
state - difference - required next action

------------------------------------------------------------------------

# 79. EXECUTION SAFETY

Before execution: - strategy is valid - strategy version is
active/proposed as appropriate - broker connected - session valid -
market data healthy where required - contracts valid - quantities
valid - margin sufficient - execution dependencies satisfied - no
unresolved reconciliation mismatch

If any critical condition fails: - block - explain - log

------------------------------------------------------------------------

# 80. STRATEGY VALIDATION

Validation should include: - supported underlying - valid contract -
valid expiry - valid strike - valid side - valid quantity - broker
eligibility where known - multi-expiry rules - duplicate-leg handling -
risk calculations - margin estimate - charges estimate where available -
data freshness - rule validity - execution dependency validity

Validation must not silently mutate the user's strategy.

------------------------------------------------------------------------

# 81. NO SILENT SUBSTITUTION

If a selected contract becomes unavailable: - keep the intended contract
in the strategy history/version - surface the problem - show valid
alternatives where useful - user explicitly selects an alternative -
create a new proposed version if the strategy changes

Never silently replace a strike/expiry/contract.

------------------------------------------------------------------------

# 82. ACCOUNT DISCONNECT

Disconnecting Zerodha: - does not delete strategy - does not delete
history - does not delete entitlement - does not delete user account

It disables: - live positions - live orders - margin - execution

until reconnect.

------------------------------------------------------------------------

# 83. PRODUCT ACCESS STATES

Commercial entitlement and operational strategy state are separate
concepts.

Do not use: - subscription state as strategy state - broker session
state as user identity - order state as strategy state

Examples: - User can be Pro but broker disconnected. - User can be
Limited but still monitor an active strategy. - Strategy can be Active
while Zerodha session temporarily expired. - Strategy can be
Reconciliation Required even when subscription is active.

------------------------------------------------------------------------

# 84. PERFORMANCE / EVENT ARCHITECTURE

Use event-driven patterns where they materially improve scale.

Likely shared flow:

Market Vendor → Gateway → Normalizer → Cache/Event Stream →
Strategy/Adjustment Evaluators → WebSocket/Alert services

Do not create per-user vendor subscriptions when one shared provider
stream can feed many users.

Fan out internally.

------------------------------------------------------------------------

# 85. REAL-TIME UI

Browser receives platform-normalized data through platform
WebSocket/session channels.

Browser must not: - connect directly to vendor - contain market-data
credentials - implement authoritative business rules - decide execution
eligibility

UI renders domain state.

------------------------------------------------------------------------

# 86. AUDITABILITY

Audit important: - strategy changes - strategy version creation - rule
evaluation - trigger values - user approvals - order preparation - order
submission - broker response - execution - reconciliation - external
broker changes - entitlement changes - admin changes - security events

Use immutable event/timeline records where appropriate.

------------------------------------------------------------------------

# 87. ERROR HANDLING

Errors must be classified.

At minimum: - user input error - strategy validation error - market-data
error - broker authentication error - broker eligibility error - margin
error - order rejection - partial execution - reconciliation mismatch -
notification error - entitlement/access error - internal system error

User-facing errors should explain: - what happened - impact - what is
blocked - next action

------------------------------------------------------------------------

# 88. ENGINEERING PRINCIPLES FOR CLAUDE CODE

1.  Preserve product invariants.
2.  Domain logic belongs in backend/domain services, not UI-only code.
3.  UI cannot bypass strategy-only execution.
4.  Broker authority wins on broker state.
5.  Never silently mutate user strategy.
6.  Never silently retry V1 orders.
7.  Never silently substitute contracts.
8.  Never equate submitted order with execution.
9.  Never treat a broker session as identity.
10. Never duplicate shared market computation per user.
11. Keep providers replaceable.
12. Keep payment replaceable.
13. Keep audit history.
14. Make state transitions explicit.
15. Test failure paths, not only happy paths.
16. Prefer simple scalable primitives over premature complexity.
17. Do not build unused V1 abstractions merely for theoretical elegance.
18. Do not remove future extensibility that is explicitly required.
19. Verify UI changes with screenshots.
20. Do not deploy to production without owner approval.

------------------------------------------------------------------------

# 89. ENGINEERING FACTORY / LEGACY CAPABILITY MIGRATION

The Engineering/Claude Code Factory is intended to be reusable across
projects.

Before recreating engineering capabilities, Claude Code should inspect
the existing/legacy project for: - Skills - Hooks - Rules -
Agents/subagents - Workflows - Configurations - Scripts - Cloud-resource
patterns - Testing patterns - Verification patterns - reusable
engineering assets

Classify each capability: - Reuse directly - Adapt - Generalize - Retire

Proven reusable capabilities should be migrated into the
Factory/Capability Library.

Do not recreate a capability that already exists and is suitable.

The Factory should support: - self-learning/self-improvement - reusable
skills - reusable agents/subagents - reusable rules - reusable hooks -
reusable workflows - reusable verification patterns

------------------------------------------------------------------------

# 90. CLAUDE CODE RESOURCE EFFICIENCY

Use model/tool resources deliberately.

Principles: - Do not use the most expensive model for trivial tasks. -
Reserve stronger reasoning for architecture, difficult debugging,
complex migrations, security, and high-risk changes. - Batch compatible
changes. - Avoid unnecessary repeated test runs after every tiny
change. - Stagger test/verification intelligently. - Avoid token-heavy
status-artifact updates when a compact update is sufficient. - Keep the
control-center/status artifact useful but efficient.

------------------------------------------------------------------------

# 91. PROJECT CONTROL CENTER

Create/maintain a project status/control-center page or equivalent
artifact.

Track: - specs - stories - tasks - status - dependencies - blockers -
verification - screenshots for UI changes - implementation progress

UI changes must be verified using screenshots during automation.

The control center should not become a token-heavy bottleneck.

------------------------------------------------------------------------

# 92. IMPLEMENTATION ORDER

Recommended implementation sequence:

### Phase 0 --- Discovery

-   inspect repository
-   inspect existing architecture
-   inspect Engineering Factory
-   inspect legacy project
-   inventory reusable capabilities
-   inspect current dependencies/tooling
-   identify what already exists
-   do not overwrite working capabilities blindly

### Phase 1 --- Core domain foundation

Implement: - strategy domain - strategy versions - legs - rules - state
machine - audit/timeline - calculations - validation - entitlement
foundations - provider interfaces

### Phase 2 --- Core vertical slice

Build one end-to-end path:

Create Strategy → Configure Legs → Calculate P&L/Risk → Save Draft →
Connect Zerodha → Validate → Prepare Execution Plan → Review → Execute →
Confirm Broker Execution → Reconcile → Active Monitoring

### Phase 3 --- Verification Gate

Before broad parallelization: - run unit tests - run integration tests -
run domain invariants - run calculation verification - run
state-transition verification - run reconciliation scenarios - run
security checks - verify screenshots for UI

### Phase 4 --- Parallel bounded implementation

After the core is stable, parallelize by bounded domain, for example: -
market-data adapter - option chain - strategy builder UI - monitoring -
alerts - entitlement/billing - admin - learn - responsive UX

Do not let parallel work redefine core domain semantics.

------------------------------------------------------------------------

# 93. CORE DOMAIN INVARIANTS --- TEST THESE

At minimum:

1.  Every executed trade belongs to a strategy.
2.  A strategy has a version.
3.  Proposed strategy version ≠ active version until
    confirmed/executed/reconciled.
4.  Order submission ≠ execution.
5.  Broker state is authoritative for actual position state.
6.  Unresolved reconciliation mismatch blocks new execution/adjustment
    execution.
7.  No automatic V1 order retry.
8.  No silent contract substitution.
9.  No silent strategy redesign when live data arrives.
10. Connecting Zerodha never auto-activates a strategy.
11. Strategy creation does not require Zerodha connection.
12. Disconnecting Zerodha does not delete strategy/history.
13. Active strategies may continue monitoring after Pro expiry.
14. Limited users cannot access live detailed Option Chain.
15. Shared market calculations are not duplicated per user.
16. Rule triggers record exact triggering values.
17. Strategy timeline is immutable/append-only.
18. Important exception states explain what happened and next action.
19. Advanced UX cannot bypass safety controls.
20. Production deployment requires explicit owner authorization.

------------------------------------------------------------------------

# 94. V1 NON-GOALS

Do not accidentally expand V1 into: - multiple brokers - unrestricted
autonomous trading - full quant backtesting platform - tick-by-tick
historical warehouse for every option - native mobile apps -
unrestricted order terminal - AI trade-advice chatbot - copy trading -
pooled money - discretionary account management - unnecessary broker RMS
recreation

------------------------------------------------------------------------

# 95. OPEN / NOT YET LOCKED AREAS

These are implementation/product questions that may require Q204+
decisions or current research:

-   exact production market-data vendor/licensing
-   detailed Zerodha commercial approval for SaaS data use
-   exact historical data provider
-   exact current-vs-expiry P&L model for live estimates
-   detailed option pricing/IV/time-value assumptions
-   bid/ask/slippage model
-   exact charges model
-   order types and per-leg pricing UX
-   tick rounding
-   timeout/cancel/repricing behavior
-   MIS/NRML details
-   expiry/multi-expiry execution edge cases
-   quantity edge cases
-   detailed existing-position grouping algorithm
-   alert provider/consent/quiet hours/templates/escalation/dedupe/rate
    limits
-   adjustment rule priority/conflict/cooldown behavior
-   detailed security architecture
-   detailed data-retention policy
-   SEBI/legal review outcomes
-   Admin/system-health screens
-   final production cloud/stack choices

Do not invent decisions for these.

When a decision is genuinely required, create Q204+ rather than silently
deciding.

------------------------------------------------------------------------

# 96. PRODUCT DECISION TRACEABILITY

Known question decisions preserved in this handoff include:

-   Q43--Q57: Option Chain
-   Q58--Q59: live/public data access
-   Q61: referral reward
-   Q63: referral stacking
-   Q64: Pro price
-   Q66: Razorpay
-   Q70: Admin eligibility
-   Q72--Q77: identity/onboarding
-   Q78: navigation
-   Q79--Q80: Zerodha connection timing
-   Q81: Home/dashboard direction
-   Q82--Q97: identity, trial, entitlement, expiry, anti-abuse lifecycle
-   Q98--Q101: market-data architecture/historical strategy
-   Q149: platform can detect adjustment opportunities without
    predefined user rules
-   Q159: generic warning + possible approaches when monitoring detects
    an important risk area but no user rule exists
-   Q160: four-layer Adjustment Opportunity panel
-   Q161--Q170: adjustment data history, aggregation, underlying data,
    extensibility, feasibility, raw-data-first, storage tiers, shared
    computation
-   Q171--Q173: authoritative market-data provider direction and vendor
    evaluation criteria
-   Q185--Q188: Zerodha connection and draft/live behavior
-   Q189: Strategy Definition vs Live Market State
-   Q190: strategy versions
-   Q191: proposed vs active versions
-   Q192: partial multi-leg execution/reconciliation
-   Q193: no automatic V1 retry
-   Q194: order lifecycle vs strategy lifecycle
-   Q195: submitted ≠ executed
-   Q196: continuous reconciliation
-   Q197: external broker change detection
-   Q198: explicit/auditable manual reconciliation
-   Q199: block execution/adjustment during mismatch
-   Q200: explicit strategy state machine
-   Q201: exception-state explanations
-   Q202: immutable activity timeline
-   Q203: exact rule-trigger values

Important source limitation: The two supplied historical handoff files
explicitly state that exact Q1--Q32 wording is not reliably retained
there. This document therefore preserves their resulting product
requirements from the handoffs rather than inventing historical wording
for missing questions. The later decisions through Q203 are consolidated
from the continuing project context.

------------------------------------------------------------------------

# 97. Q203 IMPLEMENTATION CHECK

At the end of the product-definition phase, the platform must be able to
answer for every triggered rule:

-   What rule triggered?
-   What were the exact input values?
-   What threshold was evaluated?
-   What timestamp was used?
-   What market-data source was used?
-   Was data fresh/healthy?
-   What strategy version was active?
-   What did the system do next?
-   Was an alert generated?
-   Was an order prepared?
-   Was user confirmation required?
-   Was an order executed?
-   What did the broker actually report?
-   Did reconciliation succeed?

------------------------------------------------------------------------

# 98. CLAUDE CODE OPERATING MODE

Claude Code should behave as: - senior product engineer - principal
architect - implementation agent - test/verification agent -
documentation/control-center maintainer

It should NOT behave as: - autonomous product owner - autonomous
production deployer - silent requirements editor

For implementation tasks: 1. Inspect before changing. 2. Reuse before
recreating. 3. Preserve locked decisions. 4. Make the smallest coherent
change. 5. Test. 6. Verify. 7. Update status. 8. Record important
decisions. 9. Continue when the path is clear. 10. Ask the owner only
when a genuine decision boundary is reached.

------------------------------------------------------------------------

# 99. PRODUCTION RULE

All environments other than production may be automated according to the
Engineering Factory rules.

Production deployment is explicitly owner-controlled.

Claude Code must: - prepare production - validate production readiness -
report what will change - stop before actual production deployment -
wait for explicit owner authorization

No inferred production approval.

------------------------------------------------------------------------

# 100. FIRST IMPLEMENTATION ACTION

Do not immediately start writing large amounts of code.

First: 1. Inspect the repository. 2. Inspect the current project
structure. 3. Inspect Engineering Factory capabilities. 4. Inspect
legacy project capabilities. 5. Build capability inventory. 6. Identify
current stack. 7. Identify existing implementation. 8. Map existing code
to this handoff. 9. Identify gaps. 10. Propose the implementation
sequence. 11. Start with the smallest verified core vertical slice.

Do not ask the user to restate this product history.

Do not restart product discovery.

Start implementation from the current repository state.

------------------------------------------------------------------------

# 101. FINAL SOURCE-OF-TRUTH RULE

When there is a conflict:

1.  Explicit later locked project decision
2.  This comprehensive handoff
3.  Earlier handoff material
4.  Technical preference/inference

Never use a technical preference to override a locked product decision.

If two locked requirements genuinely conflict: - stop - identify the
exact conflict - explain the minimum decision required - ask one
question - record the answer as the next numbered decision

------------------------------------------------------------------------

# 102. CORE PROMISE

> Plan the trade. Follow the strategy. Then execute.

END OF COMPREHENSIVE MASTER HANDOFF
