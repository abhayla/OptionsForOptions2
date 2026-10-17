# Builder brief: W-103 Audit events on both order routes - order_prepared declared, broker replies and fills recorded (Tier A: audit allow-list guard + migration)

Core: on the ofo_test database, the Execute route's real ENTRY (strategy 1, plan 1, tag OFS1V1L0) writes ONE
`order_prepared` event {strategy_id, plan_number, action, tags} in the same transaction as `record_plan` (a refused
request writes none), and the return route on the 122104 replies writes `broker_response_recorded` for the order and
`execution_recorded` for each trade row of `GET /trades` with W-017's keys; the hash chain verifies after both.
Proof: the route tests' core sequence (`tests_app/test_execute_route.py`, `tests_app/test_execution_return.py`) on
ofo_test reads the audit table back and asserts the three event types, their payloads and the chain.

Tier: A. Model: opus.
Budget: 70 min wall-clock, 72 tool calls. HARD limit: at call 68 commit, push, report.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under 300 words, `git status --short` empty,
each new guard with its killing test (mutation-run).
Copy from: none - the allow-list (`backend/ofo_app/audit_allowlist.py`), the store (`backend/ofo_app/audit_store.py`)
and the migration pattern (`backend/ofo_app/alembic/versions/0015_audit_broker_allowlist.py`) exist; extend them.
Findings checked: guard-as-forbidden-list, privilege-guard-as-denylist, request-clock-for-database-stamped-fact, store-rule-enforced-per-call-site, fill-not-exactly-once, branch-migration-tests-move-shared-db, caller-supplied-verdict-trusted
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py

## Spec basis
- REQ-063 AC-5: "Audit and other stored payloads use a per-event-type field ALLOWLIST (each event type declares the
    fields it may carry; anything else is dropped before storage)"
- REQ-073 AC-3: "When the user returns from Kite, the platform reads the actual order states and positions from Zerodha and
  reconciles them"
- W-017 (`work/W-017.md`, REQ-063): `broker_response_recorded` = one Kite ORDER record; `execution_recorded` = one Kite
  TRADE record (the allow-list module's own docstring). Their meaning does not change.

## Build
1. Allow-list: declare `order_prepared` with exactly the fields strategy_id, plan_number, action, tags in the
   existing `ALLOWLIST` shape ("scalar" fields; the allow-list has no list type - store `tags` as ONE string, the
   plan's tags joined by "," (tags are alphanumeric, REQ-073 AC-2), unless you extend the allow-list's types with a
   killing test). Undeclared keys are DROPPED before storage, as REQ-063 AC-5 says ("anything else is dropped before
   storage") and `filter_payload` already does; do not change that rule. Migration `0017_audit_order_prepared` in the 0015 pattern updates the database copy of the
   allow-list, with a REAL downgrade (restores 0015's state; a test runs upgrade -> downgrade -> upgrade).
2. Execute route (`backend/ofo_app/routes/execute.py`): after `plans.record_plan(...)`, append `order_prepared` through
   `audit_store.append` on the SAME session/transaction (rolls back with the plan). Keep your edit to that spot only -
   another builder (W-102) edits `ExecuteOut` / `_answer` in the same file.
3. Return route (`backend/ofo_app/routes/execution_return.py`): per order read back by tag -> one
   `broker_response_recorded` (W-017 order keys); per trade row of `GET /trades` -> one `execution_recorded` (W-017
   trade keys), at most ONCE per trade_id across repeated returns (a replayed return writes nothing new - finding
   fill-not-exactly-once). Same transaction as the plan close.
4. Audit times on the database clock (finding request-clock-for-database-stamped-fact): the event time is not taken
   from the route's clock. Read `audit_store.append` and say in the report which clock stamps the row.
5. Tests: the three events on the real recordings; a refused Execute writes no event; a second return writes no
   duplicate; an `order_prepared` payload with an extra key stores without it (dropped), a payload with no declared
   field is refused (`PayloadShapeError`), a float is refused by the store; upgrade/downgrade of 0017.

## Reviewer checklist (the Tier A reviewer checks exactly this; attack cases first)
- Attack: payload `{"strategy_id": 1, "plan_number": 1, "action": "ENTRY", "tags": "OFS1V1L0", "x": 1}` is stored
  WITHOUT `x`; `{"x": 1}` alone refused; `"plan_number": 1.0` refused by the store's float rule.
- The route builds the payload itself from the stored plan (no request field reaches it).
- Attack: Execute refused at the gate -> zero audit rows added (count before/after).
- Attack: return route called twice on the same replies -> trade events not duplicated.
- The allow-list in code and in the database agree after 0017 (the existing drift check covers it, or add one).
- Downgrade really removes the declaration (not a no-op).

## DB (you are THE shared-DB holder this run)
You hold ofo_test. Run DB commands only through
`python D:/Abhay/Ventures/OptionsForOptions2/scripts/orchestrator/db_run.py <your worktree> python -m ...` with your
worktree as cwd: the alembic upgrade to 0017, the two route test files, `tests_app/test_audit_store.py`, and the
allow-list chain test. Before you report, downgrade ofo_test back to main's head
(`0016_execution_plans`) and print `alembic current` (finding branch-migration-tests-move-shared-db).

## Rules
- Branch `build/W-103-route-audit` from origin/main. Work card `work/W-103.md` (frontmatter shape of
  `work/W-100.md`; requirement_ids [REQ-063, REQ-073]; tier A; depends_on [W-017, W-095, W-096]; tests_required
  ['AC-5: tests_app/test_audit_store.py', 'AC-3: tests_app/test_execution_return.py']) and `W-103: 4b` in
  `docs/process/coverage-stages.yaml`.
- Never copy .env; no PR. No kit or `spec/` edit, no `views/`, no `evidence/`. Common rules: `docs/process/builder-brief.md`.
