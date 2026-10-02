# Builder brief: W-052 PostgreSQL store for the hash-chained audit log

Core: audit events written to PostgreSQL reload into `ofo.audit.AuditLog.from_events` and `verify()` passes; one changed
byte in any stored row makes verification fail.
Proof (step 1, real PostgreSQL, as the application role): append 3 events (one with a Decimal and a datetime in its
payload); open a new connection, reload, `verify()` passes and every hash equals the in-memory one; as the owner change
one payload value, reload, verification fails naming that row; two concurrent appends produce one linear chain.

Why Opus: Tier A; append-only storage whose hashes must recompute byte for byte, plus concurrency.
Budget: 60 min wall-clock, 80 tool calls. At budget, stop and report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`).
Tier: A.

## Spec basis
- REQ-064 AC-2: "Audit and timeline records are append-only."
- REQ-063 AC-5: "Audit and other stored payloads use a per-event-type field ALLOWLIST (each event type declares the
  fields it may carry; anything else is dropped before storage), never a list of forbidden key names"
- ADR-048 and the W-051 base: role `ofo_app`, schema-qualified tables, column-level INSERT grants, no TEMPORARY.
- ADR-047: Copy from: none - algochanakya has no hash-chained audit log (legacy-reuse.md M9). Follow our own
  `backend/ofo/audit/models.py` (canonical JSON, `$decimal`/`$datetime` tags, GENESIS_HASH) and `log.py` (HeadAnchor,
  `verify`, `from_events`).

## Design (required)
- Table `public.audit_events`: `seq BIGINT PRIMARY KEY` (assigned under the lock, gap-free), `event_type TEXT`, `actor
  TEXT`, `timestamp TIMESTAMPTZ`, `correlation_id TEXT`, `payload JSONB` in the canonical tagged form, `previous_hash
  TEXT`, `hash TEXT`, `recorded_at TIMESTAMPTZ` stamped by the W-051 trusted-clock pattern (trigger), with the same
  owner/grant model as `ledger_entries` (SELECT + column INSERT only for `ofo_app`).
- The event's own `timestamp` must lie within the 60 s window of `recorded_at` (ADR-023 Q256): reuse the W-051 trigger
  function or a sibling with the same rule, not a copy of the constant.
- Appends take `pg_advisory_xact_lock(<fixed key>)`, read the head, compute the hash with `ofo.audit` code, insert, and
  update the anchor in the same transaction.
- Anchor table `public.audit_anchor` (count, last_hash), separate from the events: `ofo_app` may change it only through
  a SECURITY DEFINER append function owned by the owner role (search_path pinned), never by direct UPDATE.
- Allowlist: a registry `event type -> allowed payload fields` in `backend/ofo_app/audit_allowlist.py`. Fields not in the
  list are dropped before the hash is computed. An event type with no entry is REFUSED (fail closed). Declare entries
  only for: ENTITLEMENT_CHANGED, TRIAL_STARTED, TRIAL_EXPIRED, DIRECT_CUSTOMER_ELIGIBILITY_GRANTED,
  DIRECT_CUSTOMER_ELIGIBILITY_REVOKED, REFERRAL_REWARD_GRANTED, SUBSCRIPTION_STARTED, SUBSCRIPTION_EXPIRED,
  ADMIN_CHANGE_RECORDED; choose their fields from how `backend/ofo/admin/qualifying.py` and the entitlement domain use
  them, and list them in the module docstring. Broker, order, execution, reconciliation and session event types stay
  undeclared (W-017).
- Reload: `load_log(session) -> AuditLog` via `AuditLog.from_events` and the stored anchor; any mismatch raises
  `AuditChainError`.

## Migration and allowlist (from W-051, merged in PR #102)
- New migration revision id 0002_audit_store with down_revision 0001_baseline, owner-run like 0001.
- Extend the W-051 allowlist function `public.ofo_assert_app_role_allowlist` (CREATE OR REPLACE in 0002) so its `post`
  phase also asserts the exact privileges on `audit_events`, `audit_anchor` and any sequence/function you add (finding
  `privilege-guard-as-denylist`: every new append-only table must be in the allowlist). Run it at the end of 0002.
- Reuse the 0001 trigger pattern for the clock; do not duplicate the 60 s constant (call or share the 0001 function).

## Tests (tests_app/test_audit_store.py, real PostgreSQL; skip with reason without TEST_DATABASE_URL; CI requires them)
- The proof steps above, each its own test.
- Allowlist: an extra field is dropped before storage (and the hash covers the stored form); an undeclared type is
  refused with no row written.
- Truncation: the owner deletes the last row; reload with the anchor fails.
- Mutation tests with `pytest.raises(AssertionError, match=...)`: remove the advisory lock (concurrency test goes red);
  grant UPDATE on audit_anchor to ofo_app (anchor test goes red).

## Standing items (run-discipline B4)
- Fail closed on any event type, payload shape or tag the store cannot round-trip.
- Decimal stays exact: `1365.00` must not come back as `1365.0` (the hash would change); a test proves it.
- Kit CI stays green: nothing under `tests/` imports app packages; `backend/ofo/` unchanged unless a pure helper is
  needed (then with its own stdlib test).

## Rules
- Work only in your worktree (branch from origin/main after W-051 merged). Do not edit kit files. Never write
  `evidence/`. No secrets; CI dummy passwords contain the word dummy or test.
- Run the domain suite and `python -m pytest -c pytest-app.ini -q` before finishing (DB tests skip locally; say so).
- Commit; do not push.
