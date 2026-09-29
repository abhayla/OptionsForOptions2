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
- Before the first execution, definition changes are activity-history entries with restore (Q135, T2 #86), not
  versions. From the first execution on, every meaningful modification creates a new version; old versions are kept
  (Q190, T2 #128; ADR-019 "versions after execution").
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
| Strategy health (monitoring status) | Green Healthy · Yellow Watch · Orange Adjustment opportunity · Red Exit condition reached — the owner-chosen health scale (Q20 = B, T1 #40–#41); these four colours mean health only | ADR-010 (Q20, T1 #41) |
| Monitoring availability | active · paused, per strategy (Q184, T2 #124) — separate from strategy health; the 🟢/🔴 marks in ChatGPT's Q184 example and the 🔴 in Q199's *"Execution blocked"* (T2 #130) are illustrations, not the health colours; paused and blocked are text badges with their own icon, never a health colour: `⏸ Monitoring paused` (neutral), `🔒 Execution blocked — needs reconciliation` (neutral, plus a strategy-page banner with Reconcile). While paused the health dot is grey, labelled "Health unknown — no current data"; the last colour is never shown as current. Every colour has a text label (delegated overnight, joint decision of two independent reviewers (ADR-045), audit C-9) | ADR-015, ADR-018 |
| Order state | Prepared · Submitted · Pending · Partially Executed · Executed · Rejected · Cancelled | ADR-017 (Q194) |
| Entitlement | Trial Pro · Direct Zerodha Customer Pro · Referral-earned Pro · Paid Monthly/Annual Pro · Expired/Limited | ADR-023 |
| Broker connection | four separate statuses (Q181, T2 #124): account connection · live market data · position/account sync · order-execution readiness, each Connected · Partially connected · Disconnected. The Zerodha authorization session itself is valid · expired (expires every morning, owner T1 #265); expiry is not identity loss | ADR-020, ADR-022 |
| Market data health | available · stale · delayed · unhealthy · unavailable | ADR-015 (Q182, T2 #124: never use stale data as live; the five-value list itself comes only from the handoff C-file) |

Valid combinations include: Pro + broker disconnected; Limited + monitoring an Active strategy; Active strategy +
expired Zerodha session; Reconciliation Required + active subscription.

## 6. Strategy operational states (Q200) and the transition table (owner-approved Q240)
States (locked): Draft · Ready for Validation · Validated · Active · Monitoring Paused · Adjustment Proposed ·
Execution in Progress · Partially Executed · Reconciliation Required · Completed · Exited · Archived.

The handoff locks the states but gave no transition table. The table below was proposed by the orchestrator and
**approved by the owner on 2026-09-29 (Q240)** with two fixes: Reconciliation Required is left only by an explicit
manual resolution (Q222), and Monitoring Paused is entered and left only by the user. It follows the locked rules
(explicit transitions, submitted ≠ executed, mismatch blocks execution).

| From | To | Trigger |
|---|---|---|
| Draft | Ready for Validation | user submits for validation |
| Ready for Validation | Validated / Draft | validation passes / fails (with reasons) |
| Validated | Execution in Progress | user confirms Execute Strategy |
| Execution in Progress | Active | every leg confirmed executed by the broker and reconciled |
| Execution in Progress | Validated | no leg filled and every order is finally rejected/failed; the rejection reasons are shown and the user may execute again or edit (Q243 fix 1) — this row is for a first ENTRY |
| Execution in Progress | Adjustment Proposed | an ADJUSTMENT whose every order is finally rejected/failed with nothing filled: the original version stays active, the proposal is kept with the rejection reasons, and the user may execute it again or withdraw it (Q245) |
| Execution in Progress | Partially Executed | some legs executed, the rest finally failed/rejected — even when the platform's intended legs differ from the fills; Reconciliation Required only if Zerodha's positions differ from the recorded fills (Q243 fix 4) |
| Partially Executed | Execution in Progress / Exited | user chooses complete or retry / close partial. "Review Manually" keeps Partially Executed and opens the review; it is not a transition (Q243 fix 2) |
| Active | Adjustment Proposed | user starts a modification, or accepts a detected opportunity to review |
| Adjustment Proposed | Execution in Progress / Active | user confirms / withdraws the proposal; a withdrawal is recorded in the version history (Q243 fix 3) |
| Active | Monitoring Paused | the user explicitly pauses monitoring of this strategy (Q240) |
| Monitoring Paused | Active | the user resumes monitoring of this strategy (Q240). A lost data feed or an expired Zerodha session does **not** change the strategy state: the strategy stays Active and its monitoring status shows paused ("Monitoring paused — reconnect Zerodha", Q182). Reason: REQ-043 AC-4 keeps monitoring status separate from this state machine, §5 allows Active + expired session, and the Zerodha session expires every morning (T1 #265), which would otherwise flip every Active strategy daily. Clarification recorded 2026-09-29 (audit item C-8). |
| any live state (Active, Monitoring Paused, Adjustment Proposed, Execution in Progress, Partially Executed — Q243 fix 5) | Reconciliation Required | broker state differs from platform state |
| Reconciliation Required | Active / Exited / previous live state | a recorded manual resolution on the latest run: **adopt → Active** on the adopted version, whatever the state before (Q247 — the adopted position is the strategy, nothing is left partial); a prepared closing order that executes, or broker flat → Exited; any other recorded resolution → the previous live state. An agreeing run alone never unblocks (Q222, Q240) |
| Active | Exited | exit orders confirmed executed |
| Active | Completed | all legs expired or closed at expiry |
| Completed / Exited / Draft | Archived | user archives |

## 7. Activity timeline and trigger audit (Q202, Q203)
- Every strategy has an append-only timeline of `Strategy Activity Event`s (events listed in ADR-019).
- Every rule trigger stores: rule id, exact input values, threshold, timestamp, market-data source, data health,
  active strategy version, and what followed (alert, order prepared, confirmation, execution, broker report,
  reconciliation result).
