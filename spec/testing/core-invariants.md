# Core invariants and required failure tests

Decisions: ADR-030 and the ADRs cited per row. Sources: comprehensive handoff §93; implementation control §7, §11,
§12, §21. Every invariant below becomes at least one automated test before the feature it guards ships.

## 1. Domain invariants (handoff §93)

| # | Invariant | ADR |
|---|---|---|
| 1 | Every executed trade belongs to a strategy. | 002 |
| 2 | A strategy has a version. | 019 |
| 3 | A proposed version is not active until confirmed, executed and reconciled. | 019 |
| 4 | Order submission ≠ execution. | 017 |
| 5 | Broker state is authoritative for actual positions. | 016, 018 |
| 6 | An unresolved reconciliation mismatch blocks new execution and adjustment execution. | 018 |
| 7 | No automatic order retry in V1. | 017 |
| 8 | No silent contract substitution. | 007, 016 |
| 9 | No silent strategy redesign when live data arrives. | 020 |
| 10 | Connecting Zerodha never auto-activates a strategy. | 020 |
| 11 | Strategy creation does not require a Zerodha connection. | 020 |
| 12 | Disconnecting Zerodha does not delete strategy or history. | 020 |
| 13 | Active strategies keep monitoring after Pro expiry. | 023 |
| 14 | Limited users cannot access the live detailed Option Chain. | 023 |
| 15 | Shared market calculations are not duplicated per user. | 012 |
| 16 | Rule triggers record their exact triggering values. | 019 |
| 17 | The strategy timeline is append-only. | 019 |
| 18 | Important exception states explain what happened and the next action. | 019 |
| 19 | Advanced UX cannot bypass safety controls. | 004 |
| 20 | Production deployment requires explicit owner authorization. | 030 |

Added at import from the 15 Sep handoff: 21 — if a protective leg fails, its dependent sell leg is not submitted
(ADR-017). 22 — scenario values match `spec/business-rules/scenario-calculations.md` §6 exactly (ADR-008).

## 2. Failure paths that must be tested (implementation control §11)
Broker disconnect · expired broker session · invalid contract · unavailable contract · insufficient margin · order
rejection · partial fill · external position change · stale market data · duplicate contract · strategy mismatch ·
entitlement expiry · notification failure.

## 3. UI verification (implementation control §12)
Every meaningful UI change is verified with screenshots at desktop and mobile widths, covering the loading, empty,
error, blocked and active states, and the reconciliation state where relevant. Compiling is not done.

## 4. Verification gate before parallel work (implementation control §7)
Domain (versioning, transitions, rules, timeline) · calculations (payoff, P&L, breakevens, max P/L, scenario
table) · broker (connection, margin, submission, status, positions) · execution (dependencies, partial, no
auto-retry, no silent unwind) · reconciliation (mismatch, external change, manual, block) · UI (screenshots,
responsive, strategy-only controls, error states). Also (M §92 Phase 3; audit S-MASTER-§92): unit and integration
tests pass; security checks — each REQ-063 boundary has a test (no API places an order outside a strategy or
bypasses a reconciliation block; vendor credentials never reach the browser; the Zerodha access token is stored only
through the official token mechanism, encrypted at rest and never logged — best practice, the legacy stored it in
plaintext), plus a dependency-vulnerability scan and a secret scan with no open high finding (best practice).

## 5. Definition of done (implementation control §21; audit S-IMPL-§21)
A work item is done only when: 1 code implemented; 2 its tests pass (`tests_required`, CI); 3 the relevant failure
paths in §2 are tested; 4 the §1 invariants still pass; 5 UI screenshot-verified per §3 where UI changed; 6 no
`spec/decisions/` row violated (Spec-deviation block, class none/1/2 only); 7 spec, work item and status updated;
8 the change is reviewable (one work item per PR, verifier evidence in `evidence/<W-id>/`); 9 no production change
(production only per REQ-067 AC-6).
