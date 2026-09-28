# Build plan: night of 2026-09-29 (owner away, ADR-045)

**Core:** the one calculation engine (ADR-008, REQ-033) — every P&L, scenario, breakeven and table number depends on it.
**Proof:** the engine reproduces the spec's golden Iron Condor exactly (scenario-calculations.md §6), and the
instrument catalogue parses Zerodha's real public instrument list (NIFTY gap 50 / lot 65, SENSEX gap 100 / lot 20).

The Zerodha live-data core (docs/HANDOVER.md NEXT) stays blocked: it needs the owner's Kite credentials and Zerodha's
written answer (ADR-034).

## Rules for tonight
- One work item links one requirement (evidence is keyed `evidence/<W-id>/<AC-id>.md`; guarded by
  `tests/test_spec_integrity.py`).
- Engine and domain code use the Python standard library only (plus PyYAML): CI installs only
  `pyyaml jsonschema pytest` and its workflow is a kit file.
- Loop per item (`.claude/skills/deliver/SKILL.md`): builder in its own worktree → verifier (fresh context, Tier B/A)
  → evidence written by the orchestrator → trace check → PR → `merge_when_green.py`. Tier A adds an adversarial
  review and mutation tests.
- Legacy code: copy/adapt with provenance per `spec/technical-design/legacy-reuse.md` (ADR-043).

## Waves
| Wave | Work items | Tier | Depends on |
|---|---|---|---|
| 1 | W-001 engine core (REQ-033) · W-006 instrument catalogue (REQ-053) · W-007 entitlement engine (REQ-017) | B · B · A | — |
| 2 | W-002 engine inputs/Greeks (REQ-032) · W-005 templates (REQ-028) · W-008 access policy (REQ-018) · W-009 referrals (REQ-021) | B · B · A · A | W-001 / W-007 |
| 3 | W-003 scenario levels (REQ-034) | B | W-001, W-002 |
| 4 | W-004 strategy table model (REQ-035) | B | W-003 |
| later | API (FastAPI) and frontend (Vue) work items — need a project CI workflow that installs them (owner/kit question) | | |

## Not tonight
Live Zerodha data, orders/execution, OTP sending, payments, anything production. Open owner items are listed in
`docs/owner-review-2026-09-30.md`.
