# Claude Code Implementation Control --- Indian Index Options / F&O SaaS

Version: 2026-09-28 Use with: CLAUDE_CODE_MASTER_HANDOFF.md

## 1. PURPOSE

This file tells Claude Code HOW to implement the product handoff.

The Master Handoff tells Claude Code WHAT the product is and which
decisions are locked.

Do not replace the Master Handoff with this file.

------------------------------------------------------------------------

## 2. IMPLEMENTATION RULE

Do not restart product discovery.

The product-definition phase reached Q203.

Next product question is Q204 only when a genuine new product/business
decision is required.

------------------------------------------------------------------------

## 3. PHASE 0 --- DISCOVER BEFORE BUILDING

Inspect:

### Repository

-   directory structure
-   package manager
-   framework
-   database
-   migrations
-   APIs
-   frontend
-   backend
-   tests
-   deployment configuration
-   environment configuration

### Engineering Factory

Inspect existing: - skills - hooks - rules - agents/subagents -
workflows - scripts - verification tools - testing patterns - cloud
patterns - status/control-center tooling

### Legacy Project

Inventory: - reusable skills - hooks - rules - agents - workflows -
configurations - scripts - cloud-resource patterns -
testing/verification patterns - reusable domain utilities

Classify: - REUSE DIRECTLY - ADAPT - GENERALIZE - RETIRE

Migrate proven reusable capabilities into the Factory/Capability Library
where appropriate.

Do not recreate existing capability without first checking.

------------------------------------------------------------------------

## 4. PHASE 1 --- DOMAIN FOUNDATION

Prioritize the core domain.

Build and verify:

-   Strategy
-   Strategy Version
-   Strategy Leg
-   Strategy Rules
-   Entry Rules
-   Adjustment Rules
-   Exit Rules
-   Risk Limits
-   Strategy State
-   Strategy Activity Timeline
-   Audit Events
-   Market Instrument/Contract
-   Market Data abstraction
-   Broker abstraction
-   Order
-   Execution Plan
-   Execution Step
-   Broker Position
-   Strategy Position
-   Reconciliation
-   Entitlement foundation

Core invariants must be encoded as tests.

------------------------------------------------------------------------

## 5. PHASE 2 --- CALCULATION FOUNDATION

Create a centralized calculation engine.

Must support: - leg P&L - strategy P&L - expiry payoff - max profit -
max loss - breakevens - current value - unrealized P&L - P&L % - Greeks
where applicable - margin planning interface - charges interface -
scenario calculations

Scenario calculations must exactly match the product handoff.

Do not duplicate payoff formulas across components.

------------------------------------------------------------------------

## 6. PHASE 3 --- CORE VERTICAL SLICE

Build:

Create Strategy → Configure Legs → Calculate P&L/Risk → Save Draft →
Connect Zerodha → Validate → Prepare Execution Plan → Review → Execute →
Confirm Broker Execution → Reconcile → Active Monitoring

Do not build every screen before this path works.

------------------------------------------------------------------------

## 7. PHASE 4 --- VERIFICATION GATE

Before broad parallelization, verify:

### Domain

-   strategy versioning
-   state transitions
-   rules
-   audit timeline

### Calculations

-   payoff formulas
-   P&L
-   breakevens
-   max profit/loss
-   scenario table

### Broker

-   connection
-   margin
-   order submission
-   order status
-   position retrieval

### Execution

-   dependencies
-   partial execution
-   no auto-retry
-   no silent unwind

### Reconciliation

-   mismatch detection
-   external broker changes
-   manual reconciliation
-   execution block

### UI

-   screenshots
-   responsive layouts
-   strategy-only controls
-   error states

------------------------------------------------------------------------

## 8. PHASE 5 --- PARALLEL WORK

Only after the core is stable.

Parallelize bounded domains such as: - market data - option chain -
strategy builder UI - monitoring - notifications - entitlement/billing -
admin - learn - responsive UX

Do not allow parallel agents to redefine: - Strategy semantics -
execution invariants - state machine - calculation formulas -
reconciliation authority

------------------------------------------------------------------------

## 9. WORKTREE RULE

When parallel work is useful: - use separate worktrees/branches - one
bounded domain per worktree - clear ownership - no uncontrolled shared
edits - merge only after tests pass

Before merging: - run relevant tests - resolve schema/domain conflicts
centrally - verify product invariants - verify screenshots where UI
changed

------------------------------------------------------------------------

## 10. CLAUDE CODE DECISION RULE

Proceed autonomously when: - the handoff is explicit - implementation
choice does not alter product behavior - the choice is reversible -
existing architecture supports it

Ask the owner when: - two locked requirements conflict - a business rule
is genuinely missing - compliance/legal interpretation changes product
behavior - licensing changes what can legally be displayed/used -
production deployment is requested - destructive migration has
irreversible consequences

Do not ask about ordinary implementation details that can be decided by
engineering judgment.

------------------------------------------------------------------------

## 11. TESTING RULE

Test both: - happy paths - failure paths

High-priority failure tests: - broker disconnect - expired broker
session - invalid contract - unavailable contract - insufficient
margin - order rejection - partial fill - external position change -
stale market data - duplicate contract - strategy mismatch - entitlement
expiry - notification failure

------------------------------------------------------------------------

## 12. UI VERIFICATION RULE

Any meaningful UI change must be verified with screenshots.

Verify: - desktop - mobile - loading - empty state - error state -
blocked state - active state - reconciliation state where relevant

Do not mark UI work complete merely because the code compiles.

------------------------------------------------------------------------

## 13. MARKET DATA RULE

Browser: - never connects directly to vendor - never contains vendor
credentials - never owns authoritative market logic

Architecture:

Vendor → Gateway → Normalization → Cache/Event Stream → Engines →
WebSocket → Browser

Provider must be replaceable.

V1 interim: - Zerodha live data - user-guided API connection -
historical data deferred

But verify current Zerodha terms/permissions before production use.

------------------------------------------------------------------------

## 14. BROKER RULE

Zerodha is authoritative for: - account - positions - orders -
execution - current eligibility - margin - actual execution state

Do not recreate full broker RMS.

Broker response wins.

------------------------------------------------------------------------

## 15. EXECUTION SAFETY RULE

Never: - auto-retry V1 orders - silently substitute contracts - silently
redesign a strategy - treat submitted as executed - execute while
reconciliation mismatch exists - bypass strategy-only execution

Partial execution must become explicit state.

------------------------------------------------------------------------

## 16. DATA SCALE RULE

Design for: - 5k--6k users - 100k+ - potentially 500k

Shared calculations should be shared.

Do not: - create one vendor stream per user - calculate identical market
metrics independently for every user - store unnecessary tick history
for every option

------------------------------------------------------------------------

## 17. RESOURCE EFFICIENCY

Use the right model for the task.

Prefer: - cheaper/faster models for simple implementation - stronger
reasoning for architecture/debugging/security/high-risk changes

Batch changes.

Avoid: - repeated test runs for trivial edits - token-heavy status
updates - unnecessary agent duplication - repeated repository
rediscovery

------------------------------------------------------------------------

## 18. STATUS CONTROL CENTER

Maintain a concise project control-center artifact.

Track: - feature - spec/story/task - owner/agent - status - dependency -
blocker - verification - screenshot - commit/branch where useful

Keep updates compact.

------------------------------------------------------------------------

## 19. DOCUMENTATION

Important decisions should be recorded.

Use: - ADRs for architectural decisions - changelog for meaningful
implementation changes - strategy activity model for runtime events -
audit log for security/commercial/admin events - control center for
project status

Do not create documentation purely for volume.

------------------------------------------------------------------------

## 20. PRODUCTION

Production is owner-controlled.

Claude Code may: - prepare - test - validate - generate release notes -
generate deployment plan

Claude Code must stop before actual production deployment unless the
owner explicitly authorizes that deployment.

------------------------------------------------------------------------

## 21. DEFINITION OF DONE

A task is done only when:

1.  Code is implemented.
2.  Tests pass.
3.  Relevant failure cases are tested.
4.  Domain invariants remain intact.
5.  UI is screenshot-verified if applicable.
6.  No locked product decision was violated.
7.  Documentation/status is updated where needed.
8.  Changes are reviewable.
9.  No accidental production change occurred.

------------------------------------------------------------------------

## 22. FIRST COMMAND / FIRST JOB

First inspect, do not build.

Produce: 1. repository map 2. current stack 3. existing implementation
map 4. Engineering Factory capability inventory 5. legacy capability
inventory 6. reusable/adapt/generalize/retire classification 7. current
gaps against Master Handoff 8. proposed implementation sequence 9. first
vertical-slice task

Then begin implementation.

END OF IMPLEMENTATION CONTROL
