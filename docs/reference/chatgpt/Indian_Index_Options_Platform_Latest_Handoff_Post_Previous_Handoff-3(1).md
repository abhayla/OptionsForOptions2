# Indian Index Options / F&O SaaS Platform — Latest Handoff

## Purpose
This is the latest continuation handoff after the previous handoff. Use it together with the previous handoff so a new session can continue without reopening settled decisions.

**Project rule:** Ask exactly ONE question at a time, give a recommendation with it, and do not proceed until approximately 95% confidence. Do not reopen locked decisions unless the user explicitly asks.

## 1. Handoff history
The previous handoff was created **before Q33A**. The project subsequently progressed much further. An old continuation marker incorrectly pointed back to Q33A; **Q33A is not the current continuation point**.

This handoff captures the later decisions reliably available from the project history. Exact wording of Q1–Q32 is not reproduced where it is not available; do not invent it. Their resulting requirements remain covered by the previous handoff and this consolidated state.

## 2. Product vision
Public SaaS for Indian index derivatives, designed to make strategy-based options/F&O trading easy, structured and transparent.

V1 supports **NIFTY and SENSEX**, with **Zerodha only** initially.

Supported legs: Call Buy/Sell, Put Buy/Sell, Futures Buy/Sell.

Core promise:
> **Plan the trade. Follow your strategy. Then execute.**

Strategy-first product: users create/setup strategies, calculate P&L/risk/margin/payoff, prepare and execute through Zerodha, monitor them, and review rule-triggered adjustment opportunities. Future automation is controlled by predefined strategy conditions; there is no unrestricted order interface.

Preferred language: “Strategies you could consider”, “Suggested setup”, “Adjustment opportunity detected”, “Possible adjustment”, “Review adjustment”, “Your rule was triggered”. Avoid guaranteed outcomes or “you should take this trade”. Personalized adjustment logic may require SEBI/legal review.

## 3. Strategy engine
Generic engine supports unlimited combinations of Call/Put Buy/Sell and Futures Buy/Sell. Templates sit above the generic engine.

Strategy object: Legs, Entry conditions, Risk, Adjustments, Exit plan, Execution plan, Orders, Monitoring, Completion.

Creation: Strategy-first default plus Advanced Manual Builder. Guided flow: objective → market/view/risk/capital → strategies to consider → configure → P&L/risk/margin/charges/payoff → entry/exit/adjustment conditions → review → prepare/execute.

Objectives: Earn premium; Limit risk; Benefit if market rises; Benefit if market falls; Trade a big move; I already know my strategy.

## 4. Option Chain decisions — Q43–Q57
- **Q43:** Same contract with opposite actions remains separate strategy legs; no auto-netting.
- **Q44:** Unavailable contract remains visible; valid alternatives may be suggested; explicit user choice; no silent substitution.
- **Q45:** Clean default + Advanced Details. Default: Strike, LTP, Change, IV, OI, Volume. Advanced: Bid/Ask, Delta, Gamma, Theta, Vega, OI Change, etc.
- **Q46:** Hybrid live-data architecture: LTP/bid/ask streaming; OI/IV lower-frequency.
- **Q47:** Persistent Selected Legs summary while scrolling; Add to Strategy.
- **Q48:** Duplicate contract asks whether to increase quantity, keep separate, or cancel.
- **Q49:** Validate before import; block serious errors; warn on legitimate cases such as mixed expiries.
- **Q50:** Selections persist across expiry tabs; multi-expiry strategies supported.
- **Q51:** Identify matching templates but never auto-convert/execute.
- **Q52:** Unmatched combinations allowed as Custom Strategy.
- **Q53:** Explicit Buy/Sell per contract; never infer action.
- **Q54:** +/- lot stepper using broker-valid lot size; exact quantity in Advanced.
- **Q55:** Compact live Strategy Preview: net premium, max profit/loss, breakevens, mini payoff; full scenario table in Builder.
- **Q56:** Immediate remove + short Undo.
- **Q57:** Adjustment rules global defaults + per-strategy overrides.

## 5. Market data foundation
Architecture:
**Vendor → Market Data Gateway → Normalization Layer → Redis/Fast Cache → Internal Event Stream → Option Chain/Strategy/Adjustment Engines → WebSocket → Browser**

Do not let browsers connect directly to vendors. Do not rely on Zerodha as the sole public market-data source. Establish data foundation before deep UI build. Confirm commercial licensing for multi-user SaaS.

Normalized fields: strike, expiry, CE/PE, LTP, bid, ask, volume, OI, OI change, IV, Greeks, timestamp. Vendor Greeks can be reference; platform should calculate independently where feasible.

## 6. Public/live data — Q58–Q59
- **Q58 = A:** All real-time/detailed market data behind login.
- **Q59 = A:** Public unauthenticated site is marketing/product only: product explanation, sample/static screenshots, clearly labelled sample/historical payoff diagrams, pricing, FAQ, signup/login. No live data.

## 7. Commercial model
Everyone may register. Google/Gmail login accepted. Everyone receives **7-day full Pro trial** beginning at successful registration.

After trial, users without another entitlement enter **Limited/Read-Only**, not hard lockout. They can see existing strategies/history/settings/eligibility/referrals/billing and continue monitoring active strategies/important alerts, but cannot create new Pro strategies, use live detailed Option Chain, run new Pro simulations or execute new Pro functionality.

Pro feature click should show contextual upgrade/eligibility message: **Subscribe to Pro** / **Check Free Eligibility**. Avoid aggressive popups.

### Entitlement Engine
Do not model access as `free_user=true`. Sources include:
- Trial Pro
- Direct Zerodha Customer Pro
- Referral-earned Pro
- Paid Monthly Pro
- Paid Annual Pro
- Expired/Limited

Entitlements are event-based with source, start/expiry/status/reference/audit data.

### Direct qualifying Zerodha customer
Admin maintains qualifying Zerodha Client IDs. User authenticates via official Zerodha integration; platform verifies Client ID against list. Match = full Pro free indefinitely.

Billing UI: “You’re already on Pro 🎉”; complimentary qualifying Zerodha customer; Pro; ₹0; Complimentary/Active; renewal not applicable; payment disabled; no upgrade prompt or payment-method requirement.

Internal state: Plan=Pro, Price=0, Entitlement source=Direct Zerodha Customer, Expiry=none.

### Q70 — Admin eligibility
CSV bulk import + manual Client ID management. Include search/filter, verification status, user association, entitlement status, import history, audit trail, export/reporting, duplicate/malformed validation before applying changes.

### Referral Pro — Q61, Q63
**Q61 = A:** One successful qualifying Zerodha referral earns **1 month Pro free**. Success requires account opening through the user’s referral and attribution to the user; click/application start alone does not count.

**Q63 = C:** Stacking configurable; initial default enabled. Example: active until Oct 10 + successful referral Sep 20 → Nov 9 when stacking enabled. Store rewards as entitlement events.

Admin-configurable referral rules should include reward duration, stacking, max accumulated free days, validity, extension behavior, attribution and fraud controls.

### Paid Pro — Q64, Q66
**Q64 = A:** ₹600/month. Annual price/discount remains Admin-configurable.

**Q66 = A:** Razorpay for V1. Keep payment abstraction replaceable.

Admin-configurable: monthly/annual prices, discount, trial duration, referral reward, stacking, promotions, grace period, future plans.

### Free eligibility loop
“I already have Zerodha” → Check eligibility / Refer someone.
“I don’t have Zerodha” → Open Zerodha through referral → connect/authenticate → eligibility.

Preferred positioning: **Zerodha Partner Benefit** / “Zerodha customers may qualify for complimentary access.” Avoid disguising broker acquisition.

## 8. Identity/authentication — Q72–Q77
Identity layers:
1. Platform User ID
2. Google identity/email
3. Mobile identity
4. Zerodha Client ID
5. Zerodha authorization/session
6. Commercial entitlement

Persistent principle: email/session can change or expire; the historical relationship between Zerodha Client ID and platform entitlement must not reset.

Google Sign-In preferred; Google-authenticated email is verified, so no email OTP.

Mobile is verified through **WhatsApp OTP** using the user's separate OTP system. Store number, country code, verification status/timestamp, attempt/rate-limit metadata, and email verification status separately.

Registration required: first name, last name, Google-verified email, WhatsApp-verified mobile, market experience, profession, legal/consent acknowledgements. Optional: DOB and city/location. No full address.

Market experience: New to stock markets; Beginner; Intermediate; Experienced; Advanced/Professional.
Profession: Salaried/Employee; Business Owner; Self-employed/Freelancer; Trader; Investor; Finance Professional; Student; Retired; Homemaker; Other.

## 9. Navigation — Q78
1. Home — Overview, Important alerts, Active strategies, Account status
2. Strategies — My Strategies, Create Strategy, Strategy Builder, Live Strategies, Adjustments, Completed Strategies
3. Positions — Current positions, Strategy-linked positions, Adjustment opportunities, P&L/risk
4. Market — Option Chain, Underlying/index view, Market context
5. Orders — Pending, Executed, Failed/partial, Execution history
6. Alerts — Active, History, Notification settings
7. Learn — Strategy education, Options concepts, Platform guidance

Profile/avatar → Account & Settings: Profile, Zerodha connection, Subscription & Billing, Free Eligibility, Referrals, Notifications, Security, Preferences.

## 10. Zerodha connection — Q79–Q80
**Q79 = A:** Connection completely optional until a broker-dependent function is needed: execution, live positions/orders/account data, or direct-customer eligibility.

Contextual prompt: “Connect your Zerodha account to continue. We’ll use your Zerodha account to verify availability, check margin and prepare/execute your strategy.”

**Q80:** Open Home/dashboard directly after onboarding; no forced connection.

Zerodha authorization/session lasts about 24 hours and requires daily reauthentication. This is session expiration, not identity deletion. Same Client ID reconnecting restores the same association and does not create a new trial.

## 11. Q82–Q97 identity/anti-abuse/trial lifecycle
- **Q82 = C:** Same Zerodha Client ID on second Gmail/platform account: block normal second independent access; offer legitimate recovery/transfer; no second trial.
- **Q83 = D:** Hybrid transfer: straightforward legitimate cases may auto-complete after verification; suspicious/repeated cases Admin review.
- **Q84 = A:** One Zerodha Client ID → one platform account at a time; no family/business sharing in V1.
- **Q85 = A:** Email can change within same platform account; preserve Platform User ID, Zerodha association, trial, entitlements, strategies/history/referrals.
- **Q86 = A:** Old email immediately stops being login identifier; retain only in security/audit history.
- **Q87 = A:** V1 does not attempt to identify one human across multiple legitimate Zerodha accounts; basic anti-abuse only.
- **Q88 = A:** Trial begins at successful registration.
- **Q89 = A:** Active strategies continue monitoring after Pro expiry.
- **Q90 = A:** Paid Pro expiry uses same Limited/Read-Only model; no special V1 grace period.
- **Q91 = A:** Live/detailed Option Chain unavailable in Limited/Read-Only.
- **Q92 = A:** Option Chain can be shown behind Pro gate with static/sample preview clearly labelled Sample/Not Live.
- **Q93 = A:** Historical records/results accessible indefinitely; new simulations remain Pro.
- **Q94 = A:** Disconnecting Zerodha does not delete/close strategy. Strategy/history remain; live positions/orders/margin/execution unavailable until reconnect.
- **Q95 = A:** Same Client ID reauthentication restores existing association; no new trial/customer/entitlement.
- **Q96 = A:** Account deletion retains only minimal anti-abuse/entitlement record needed to prevent trial reset, subject to privacy/retention policy; do not retain whole deleted account solely for this.
- **Q97 = A:** If Zerodha never connected, trial history is tied to platform account; another unlinked account may receive its own trial; no aggressive fingerprinting.

## 12. Home — Q81
Q81 is the latest conversational continuation point referenced by the user.

Proposed Home:
- Welcome, [Name]
- Create a Strategy
- Explore Option Chain
- Learn
- 7-day Pro trial status
- “I already know my strategy” quick path
- Active strategies
- Important alerts
- Account status

No forced Zerodha connection; connect contextually when a broker-dependent feature is selected.

**Treat Q81 as the next decision to confirm if still unresolved. Do not jump back to Q33A.**

## 13. Positions/adjustment engine
Positions are strategy/risk objects, not merely a broker positions table.

Model:
**Strategy + Current Market + Time + P&L + Greeks + Position geometry + User Rules → Trigger → Candidate Adjustment → Before/After Analysis → User Decision**

WHEN examples: underlying moves X points/reaches level; distance from short strike/breakeven; leg reaches profit threshold; strategy reaches max-profit/loss threshold; Greek thresholds; IV change/percentile; DTE; premium; P&L; compound AND/OR.

DO examples: take profit, close/roll leg, roll spread, move strike, add/remove hedge/leg, change quantity, re-center, convert strategy, exit, alert/no trade proposal.

UI should show current strategy, exact trigger, current conditions, proposed adjustment, before/after legs, P&L/risk/margin/payoff/breakevens and “Why am I seeing this?” tied to the user's rule.

The platform does not decide a universally correct adjustment. Adjustments can increase risk. Personalized adjustment logic may require SEBI/legal review.

## 14. Strategy modification
Modify live strategy → proposed leg changes → recalculate max P/L, breakevens, current P/L, margin, charges, risk → Before/After → prepare adjustment orders → confirm → execute.

## 15. Entry/exit
Entry V1: immediate, market level/range, premium target, volatility condition, time window. Same rule engine should power entry, adjustment, exit and future controlled automation.

Exit V1: profit target, max loss, time exit, underlying level. Action = alert + prepare exit orders. Every strategy has an explicit exit plan.

## 16. Strike selection
Modes: Conservative, Balanced, Aggressive, Manual Custom.
Potential inputs: spot, expiry, premiums, IV, expected move, capital, max loss, desired premium.
Use “Suggested setup”, not “Recommended trade”. Manual override remains.

## 17. Historical simulation
V1 = simple historical strategy simulation, not full quant backtesting.
Metrics: best/worst, winning days, drawdown, historical behavior. Clearly label simulation/historical behavior and do not imply future guarantee.

## 18. P&L/scenario table
Every user, including beginners, sees the outcome view.

Single horizontally scrollable table columns:
1 Leg
2 Action
3 Instrument
4 Expiry
5 Strike
6 Quantity
7 Entry Price
8 LTP
9 Entry Value
10 Current Value
11 Unrealized P&L
12 P&L %
13 IV
14 Delta
15 Gamma
16 Theta
17 Vega
18+ scenario market levels
Then strategy-level lower breakeven, upper breakeven, status.

Sticky left columns; current market highlighted; scenario cells are formula-driven and never blank. Default scenario levels are centered around current underlying, roughly ₹100 spacing, with about 1,000–2,000 points of range where appropriate.

Expiry formulas:
- BUY CALL = [MAX(Market - Strike, 0) - Entry Price] × Qty
- SELL CALL = [Entry Price - MAX(Market - Strike, 0)] × Qty
- BUY PUT = [MAX(Strike - Market, 0) - Entry Price] × Qty
- SELL PUT = [Entry Price - MAX(Strike - Market, 0)] × Qty

Strategy scenario P&L = sum of leg scenario P&Ls. Breakevens are strategy-level.

## 19. Iron Condor reference
- Buy 22,800 PE @ 42.50 ×75; LTP 38.20
- Sell 23,000 PE @ 86 ×75; LTP 72.50
- Sell 23,400 CE @ 91.50 ×75; LTP 78
- Buy 23,600 CE @ 44 ×75; LTP 39.50

Live P&L +₹1,365; net credit ₹6,825; max profit ₹6,825; max loss ₹8,175; approximate BEs 22,909 and 23,491.
Scenario: 22,000–22,800 = -₹8,175; 22,900 = -₹675; 23,000–23,400 = +₹6,825; 23,500 = -₹675; 23,600–24,000 = -₹8,175.

## 20. Live monitoring
Monitor P&L, underlying, distance from BEs/short strikes, DTE, IV, Greeks, margin utilization, entry/adjustment/exit conditions.

Statuses:
- Green — Healthy
- Yellow — Watch
- Orange — Adjustment opportunity
- Red — Exit condition reached

V1 is rule-based, not predictive.

## 21. Notifications
Channels: in-app, push, email, WhatsApp.
Info → in-app.
Watch → in-app + push.
Action opportunity → push + in-app + possibly WhatsApp.
Exit/risk/order failure → push + email + WhatsApp + in-app.

Still to finalize: provider, consent, quiet hours, templates, escalation, dedupe, rate limits, audit, retry.

## 22. Execution
V1: alert + prepare exact multi-leg orders; user reviews/executes. Future controlled automation.

Before order workflow: validate margin through Zerodha/broker margin availability check. Zerodha is final authority for contract validity, margin and order acceptance/execution state.

Use dependency-aware sequencing. Protective/buy legs may need to be established before shorts; do not blindly hard-code all buys first for every strategy.

Partial failure priority:
1. Complete Strategy
2. Retry Failed Leg
3. Review Manually
4. Close Partial Strategy

Do not automatically unwind successful legs by default. Re-fetch positions/order status, recalculate remaining strategy, re-check margin and verify missing leg before completion.

Still to finalize: partial-fill state machine, pricing, order types, per-leg prices, tick rounding, retry/repricing/slippage, timeout/cancel, MIS/NRML, expiry/multi-expiry details, auth/security, quantity edge cases, existing-position reconciliation.

## 23. Existing positions
On Zerodha connection, fetch open positions and identify possible multi-leg structures. User may add to existing strategy, create new strategy, or leave standalone. Once grouped, monitor as strategy.

Grouping/reconciliation rules remain open.

## 24. Responsive web
Responsive web Day 1. Desktop optimized for construction/Option Chain/analysis/wide tables/payoff. Mobile optimized for alerts/monitoring/P&L/review/execution. No native app initially.

## 25. Open areas
Still requiring future questions: exact market-data vendor/licensing/update frequency/historical source; current-vs-expiry P&L modeling; pricing/IV/time-value/bid-ask/slippage/charges; builder UX; execution details; position reconciliation; adjustment rule priority/conflicts/cooldowns/audit; alert providers/consent; SEBI/legal review; Admin screens and system health.

## 26. Question tracker
Exact Q1–Q32 wording is not reliably retained here; rely on the previous handoff for those historical questions and their outcomes.

Reliable later records:
- Q33A appears in an older continuation marker and is **not** the current continuation point.
- Q43–Q57 Option Chain: locked as above.
- Q58–Q59: public/live data.
- Q61/Q63/Q64/Q66: referral/commercial/payment.
- Q70: Admin eligibility.
- Q72/Q73: WhatsApp OTP and Google email verification.
- Q74/Q75: optional DOB/city.
- Q76/Q77: market experience/profession.
- Q78: navigation.
- Q79/Q80: Zerodha timing.
- Q81: Home/Dashboard — latest conversational point.
- Q82–Q97: identity/trial/entitlement/session/anti-abuse lifecycle decisions.

## 27. Exact continuation instruction
**Start from Q81 / the latest unresolved conversational state.**

Do not restart. Do not revisit Q33A. Do not ask already-answered questions. Ask one question only, give a recommendation, wait for the answer, then record the decision before proceeding.

### Quick project summary
V1 = NIFTY + SENSEX, Zerodha only, strategy-first, Call/Put/Futures Buy/Sell, Strategy Builder, Option Chain, P&L/payoff/scenario analysis, monitoring, rule-based adjustment opportunities, controlled execution, historical simulation, alerts, learning, 7-day Pro trial, ₹600/month Pro, complimentary Pro for qualifying Zerodha customers, 1-month referral rewards, Razorpay, Google login + WhatsApp OTP, contextual Zerodha authentication, Limited/Read-Only after expiry, persistent strategies/history, Entitlement Engine, anti-abuse identity model, and vendor-independent market-data architecture.

**Core promise: Plan the trade. Follow your strategy. Then execute.**
