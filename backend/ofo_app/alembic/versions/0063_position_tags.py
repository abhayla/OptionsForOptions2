"""The stored position tag and the real-position record book (Lane R1; ADR-330 (58) and (64) withdrawn, ADR-281).

Spec basis: ADR-330 (58) (paper and real are one rule; the tag is the only difference), the owner's 28 Nov 2026 rule
("the tag never changes"); ADR-016 to ADR-019 (the broker is the authority; nothing here sends an order); ADR-048
(the limited application role); ADR-008 (money exact).

Why: the tag was DERIVED on every read (a held entry -> real; an order and no paper order -> real; a paper order ->
paper), so any stored paper order on a basket-sent real strategy flipped its kind. The tag is now a stored fact,
written once, never updated.

Changes (owner-run, one transaction; ADDITIVE: two new tables, nothing existing changed):
- public.strategy_position_tags(strategy_id PK -> strategies, tag 'paper'|'real', created_at). INSERT-ONLY: a guard
  trigger refuses every UPDATE and DELETE (SQLSTATE OF063). The application role has SELECT and INSERT; the code writes
  the row once (``strategy_store.claim_tag``: under the strategy row lock at a first paper order, or when a real
  strategy's tag is first read); ON CONFLICT DO NOTHING, so the first write decides. No row and no order reads "none";
  no row and an order reads "unknown" (fail closed). (No trigger on paper_orders, execution_plans or
  strategy_held_entries: the allow-list refuses an unexpected trigger on those tables.)
- Backfill: every existing strategy that has an order gets the tag today's derivation gives (held entry -> real; else a
  paper order -> paper; else an execution plan -> real).
- public.real_action_records: append-only book of what a user stored for a REAL position (open, add, exit, stop) and
  what the worker stored when a stop was reached (stop_fired). No broker field: nothing is sent. Insert-only guard
  (OF063), SELECT and column-limited INSERT for the application role. Unique (user_ref, request_key, action) where a
  key is set (a repeated press stores one record per action); unique (trigger_id) for stop_fired (a fired stop is claimed once).
- downgrade: refuses while real_action_records holds a row (it exists nowhere else); else drops both tables and the
  guard function.

Old-code compatibility: additive. Old code never reads the tables.

Revision ID: 0063_position_tags
Revises: 0062_order_request_keys_expiry
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0063_position_tags"
down_revision = "0062_order_request_keys_expiry"
branch_labels = None
depends_on = None


def _load(filename: str, name: str):
    path = Path(__file__).with_name(filename)
    found = importlib.util.spec_from_file_location(name, path)
    if found is None or found.loader is None:
        raise RuntimeError(f"cannot load the migration {path}")
    module = importlib.util.module_from_spec(found)
    found.loader.exec_module(module)
    return module


_BASE = _load("0009_minute_history.py", "ofo_migration_0009_for_0063")._BASE

TAGS = "public.strategy_position_tags"
RECORDS = "public.real_action_records"
SEQUENCE = "public.real_action_records_id_seq"
GUARD = "public.position_tag_tables_guard"
SQLSTATE = "OF063"
ACTIONS = ("open", "add", "exit", "stop", "stop_fired")
RECORD_INSERT_COLUMNS = ("user_ref", "strategy_id", "action", "legs", "reason", "trigger_id", "request_key",
                         "stored_at")
#: the one derivation of the backfill (held -> real; else paper order -> paper; else plan -> real)
_TAG_OF = """CASE
            WHEN EXISTS (SELECT 1 FROM public.strategy_held_entries h WHERE h.strategy_id = {sid}) THEN 'real'
            WHEN EXISTS (SELECT 1 FROM public.paper_orders o WHERE o.strategy_id = {sid}) THEN 'paper'
            WHEN EXISTS (SELECT 1 FROM public.execution_plans p WHERE p.strategy_id = {sid}) THEN 'real'
            ELSE NULL END"""


def _guard_sql() -> str:
    return f"""
        CREATE OR REPLACE FUNCTION {GUARD}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $fn$
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'the position tag and the real action records are insert-only'
                    USING ERRCODE = '{SQLSTATE}';
            END IF;
            RETURN NEW;
        END
        $fn$
        """


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    kinds = ", ".join(f"'{a}'" for a in ACTIONS)
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(
        f"""
        CREATE TABLE {TAGS} (
            strategy_id BIGINT      PRIMARY KEY REFERENCES public.strategies (id),
            tag         TEXT        NOT NULL CHECK (tag IN ('paper', 'real')),
            created_at  TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE {RECORDS} (
            id          BIGSERIAL   PRIMARY KEY,
            user_ref    TEXT        NOT NULL CHECK (user_ref <> ''),
            strategy_id BIGINT      NOT NULL REFERENCES public.strategies (id),
            action      TEXT        NOT NULL CHECK (action IN ({kinds})),
            legs        JSONB       NOT NULL,
            reason      TEXT        NULL,
            trigger_id  BIGINT      NULL,
            request_key UUID        NULL,
            stored_at   TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            created_at  TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
        )
        """
    )
    op.execute(f"CREATE INDEX real_action_records_strategy ON {RECORDS} (strategy_id, id)")
    op.execute(f"CREATE UNIQUE INDEX real_action_records_key ON {RECORDS} (user_ref, request_key, action) "
               "WHERE request_key IS NOT NULL")
    op.execute(f"CREATE UNIQUE INDEX real_action_records_fired ON {RECORDS} (trigger_id) "
               "WHERE action = 'stop_fired' AND trigger_id IS NOT NULL")
    op.execute(_guard_sql())
    for table in (TAGS, RECORDS):
        short = table.split(".")[1]
        op.execute(f"CREATE TRIGGER {short}_guard BEFORE UPDATE OR DELETE ON {table} "
                   f"FOR EACH ROW EXECUTE FUNCTION {GUARD}()")
    # backfill: every strategy that has an order gets today's derivation
    op.execute(
        f"""
        INSERT INTO {TAGS} (strategy_id, tag)
        SELECT s.id, {_TAG_OF.format(sid="s.id")} FROM public.strategies AS s
        WHERE {_TAG_OF.format(sid="s.id")} IS NOT NULL
        """  # noqa: S608 constants only
    )
    for fn in (GUARD,):
        op.execute(f"REVOKE ALL ON FUNCTION {fn}() FROM PUBLIC")
        op.execute(f'REVOKE ALL ON FUNCTION {fn}() FROM "{role}"')
    for table in (TAGS, RECORDS):
        op.execute(f"REVOKE ALL ON TABLE {table} FROM PUBLIC")
        op.execute(f'REVOKE ALL ON TABLE {table} FROM "{role}"')
        op.execute(f'GRANT SELECT ON TABLE {table} TO "{role}"')
    op.execute(f'GRANT INSERT (strategy_id, tag) ON TABLE {TAGS} TO "{role}"')
    op.execute(f'GRANT INSERT ({", ".join(RECORD_INSERT_COLUMNS)}) ON TABLE {RECORDS} TO "{role}"')
    op.execute(f"REVOKE ALL ON SEQUENCE {SEQUENCE} FROM PUBLIC")
    op.execute(f'REVOKE ALL ON SEQUENCE {SEQUENCE} FROM "{role}"')
    op.execute(f'GRANT USAGE ON SEQUENCE {SEQUENCE} TO "{role}"')
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            EXECUTE 'LOCK TABLE {RECORDS} IN ACCESS EXCLUSIVE MODE';
            IF EXISTS (SELECT 1 FROM {RECORDS}) THEN
                RAISE EXCEPTION 'refusing downgrade: {RECORDS} holds records that exist nowhere else';
            END IF;
        END
        $$
        """  # noqa: S608 constant table name
    )
    op.execute(f"DROP TABLE {RECORDS}")
    op.execute(f"DROP TABLE {TAGS}")
    op.execute(f"DROP FUNCTION {GUARD}()")
