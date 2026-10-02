# Builder brief: W-007 round 7 - entitlement engine on the trusted database clock (un-park issue #12)

Core: given a user's entitlement events, access(t) is computed correctly at every boundary (trial end, stacked referral
end, paid end), and every event's recorded-at time comes from the database clock, never the caller.
Proof (step 1): (a) domain - tests/entitlements/test_engine.py replays the spec examples (trial 7 days from
registration; Pro until 10 Oct + referral -> 9 Nov, as in work/W-007.md) and asserts access at each boundary second, mutation tests on the
boundary comparison; (b) database (CI, as ofo_app) - append a grant through the new store passing a caller time from
2020: the stored recorded_at is the database time; reload the history, access(t) is unchanged; lower a cap (e.g.
max_free_days 90 -> 30) and reload a legally built 7 + 30 + 30 history: it still loads and access is unchanged.

Why Opus: Tier A; six prior rounds and a parked third red of the class entitlement-ledger-accepts-out-of-domain-inputs (issue #12).
Budget: 60 min wall-clock, 80 tool calls. At budget, stop and report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`).
Tier: A.

## Spec basis
- REQ-017 AC-1..AC-5 (the requirement file) and ADR-023 rules 1-5.

- ADR-023 Q225: "a NEW entitlement event is checked against the current settings (caps,
  clock skew, no backdating, no post-dating). STORED history is loaded with integrity checks only (order, ids,
  references) and is never re-judged by today's settings"
- ADR-023 clarification: the recorded-at time "is stamped by the ledger from its own clock; a caller can never supply it."
- ADR-023 Q256: "the clock-skew window is 60 seconds, both ways."
- Issue #12 (parked): the two round-4 defects (post-dated status change accepted; stored history re-judged by today's
  settings) and the recommendation to separate validating a new event from loading stored history.

## Start from
- Branch `build/W-007-entitlements` @ a459ac0 (rounds 5-6: NewGrant/NewStatusChange, ledger-stamped recorded_at,
  stored-history loading). Merge current origin/main into it first (W-051..W-055 merged since); resolve conflicts.
- Copy from: none - algochanakya has no entitlement code (legacy-reuse.md M9).

## Design (required)
- Keep the domain engine standard-library in `backend/ofo/entitlements/` (kit CI runs `tests/`).
- New `backend/ofo_app/entitlement_store.py`: append each new entitlement event as a row in the W-051 trusted-clock
  ledger (`public.ledger_entries`, kind prefix `entitlement.`), sending event data and `event_at` but never
  `recorded_at`; the database stamps it and enforces the 60 s window. The domain's own clock seam is fed the stored
  `recorded_at` on load. Load = integrity checks only (order by id, ids, references), never today's caps or skew.
- Each new grant/status change also writes the matching audit event through the W-052 store (event types
  ENTITLEMENT_CHANGED, TRIAL_STARTED, TRIAL_EXPIRED, REFERRAL_REWARD_GRANTED, SUBSCRIPTION_STARTED, SUBSCRIPTION_EXPIRED,
  DIRECT_CUSTOMER_ELIGIBILITY_GRANTED/REVOKED - fields per backend/ofo_app/audit_allowlist.py), in the same transaction.
- Amend work/W-007.md in this PR: affected adds `backend/ofo_app/` and `tests_app/`; proof adds the database steps;
  status stays as the orchestrator sets it.

## Tests
- Domain (`tests/entitlements/`, stdlib): existing rounds' tests plus: a status change dated more than 60 s after its
  recorded-at time is refused (issue #12 defect 1); a 7 + 30 + 30 history loads after max_free_days drops to 30 (defect 2).
- App (`tests_app/test_entitlement_store.py`, real PostgreSQL, skip with reason locally): the proof (b) steps; a raw
  insert with a caller recorded_at gets the database time; the audit event is written in the same transaction (rolled
  back together on failure).
- Mutation tests with `pytest.raises(AssertionError, match=...)`: remove the upper-bound check on status changes;
  re-apply current caps on load - each turns its test red.

## Standing items (run-discipline B4)
- Fail closed on any stored row the loader cannot decode; name the row id.
- Expected values from the spec examples, never from running the code.
- Kit CI stays green: nothing under `tests/` imports app packages.

## Rules
- Work only in your worktree. Do not edit kit files. Never write `evidence/`. No secrets.
- Run the domain suite and `python -m pytest -c pytest-app.ini -q` before finishing (DB tests skip locally; say so).
- Commit; do not push. Report worktree path, branch, commits.
