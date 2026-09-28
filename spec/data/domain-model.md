# Domain model

Decisions: ADR-002, ADR-019, ADR-016–ADR-018, ADR-023. Source: comprehensive handoff §5, §11, §12, §46, §51, §75,
§83. Persistence technology is an implementation choice (§75).

## 1. Central object
**Strategy, not Order.** Strategy → Legs → Entry Conditions → Risk → Adjustment Plan → Exit Plan → Execution Plan
→ Orders → Monitoring → Completion. Orders are execution artifacts that belong to a strategy.

## 2. Strategy Definition vs Live Market State (Q189) — two objects, never one

| Strategy Definition (versioned, stable) | Live Market State (changes continuously) |
|---|---|
| underlying, expiry, legs, strikes, Buy/Sell side, quantities | spot, futures, LTP, bid/ask, volume, OI, OI change |
| entry, adjustment and exit rules | IV, Greeks, current P&L, margin, charges |
| risk limits, user preferences/constraints | distances (to strikes, breakevens), trigger state, timestamps, data health |

## 3. Versions (Q190, Q191)
- Every change to a definition creates a new version; old versions are kept.
- **Active** version = the accepted state. **Proposed** version = separate; it becomes active only after user
  confirmation and successful execution/reconciliation.
- Partial execution → exception/reconciliation state; the broker's actual state wins.
- A contract that becomes unavailable stays in the version history; changing it creates a new proposed version
  (§81).

## 4. Entities the code must model explicitly (§75)
User · Identity · Mobile Verification · Zerodha Connection · Entitlement · Strategy · Strategy Version · Strategy
Leg · Strategy Rule · Entry Rule · Adjustment Rule · Exit Rule · Strategy Risk Limits · Strategy Live State · Market
Instrument · Contract · Market Tick/Quote · Aggregated Market Data · Order · Execution Plan · Execution Step · Broker
Position · Strategy Position · Reconciliation Event · Adjustment Opportunity · Adjustment Proposal · Alert ·
Notification · Strategy Activity Event · Audit Event.

## 5. Separate state dimensions (§83) — never substitute one for another
| Dimension | Values | Source |
|---|---|---|
| Strategy operational state | the 12 states in §6 | ADR-019 (Q200) |
| Monitoring status | Green Healthy · Yellow Watch · Orange Adjustment opportunity · Red Exit condition reached | ADR-010 (Q144) |
| Order state | Prepared · Submitted · Pending · Partially Executed · Executed · Rejected · Cancelled | ADR-017 (Q194) |
| Entitlement | Trial Pro · Direct Zerodha Customer Pro · Referral-earned Pro · Paid Monthly/Annual Pro · Expired/Limited | ADR-023 |
| Broker session | connected · expired · disconnected | ADR-020 |
| Market data health | available · stale · delayed · unhealthy · unavailable | ADR-015 (Q184) |

Valid combinations include: Pro + broker disconnected; Limited + monitoring an Active strategy; Active strategy +
expired Zerodha session; Reconciliation Required + active subscription.

## 6. Strategy operational states (Q200) and a PROPOSED transition table
States (locked): Draft · Ready for Validation · Validated · Active · Monitoring Paused · Adjustment Proposed ·
Execution in Progress · Partially Executed · Reconciliation Required · Completed · Exited · Archived.

The handoff locks the states but gives **no transition table**. The table below is a **proposal for owner review**,
not a decision; it follows the locked rules (explicit transitions, submitted ≠ executed, mismatch blocks execution).

| From | To | Trigger |
|---|---|---|
| Draft | Ready for Validation | user submits for validation |
| Ready for Validation | Validated / Draft | validation passes / fails (with reasons) |
| Validated | Execution in Progress | user confirms Execute Strategy |
| Execution in Progress | Active | every leg confirmed executed by the broker and reconciled |
| Execution in Progress | Partially Executed | some legs executed, some failed/rejected |
| Partially Executed | Execution in Progress / Reconciliation Required / Exited | user chooses complete or retry / review / close partial |
| Active | Adjustment Proposed | user starts a modification, or accepts a detected opportunity to review |
| Adjustment Proposed | Execution in Progress / Active | user confirms / discards the proposal |
| Active | Monitoring Paused / Active | data or broker session unavailable / restored |
| any live state | Reconciliation Required | broker state differs from platform state |
| Reconciliation Required | previous live state | mismatch resolved (auto or explicit manual reconciliation) |
| Active | Exited | exit orders confirmed executed |
| Active | Completed | all legs expired or closed at expiry |
| Completed / Exited / Draft | Archived | user archives |

## 7. Activity timeline and trigger audit (Q202, Q203)
- Every strategy has an append-only timeline of `Strategy Activity Event`s (events listed in ADR-019).
- Every rule trigger stores: rule id, exact input values, threshold, timestamp, market-data source, data health,
  active strategy version, and what followed (alert, order prepared, confirmation, execution, broker report,
  reconciliation result).
