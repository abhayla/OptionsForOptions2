# Builder brief: W-094 Persisted execution-plan intent - one open plan per strategy, tag never reused (Tier A: migration, order-safety gate)

Core: for strategy id 1, the store mints plan number 1, records its one order with tag OFS1V1L0 (BUY 65
NIFTY26O1923650CE LIMIT 5.45 - the owner's real basket of 2026-10-16), refuses a second open plan for strategy 1, and
after `close_plan` mints 2 for the exit (tag OFS1V2L0, SELL 65 LIMIT 3.10) - the numbers the real orders carry.
Proof: step 1 is `tests_app/test_execution_plan_store.py::test_core_real_order_plan_numbers` (a DB test) on those
two real baskets (`D:/Abhay/Ventures/ofo-kite-ticks/2026-10-16/real-order/basket-121848.json` and `exit.html`'s
basket; copy the two order rows into the test as literals with a comment naming the source file). Write it FIRST, red.

Tier: A (migration + the gate that stops a duplicate basket). Model: sonnet.
Budget: 60 min wall-clock, 64 tool calls. HARD limit: at call 60 commit, push, report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~300 words.
Copy from: none - spec/technical-design/legacy-reuse.md has no plan/intent store row (searched: order intent, plan,
basket store); algochanakya's order tables are not copied (ADR-054). Pattern: `backend/ofo_app/strategy_store.py` and
migration `0015_audit_broker_allowlist.py`.
Findings checked: state-read-after-await, identifier-unique-only-by-convention, store-rule-enforced-per-call-site,
branch-migration-tests-move-shared-db, fill-not-exactly-once, caller-supplied-verdict-trusted, money-parsed-through-float
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py

Read first: `docs/process/builder-brief.md` (every line applies), `CLAUDE.md`, `backend/ofo_app/strategy_store.py`
(row lock `_locked`, id checks, error style), the latest migrations and `tests_app/_migration_replay.py`,
`tests_app/test_strategy_store.py`, `backend/ofo/execution/basket.py` (`make_tag`, `parse_tag`, `MAX_TAG_LENGTH`), the
finding files named above.

## Spec basis
- ADR-050 item 4: "(b) persist the order intent before sending"
- ADR-054: "Confirmation, reconciliation and the eight
  safeguards of ADR-050 item 4 run on the result (tag lookup, order updates, positions)."
- REQ-073 AC-2: "Every order in the basket carries our own tag (at most 20 alphanumeric characters) that identifies the strategy
    and plan version, so the result is matched by tag, never by symbol (ADR-050 item 4a)."
- Technical decision (orchestrator, GC-2c design review 2026-10-17; its decision row lands in the GC-2c docs batch):
  the tag's plan version is a per-strategy PLAN NUMBER minted for every Execute (entry 1, exit 2 on the real order); it
  is not the domain `Version` number (an EXIT runs the active version, context.py:9). One plan may be open per
  strategy at a time (review CRITICAL 1: two exit presses = two live exit baskets).

## Work card (commit FIRST as `work/W-094.md`; frontmatter shape of `work/W-091.md`)
id W-094; title "Persisted execution-plan intent: plan number per strategy, one open plan, tags unique (ADR-050 4b)";
requirement_ids [REQ-073]; tier A; status in_progress; depends_on []; affected [backend/ofo_app/, tests_app/];
tests_required ['AC-2: tests_app/test_execution_plan_store.py']; core/proof = the lines at the top; review_status
'not reviewed'; next_action 'Tier A review'.

## The API (FIXED: W-095 is built in parallel against exactly this; do not rename)
`backend/ofo_app/execution_plan_store.py`:
- `PlanOrder` frozen dataclass: `leg_index: int` (>= 0), `tag: str` (must equal `make_tag(strategy_id, plan_number,
  leg_index)`, checked on record), `instrument_id: str`, `tradingsymbol: str`, `transaction_type: Literal["BUY","SELL"]`,
  `quantity: int` (> 0), `price: Decimal` (positive, finite, at most 2 decimals; a float refused).
- `StoredPlan` frozen dataclass: `strategy_id: int`, `plan_number: int`, `action: Literal["ENTRY","EXIT"]`,
  `status: Literal["open","closed"]`, `orders: tuple[PlanOrder, ...]`, `created_at`, `closed_at | None`,
  `close_reason: str | None`.
- `PlanStoreError(code, detail)`; codes `plan_open` (an open plan exists), `not_found` (no strategy for this user /
  no plan), `bad_plan` (orders invalid), `tag_taken` (a tag already stored).
- `async next_plan_number(conn, user_ref, strategy_id, *, floor: int = 0) -> int`: locks the strategy row (reuse
  `strategy_store`'s lock; another user's strategy = `not_found`), refuses `plan_open` when an open plan exists, returns
  `max(highest stored plan number, floor) + 1` (`floor` = the highest plan number the caller saw in Zerodha's own
  order book today, so a number Kite already holds is never minted again). Must run inside the caller's transaction;
  the lock holds until commit, so two concurrent calls cannot both pass (test it with two connections).
- `async record_plan(conn, user_ref, strategy_id, plan_number, action, orders) -> StoredPlan`: inserts the plan
  `open` with its orders; same transaction as `next_plan_number`.
- `async plans_for(conn, user_ref, strategy_id) -> tuple[StoredPlan, ...]` (all, ascending) and
  `async open_plan(conn, user_ref, strategy_id) -> StoredPlan | None`.
- `async close_plan(conn, user_ref, strategy_id, plan_number, *, reason) -> StoredPlan`; reason in
  {"filled", "exited", "nothing_placed", "partial"}; closing a closed plan refuses (`bad_plan`).

## Structural guarantees (the database enforces them; a store-only check is not enough - finding store-rule-enforced-per-call-site)
- Migration `0016_execution_plans` (Alembic, owner role; grants to `ofo_app` like the latest migrations; a REAL
  downgrade that drops what it created): table `execution_plans` (strategy_id BIGINT FK -> strategies.id, plan_number
  INTEGER > 0, action CHECK in ('ENTRY','EXIT'), status CHECK in ('open','closed'), created_at/closed_at TIMESTAMPTZ
  from the database clock, close_reason CHECK in the four reasons or NULL, CHECK closed <=> closed_at and reason set);
  PRIMARY KEY (strategy_id, plan_number); a PARTIAL UNIQUE INDEX on (strategy_id) WHERE status = 'open' (one open plan);
  table `execution_plan_orders` (strategy_id, plan_number FK, leg_index >= 0, tag TEXT UNIQUE with a CHECK that it is
  1..20 ASCII alphanumerics, instrument_id, tradingsymbol, transaction_type CHECK, quantity > 0, price NUMERIC(14,2) > 0;
  PRIMARY KEY (strategy_id, plan_number, leg_index)). No UPDATE of orders; plans change only open -> closed.

## Reviewer checklist (each red when mutated; write these first)
- Drop the partial unique index -> a test inserting a second open plan by raw SQL (bypassing the store) goes red.
- Drop the row lock -> the two-connection test (both call `next_plan_number` for strategy 1 before either commits)
  goes red: the second must wait and then get `plan_open`.
- `floor` ignored -> red: floor 2 with no stored plans gives 3.
- A tag that is not `make_tag(...)` of its own row, a duplicate tag (another strategy), a float price, price 0,
  quantity 0, another user's strategy -> each refused with its code.
- Closed plan closed again -> `bad_plan`; reopening is impossible (no API, and the CHECK refuses closed_at NULL).
- Downgrade then upgrade leaves the schema equal (the replay helper).

## Rules
- DB steps only through `scripts/orchestrator/db_run.py`. Finding `branch-migration-tests-move-shared-db`: the shared
  test DB is at main's head `0015`. Run `db_run.py . python -m alembic -c backend/ofo_app/alembic.ini upgrade head`
  from YOUR worktree, run ONLY `tests_app/test_execution_plan_store.py` and `tests_app/test_migration_sql_parses.py`
  and `tests_app/test_alembic_migration_guard.py`, then `... alembic ... downgrade 0015_audit_broker_allowlist` and
  `... alembic ... current` (paste it: must print 0015). Never run the migration replay files locally (CI runs them).
- `python scripts/alembic_migration_guard.py`; `python scripts/orchestrator/atool.py <your worktree> W-094 --no-tests`
  (read its exit and every ` rc ` line); `python scripts/ruff_ratchet.py` must not rise.
- No route, no UI, no change to strategy_store behaviour (reuse its lock; if it is private, add a small public
  function there). No kit or `spec/` edit, no `views/`, no findings INDEX, no regenerated files, no `evidence/`.
- Commit and push `build/W-094-plan-store`. No PR.
