# Indian Index Options / F&O SaaS
# Q102–Q203 Question / Decision Continuation

Version: 2026-09-28

## Important note

The historical handoff files available to this project do not preserve the verbatim wording of every question from Q102–Q148. I will not invent historical wording and present it as verbatim.

Therefore:
- Q102–Q148 below are consolidated decision records reconstructed from the finalized project requirements.
- Q149–Q203 preserve the later question/decision subjects and locked outcomes available from the project record.
- This file is a continuation of `CLAUDE_CODE_MASTER_HANDOFF_COMPREHENSIVE_Q1-Q203.md`.
- These decisions should not be reopened unless the owner explicitly asks.

---

# Q102–Q148 — Consolidated Decision Records

## Q102 — Market-data architecture
Decision: Centralize market data.

Vendor → Market Data Gateway → Normalization → Redis/Fast Cache → Internal Event Stream → Option Chain/Strategy/Adjustment Engines → WebSocket → Browser.

Browsers never connect directly to vendors.

## Q103 — Vendor independence
Decision: Market-data architecture is vendor-agnostic from Day 1. Providers must be replaceable/addable without redesigning product-domain logic.

## Q104 — Normalized market-data model
Decision: Normalize, as applicable, instrument/underlying/exchange/expiry/strike/CE-PE/LTP/bid/ask/volume/OI/OI change/IV/Greeks/timestamp/source/data-health.

## Q105 — Shared market feed
Decision: Prefer shared provider streams and internal fan-out rather than one vendor connection per user.

## Q106 — Browser security boundary
Decision: Vendor credentials and direct vendor connections never reach the browser.

## Q107 — Shared calculations
Decision: Calculate shared market metrics once and reuse them. Do not duplicate identical market calculations per user.

## Q108 — Strategy calculations
Decision: Strategy-specific P&L, risk, rules, state and adjustment analysis are calculated for active strategies as required.

## Q109 — Scale
Decision: Design from the beginning for approximately 5,000–6,000 users, then 100,000+, potentially 500,000.

## Q110 — Historical storage
Decision: Do not retain complete tick-by-tick history for every option. Use real-time, aggregated intraday, daily and strategy-snapshot tiers.

## Q111 — Build historical data
Decision: Where practical, build historical/aggregated data from the licensed live feed. Keep a separate historical provider possible through the abstraction.

## Q112 — Historical priority
Decision: Historical data is lower priority for immediate V1 and must not block live strategy creation, Option Chain, execution or monitoring.

## Q113 — Simulation
Decision: V1 historical simulation is simple strategy simulation, not a full quant backtester. EOD is the default; richer intraday analysis can follow.

## Q114 — Outcome visibility
Decision: Every user should see P&L, max profit/loss, breakevens, payoff, scenario behavior, margin and risk before execution.

## Q115 — Calculation engine
Decision: One centralized calculation engine powers builder, payoff, scenario table, current P&L, adjustment Before/After analysis and related calculations.

## Q116 — Expiry scenario formulas
Decision:
- BUY CALL = [MAX(Market−Strike,0) − Entry Price] × Quantity
- SELL CALL = [Entry Price − MAX(Market−Strike,0)] × Quantity
- BUY PUT = [MAX(Strike−Market,0) − Entry Price] × Quantity
- SELL PUT = [Entry Price − MAX(Strike−Market,0)] × Quantity

Strategy scenario P&L = sum of leg scenario P&Ls. Current LTP is not used for expiry payoff.

## Q117 — Live/current P&L
Decision: Current/live P&L uses current market pricing; expiry scenario uses entry premium and intrinsic payoff. Exact bid/ask/slippage methodology remains an implementation/open detail unless later locked.

## Q118 — Scenario table
Decision: One horizontally scrollable table. Columns: Leg, Action, Instrument, Expiry, Strike, Quantity, Entry Price, LTP, Entry Value, Current Value, Unrealized P&L, P&L %, IV, Delta, Gamma, Theta, Vega, scenario market levels, Lower BE, Upper BE, Status. Sticky left columns; current market highlighted.

## Q119 — Scenario cells
Decision: Every scenario cell is populated. No blanks merely because a leg is out-of-the-money.

## Q120 — Scenario levels
Decision: Approximately ₹100 spacing is the default where appropriate, with roughly 1,000–2,000 points of useful underlying range. Keep the implementation configurable.

## Q121 — Breakevens
Decision: Breakevens are strategy-level properties; individual legs do not require breakevens.

## Q122 — Live pricing fields
Decision: Entry Price, LTP, Entry Value, Current Value, Unrealized P&L and P&L % are first-class fields and update live. Bid/Ask can remain advanced.

## Q123 — Greeks
Decision: Default fields include IV, Delta, Gamma, Theta and Vega, after P&L % and before scenario columns.

## Q124 — Risk UX
Decision: Avoid repetitive generic acknowledgements. Normal = explain; elevated = warn; exceptional = explicit acknowledgement. Execution review shows strategy, margin, max loss/profit, current P&L, leg count, sequence and broker.

## Q125 — Strategy-only execution
Decision: Option Chain and builder may prepare legs but cannot become unrestricted order-entry surfaces. Every execution belongs to a strategy.

## Q126 — Option Chain role
Decision: Option Chain is both market exploration and strategy construction. Selected contracts can be added to a strategy.

## Q127 — Contract substitution
Decision: Never silently substitute an unavailable contract. Preserve intent/history, surface the issue, suggest alternatives if useful, require explicit user selection and create a proposed/new version if strategy changes.

## Q128 — Strategy discovery language
Decision: Surface “Strategies you could consider” and “Suggested setup”. Avoid “Best trade” and imperative personalized trade instructions.

## Q129 — Expected market range
Decision: When user is unsure about outlook, allow lower/upper expected market levels for a selected timeframe/expiry and use the range for strategy/risk analysis.

## Q130 — Range pick lists
Decision: Separate lower and upper lists around current price; approximately 100-point increments. Lower cannot exceed current; upper cannot be below current.

## Q131 — Strategy preferences
Decision: Users may select preferred strategy types. Use preferences with range/market/risk constraints to surface matching valid strategies; do not force them.

## Q132 — Templates
Decision: Named strategy templates sit above the generic strategy engine. Do not create a separate hard-coded engine for every strategy.

## Q133 — Custom strategies
Decision: Unmatched leg combinations are allowed as Custom Strategy using the generic engine.

## Q134 — Strategy modification
Decision: Modify Strategy → proposed changes → recalculate P&L/risk/margin/charges/breakevens → Before/After → prepare adjustment orders → confirm → execute.

## Q135 — Expected-range strategy use
Decision: Expected range is an input for evaluating strategy candidates and risk, not a prediction guarantee.

## Q136 — Strike-selection modes
Decision: Conservative, Balanced, Aggressive, Manual Custom. Inputs may include spot, expiry, premiums, IV, expected move, capital, max loss and desired premium. Label output “Suggested setup”.

## Q137 — Manual override
Decision: Suggested setups never remove user control; manual override remains available.

## Q138 — Unified rule engine
Decision: One rule-engine concept powers entry, adjustment, exit and future controlled automation.

## Q139 — Entry conditions
Decision: V1 supports immediate, level/range, premium target, volatility and time-window conditions. Compound logic can be supported.

## Q140 — Exit conditions
Decision: Profit target, max loss, time exit and underlying level. Action = alert + prepare exit orders.

## Q141 — V1 automation
Decision: Alert + Prepare Orders. Condition → alert → exact multi-leg orders prepared → user reviews → user executes. No unrestricted autonomous trading in V1.

## Q142 — Future automation
Decision: Architecture may support controlled future automation without redesign, but unrestricted autonomous execution is not V1.

## Q143 — Monitoring
Decision: Rule-based monitoring covers P&L, underlying, BE/short-strike distances, DTE, IV, Greeks, margin utilization, entry/adjustment/exit conditions and data health.

## Q144 — Monitoring statuses
Decision: Green Healthy; Yellow Watch; Orange Adjustment Opportunity; Red Exit Condition Reached.

## Q145 — Strategy control center
Decision: Strategy screen is the main control center for strategy definition, live state, rules, alerts, proposed adjustments, execution/reconciliation and timeline.

## Q146 — Position screen
Decision: Position screen is useful for broker/current-position information, but Strategy remains the controlling domain object.

## Q147 — Strategy/order state separation
Decision: Strategy lifecycle and order lifecycle are separate but linked. Do not infer strategy state only from orders.

## Q148 — Broker authority
Decision: Zerodha is authoritative for actual account, position, order, margin, eligibility and execution state.

---

# Q149–Q184 — Adjustment / Data Foundation

## Q149 — Detect adjustment opportunities without user rules?
Decision: YES. The platform may detect potential adjustment opportunities even when no predefined user adjustment rule exists.

## Q150 — Detection vs user rule
Decision: Clearly distinguish user-defined rule triggers from platform-detected risk/attention areas.

## Q151 — Adjustment language
Decision: Use “Adjustment opportunity detected”, “Possible approaches”, “Review adjustment”, “Your rule was triggered”. Avoid “You should do this” and “Best adjustment”.

## Q152 — Adjustment model
Decision:
Strategy + Current Market + Time + P&L + Greeks + Position Geometry + User Rules → Trigger → Candidate Adjustment → Before/After Analysis → User Decision.

## Q153 — Are adjustment/exit plans mandatory?
Decision: NO. They are optional at strategy-definition level. Monitoring can continue without them.

## Q154 — Adjustment triggers
Decision: Support underlying movement/level, distance from short strike/BE, leg profit, strategy max profit/loss, Greeks, IV change/percentile, DTE, premium, P&L and compound conditions.

## Q155 — Adjustment actions
Decision: Possible actions include take profit, close/roll leg, roll spread, move strike, add/remove hedge or leg, quantity change, re-center, convert strategy, exit, alert and no-trade proposal.

## Q156 — Before/After
Decision: Every proposed adjustment can be analyzed before execution using legs, P&L, risk, margin, Greeks, breakevens and payoff.

## Q157 — Why am I seeing this?
Decision: Explain exact market condition, relevant strike/BE, distance, metric/rule, timestamp and data state.

## Q158 — Adjustment safety
Decision: Never imply adjustments always reduce risk. Adjustments can increase risk. Personalized adjustment logic may require legal/SEBI review.

## Q159 — Risk area without predefined rule
Decision: Show a warning plus generic possible approaches, not a specific personalized candidate setup.

## Q160 — Adjustment Opportunity panel
Decision: Four layers:
1. Why detected
2. Current strategy state
3. Possible approaches
4. Next step / user-selected approach → proposed configuration → Before/After analysis

Layer 2 includes P&L, max profit/loss, BEs, Delta/Gamma/Theta/Vega, margin utilization, DTE and relevant IV/OI/LTP.

## Q161 — Adjustment metric history
Decision: YES. Maintain historical time series for useful adjustment metrics using scalable storage tiers.

## Q162 — Leg + strategy data
Decision: YES. Adjustment engine uses both individual-leg and strategy-level aggregated data.

## Q163 — Underlying data
Decision: YES. Underlying-level data can independently drive adjustment analysis.

## Q164 — Extensibility
Decision: YES. New metrics must be addable without redesigning the data layer.

## Q165 — Collect data without rules?
Decision: YES. Collect adjustment-relevant data because platform detection may operate without user-defined rules.

## Q166 — Data Feasibility Test
Decision: Every metric must answer: raw data? source? calculate ourselves? scale? historical? legal/licensing? update frequency? storage? calculation method?

## Q167 — Raw-data-first
Decision: Prefer licensed raw data and derive metrics ourselves where practical.

## Q168 — Full tick history?
Decision: NO. Do not store complete tick-by-tick history for every option. Use real-time, aggregated intraday, daily and strategy-snapshot tiers.

## Q169 — Build history from live data?
Decision: YES, where practical and licensed.

## Q170 — Per-user duplication?
Decision: NO. Shared calculations happen once; strategy-specific calculations are performed per active strategy where required.

## Q171 — Long-term primary market-data source
Decision: Long-term authoritative market-data source should be a licensed commercial provider. Zerodha remains broker/account/execution authority.

## Q172 — Candidate providers
Decision record: TrueData and Global Datafeeds (GFDL) were evaluated. Commercial SaaS redistribution/scaling rights require explicit confirmation. TrueData indicated an NSE certificate/document may be required; exact requirement must be verified directly.

## Q173 — Provider-selection checklist
Decision: Verify raw data, historical data, intraday resolution, Greeks, option-chain fields, underlying/futures, depth, timestamps, contract master, expiry/events, API limits, WebSocket capacity, historical retention, redistribution rights, 5k/100k/500k economics, NSE coverage and BSE coverage.

## Q174 — NSE + BSE
Decision: Architecture must support both. V1: NIFTY/NSE and SENSEX/BSE. Prefer a future provider that covers both.

## Q175 — Interim Zerodha data
Decision: Current V1 implementation direction uses Zerodha live market data while retaining provider independence. Historical data is deferred. Current API/commercial terms must be verified before production.

## Q176 — Zerodha setup UX
Decision: Provide visible “Connect Zerodha” guidance and step-by-step API/authorization setup.

## Q177 — Historical integration
Decision: Do not block V1 live functionality on historical-data integration.

## Q178 — Licensing boundary
Decision: Do not scrape NSE. Do not expose vendor credentials. Do not assume broker-provided data can be redistributed through a SaaS product without permission.

## Q179 — Contract catalogue vs eligibility
Decision: Keep “what contracts exist” separate from “what the broker currently permits”. Do not permanently delete unavailable contracts.

## Q180 — Execution authority
Decision: Zerodha is final authority for current order eligibility, margin, order acceptance, actual execution and actual position state.

## Q181 — Broker adapter
Decision: Zerodha only in V1, behind a broker abstraction sufficient for future expansion.

## Q182 — Market-data adapter
Decision: Provider-specific behavior belongs behind a gateway/adapter. Product engines consume normalized internal data.

## Q183 — Historical-provider abstraction
Decision: A separate historical provider, if needed, plugs into the broader data abstraction rather than requiring redesign.

## Q184 — Data health
Decision: Live strategy/rule evaluation must know whether market data is available, stale, delayed, unhealthy or unavailable. Do not silently trigger important rules from stale data.

---

# Q185–Q203 — Strategy Lifecycle / Execution / Reconciliation

## Q185 — Is Zerodha required for strategy creation?
Decision: NO. Draft strategy creation/configuration is allowed without Zerodha.

## Q186 — What works without Zerodha?
Decision: Allow draft creation/configuration and non-broker-dependent calculations. Lock live positions, margin, broker validation and execution.

## Q187 — Does connecting Zerodha auto-activate a strategy?
Decision: NO.

## Q188 — What happens when live data becomes available?
Decision: Recalculate drafts automatically using live data; never silently redesign/rewrite the strategy.

## Q189 — Strategy Definition vs Live Market State
Decision: SEPARATE.

Strategy Definition:
- underlying
- expiry
- legs
- strikes
- side
- quantities
- entry/adjustment/exit rules
- risk limits
- preferences/constraints

Live Market State:
- spot/futures
- LTP/bid/ask
- volume/OI/OI change
- IV/Greeks
- P&L
- margin/charges
- distances
- trigger state
- timestamps
- data health

## Q190 — Strategy versions
Decision: Preserve strategy versions.

## Q191 — Proposed vs active version
Decision: Proposed version is separate from active version. It becomes active only after the required user confirmation and successful execution/reconciliation process.

## Q192 — Partial multi-leg execution
Decision: Partial execution creates an explicit exception/reconciliation state. Broker actual state wins. Recalculate actual risk/P&L/margin and required remaining actions.

## Q193 — Automatic retry
Decision: NO automatic order retry in V1.

## Q194 — Order lifecycle vs strategy lifecycle
Decision: Separate but linked. Order states include Prepared, Submitted, Pending, Partially Executed, Executed, Rejected and Cancelled.

## Q195 — Submitted vs changed position
Decision: “Order submitted” does not mean “position changed”. Confirm actual execution.

## Q196 — Reconciliation
Decision: Reconcile with Zerodha after execution, reconnect, app start/resume, periodically for active strategies and on relevant broker/order events.

## Q197 — External broker changes
Decision: Detect direct Zerodha changes and require reconciliation.

## Q198 — Manual reconciliation
Decision: Allowed, explicit and auditable.

## Q199 — Unresolved mismatch
Decision: Block new execution and adjustment execution until reconciliation mismatch is resolved.

## Q200 — Strategy operational state machine
Decision: Explicit state machine including:
- Draft
- Ready for Validation
- Validated
- Active
- Monitoring Paused
- Adjustment Proposed
- Execution in Progress
- Partially Executed
- Reconciliation Required
- Completed
- Exited
- Archived

## Q201 — Exception states
Decision: Every important non-normal state explains what happened, timestamp, what is blocked and next action.

## Q202 — Strategy activity timeline
Decision: Every strategy has an immutable chronological activity timeline. Record creation, modification, validation, activation, rule triggers, adjustment proposals, order events, partial execution, rejection, reconciliation, external changes, acknowledgement, exit and completion.

## Q203 — Exact rule-trigger values
Decision: Every triggered rule records the exact input values/conditions that caused it, including thresholds, market values, timestamp, source/data health and active strategy version.

The user must be able to answer:
“Why did this trigger?”

---

# FINAL IMPLEMENTATION INSTRUCTION

Use this file together with:

`CLAUDE_CODE_MASTER_HANDOFF_COMPREHENSIVE_Q1-Q203.md`

Do not restart product discovery.

Do not invent missing historical Q102–Q148 wording.

Do not reopen Q102–Q203 decisions unless the owner explicitly asks.

When a genuinely new product/business decision is required, create Q204+ with:
1. the question,
2. the recommended answer,
3. the reason,
4. the owner’s final decision.

Core promise:

> Plan the trade. Follow your strategy. Then execute.

END
