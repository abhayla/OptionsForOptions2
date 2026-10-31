"""Adjustment playbooks, the active choice, a strategy's own plan, the F-71 rule memory and the suggestion record
(GC-ADJ2 step 1A).

Basis: REQ-158 AC-1..AC-7 (one read-only system playbook per type, named user playbooks unique per type, one active,
a strategy's plan wins and never follows a playbook edit, data not code); REQ-112 AC-1, AC-2, AC-4 (one suggestion
record, outcomes, an append-only timeline); REQ-161 AC-3 (the accepted sheet is the strategy's plan, editable later);
F-71 (rule memory: held at entry / seen clear); ADR-048 (the limited application role); ADR-023 (the database clock).
Body shape: docs/design/playbook-body-v1.md.

Copy from: none - modelled on 0029's tables, guard triggers, grants and allow-list block.

Changes (owner-run, one transaction, the API stopped):
- public.adjustment_playbooks: id, user_ref (NULL = system), strategy_type (the 12 keys), name (trimmed, 1..80),
  is_system (= user_ref IS NULL), status draft|approved (DEFAULT draft; only the seed sets approved), body JSONB (an
  object, schema 1, its strategy_type = the row's), version >= 1, created_at / updated_at from the database clock.
  UNIQUE (coalesce(user_ref, ''), strategy_type, lower(name)) - user_ref is never '' (CHECK), so '' marks the system
  rows; UNIQUE (strategy_type) WHERE is_system; UNIQUE (id, strategy_type) for the active row's composite key.
  Guard (SQLSTATE OF031): a system row is never inserted, updated or deleted by a role that is not a member of the
  table owner (the application role); id, user_ref, is_system, strategy_type, created_at never change; every UPDATE
  sets version = old + 1 and updated_at from the clock (the store's optimistic check reads version).
- public.adjustment_playbook_active: PRIMARY KEY (user_ref, strategy_type) (one active per user and type), playbook_id
  with (playbook_id, strategy_type) -> adjustment_playbooks (id, strategy_type) ON DELETE CASCADE (same type by key).
  Guard: the playbook is a system one or this user's own; user_ref and strategy_type never change. No row = the
  type's system playbook is active.
- public.strategy_adjustment_plans: strategy_id PK -> strategies, playbook_id -> adjustment_playbooks ON DELETE SET
  NULL (only the pointer), strategy_type, body (same CHECKs), accepted_at. A COPY: no trigger on the playbook table
  writes here. Guard: no DELETE; strategy_id and strategy_type never change; a body change stamps accepted_at.
- public.adjustment_rule_state: PK (strategy_id, rule_id), held_at_entry (never changes), seen_clear (false -> true
  only), updated_at. Guard: no DELETE.
- public.adjustment_suggestions: id, strategy_id, rule_id, trigger_id, stage, value, threshold, shown_at, outcome
  (open|dismissed|acted_on|lapsed|completed|partly_completed, starts open), dismiss_reason, timeline (JSONB array).
  UNIQUE (strategy_id, rule_id) WHERE outcome = 'open'. Guard: no DELETE; only outcome, dismiss_reason, timeline
  change; outcome leaves open once (then only acted_on -> completed | partly_completed, REQ-112 AC-2); dismiss_reason
  is written once; the timeline only grows and its earlier entries never change.
- Seed: the 12 system playbooks from backend/ofo/adjustment/system_playbooks.json (read at upgrade; refused unless it
  holds each of the 12 types exactly once and no float).
- Grants: the application role gets SELECT and column-limited INSERT / UPDATE; DELETE on adjustment_playbooks and
  adjustment_playbook_active only (the guard keeps system rows); no TRUNCATE; USAGE on the two sequences.
- public.ofo_assert_app_role_allowlist: the predecessor's chain text plus block 23.
- downgrade: refuses (SQLSTATE OF031, counted) while a user playbook, an active row, a plan, a rule state or a
  suggestion exists; otherwise drops the five tables and restores the predecessor's allow-list.

Known bypasses (not chased): the table owner or a superuser can edit any row (out of the threat model); the plan's
body is a copy, so a playbook fix never reaches a strategy already tracking - by design (REQ-158 AC-5).

Revision ID: 0031_adjustment_playbooks
Revises: 0030_paper_settle_zero
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from alembic import op

revision = "0031_adjustment_playbooks"
down_revision = "0030_paper_settle_zero"
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


_M29 = _load("0029_paper_triggers.py", "ofo_migration_0029_for_0031")  # the last allow-list block (0030 adds none)
_M16 = _M29._M16
_M4 = _M29._M4
_BASE = _M29._BASE
_INSERT_BEFORE = _M29._INSERT_BEFORE

SEARCH_PATH = _M16.SEARCH_PATH
SQLSTATE = "OF031"
SEED_FILE = Path(__file__).resolve().parents[3] / "ofo" / "adjustment" / "system_playbooks.json"
TYPE_KEYS = ("strangle", "straddle", "ic", "ifly", "credit", "debit", "longopt", "longvol", "calendar", "ratio",
             "dirfly", "other")  # = ofo.adjustment.playbook_types.TYPE_KEYS (a migration is frozen; a test pins it)
OUTCOMES = ("open", "dismissed", "acted_on", "lapsed", "completed", "partly_completed")
NAME_MAX = 80
USER_REF_MAX = 200

PLAYBOOKS = "public.adjustment_playbooks"
ACTIVE = "public.adjustment_playbook_active"
PLANS = "public.strategy_adjustment_plans"
RULE_STATE = "public.adjustment_rule_state"
SUGGESTIONS = "public.adjustment_suggestions"
PLAYBOOKS_SEQUENCE = "public.adjustment_playbooks_id_seq"
SUGGESTIONS_SEQUENCE = "public.adjustment_suggestions_id_seq"
NAME_INDEX = "adjustment_playbooks_name"
SYSTEM_INDEX = "adjustment_playbooks_one_system"
OPEN_INDEX = "adjustment_suggestions_one_open"

PLAYBOOK_INSERT_COLUMNS = ("user_ref", "strategy_type", "name", "body")
PLAYBOOK_UPDATE_COLUMNS = ("name", "body")
ACTIVE_INSERT_COLUMNS = ("user_ref", "strategy_type", "playbook_id")
ACTIVE_UPDATE_COLUMNS = ("playbook_id",)
PLAN_INSERT_COLUMNS = ("strategy_id", "playbook_id", "strategy_type", "body")
PLAN_UPDATE_COLUMNS = ("playbook_id", "body")
STATE_INSERT_COLUMNS = ("strategy_id", "rule_id", "held_at_entry", "seen_clear")
STATE_UPDATE_COLUMNS = ("seen_clear",)
SUGGESTION_INSERT_COLUMNS = ("strategy_id", "rule_id", "trigger_id", "stage", "value", "threshold", "timeline")
SUGGESTION_UPDATE_COLUMNS = ("outcome", "dismiss_reason", "timeline")
ALLOWLIST_BLOCK_MARKER = "-- 23. adjustment playbooks"

# (table, label, guard function, trigger name, delete allowed, insert columns, update columns, sequence or None)
_PRIVILEGED = "pg_has_role(current_user, (SELECT relowner FROM pg_class WHERE oid = TG_RELID), 'MEMBER')"


def _fn(name: str, body: str) -> str:
    return f"""
        CREATE OR REPLACE FUNCTION public.{name}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = {SEARCH_PATH}
        AS $fn$
        BEGIN
{body}
        END
        $fn$
        """


def _raise(message: str) -> str:
    return f"RAISE EXCEPTION '{message}' USING ERRCODE = '{SQLSTATE}';"


def _playbooks_guard_sql() -> str:
    return _fn("adjustment_playbooks_guard", f"""
            IF TG_OP = 'DELETE' THEN
                IF OLD.is_system AND NOT {_PRIVILEGED} THEN
                    {_raise('a system playbook is never deleted')}
                END IF;
                RETURN OLD;
            END IF;
            IF TG_OP = 'INSERT' THEN
                IF NEW.is_system AND NOT {_PRIVILEGED} THEN
                    {_raise('a system playbook is written only by a migration')}
                END IF;
                RETURN NEW;
            END IF;
            IF OLD.is_system AND NOT {_PRIVILEGED} THEN
                {_raise('a system playbook can only be saved as a new playbook')}
            END IF;
            IF (NEW.id, NEW.user_ref, NEW.is_system, NEW.strategy_type, NEW.created_at)
               IS DISTINCT FROM (OLD.id, OLD.user_ref, OLD.is_system, OLD.strategy_type, OLD.created_at) THEN
                {_raise('a playbook keeps its id, owner, kind and type')}
            END IF;
            NEW.version := OLD.version + 1;
            NEW.updated_at := clock_timestamp();
            RETURN NEW;""")


def _active_guard_sql() -> str:
    return _fn("adjustment_playbook_active_guard", f"""
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            IF TG_OP = 'UPDATE' AND (NEW.user_ref, NEW.strategy_type) IS DISTINCT FROM (OLD.user_ref, OLD.strategy_type)
            THEN
                {_raise('an active choice keeps its user and type')}
            END IF;
            IF NOT EXISTS (SELECT 1 FROM {PLAYBOOKS} p WHERE p.id = NEW.playbook_id
                           AND (p.user_ref IS NULL OR p.user_ref = NEW.user_ref)) THEN
                {_raise('the active playbook is a system one or the user''s own')}
            END IF;
            NEW.updated_at := clock_timestamp();
            RETURN NEW;""")  # noqa: S608 constant names


def _plans_guard_sql() -> str:
    return _fn("strategy_adjustment_plans_guard", f"""
            IF TG_OP = 'DELETE' THEN
                {_raise('a strategy plan is never deleted')}
            END IF;
            IF TG_OP = 'INSERT' THEN
                RETURN NEW;
            END IF;
            IF (NEW.strategy_id, NEW.strategy_type) IS DISTINCT FROM (OLD.strategy_id, OLD.strategy_type) THEN
                {_raise('a strategy plan keeps its strategy and type')}
            END IF;
            IF NEW.body IS DISTINCT FROM OLD.body THEN
                NEW.accepted_at := clock_timestamp();
            ELSE
                NEW.accepted_at := OLD.accepted_at;
            END IF;
            RETURN NEW;""")


def _state_guard_sql() -> str:
    return _fn("adjustment_rule_state_guard", f"""
            IF TG_OP = 'DELETE' THEN
                {_raise('a rule state is never deleted')}
            END IF;
            IF TG_OP = 'INSERT' THEN
                RETURN NEW;
            END IF;
            IF (NEW.strategy_id, NEW.rule_id, NEW.held_at_entry) IS DISTINCT FROM
               (OLD.strategy_id, OLD.rule_id, OLD.held_at_entry)
               OR (OLD.seen_clear AND NOT NEW.seen_clear) THEN
                {_raise('a rule state only records seen clear, once')}
            END IF;
            NEW.updated_at := clock_timestamp();
            RETURN NEW;""")


def _suggestions_guard_sql() -> str:
    return _fn("adjustment_suggestions_guard", f"""
            IF TG_OP = 'DELETE' THEN
                {_raise('a suggestion record is never deleted')}
            END IF;
            IF TG_OP = 'INSERT' THEN
                IF NEW.outcome <> 'open' OR NEW.dismiss_reason IS NOT NULL THEN
                    {_raise('a suggestion record starts open')}
                END IF;
                RETURN NEW;
            END IF;
            IF (NEW.id, NEW.strategy_id, NEW.rule_id, NEW.trigger_id, NEW.stage, NEW.value, NEW.threshold,
                NEW.shown_at)
               IS DISTINCT FROM (OLD.id, OLD.strategy_id, OLD.rule_id, OLD.trigger_id, OLD.stage, OLD.value,
                                 OLD.threshold, OLD.shown_at) THEN
                {_raise('only the outcome, dismiss reason and timeline of a suggestion change')}
            END IF;
            IF NEW.outcome IS DISTINCT FROM OLD.outcome AND NOT (OLD.outcome = 'open'
               OR (OLD.outcome = 'acted_on' AND NEW.outcome IN ('completed', 'partly_completed'))) THEN
                {_raise('a suggestion has at most one final outcome')}
            END IF;
            IF OLD.dismiss_reason IS NOT NULL AND NEW.dismiss_reason IS DISTINCT FROM OLD.dismiss_reason THEN
                {_raise('a dismiss reason is written once')}
            END IF;
            IF jsonb_array_length(NEW.timeline) < jsonb_array_length(OLD.timeline)
               OR (SELECT coalesce(jsonb_agg(e ORDER BY i), '[]'::jsonb)
                   FROM jsonb_array_elements(NEW.timeline) WITH ORDINALITY AS t(e, i)
                   WHERE i <= jsonb_array_length(OLD.timeline)) IS DISTINCT FROM OLD.timeline THEN
                {_raise('a suggestion timeline is append-only')}
            END IF;
            RETURN NEW;""")  # noqa: S608 constant names


GUARDS = (
    (PLAYBOOKS, "adjustment_playbooks", "public.adjustment_playbooks_guard", "adjustment_playbooks_guard",
     _playbooks_guard_sql, True, PLAYBOOK_INSERT_COLUMNS, PLAYBOOK_UPDATE_COLUMNS, PLAYBOOKS_SEQUENCE),
    (ACTIVE, "adjustment_playbook_active", "public.adjustment_playbook_active_guard",
     "adjustment_playbook_active_guard", _active_guard_sql, True, ACTIVE_INSERT_COLUMNS, ACTIVE_UPDATE_COLUMNS, None),
    (PLANS, "strategy_adjustment_plans", "public.strategy_adjustment_plans_guard", "strategy_adjustment_plans_guard",
     _plans_guard_sql, False, PLAN_INSERT_COLUMNS, PLAN_UPDATE_COLUMNS, None),
    (RULE_STATE, "adjustment_rule_state", "public.adjustment_rule_state_guard", "adjustment_rule_state_guard",
     _state_guard_sql, False, STATE_INSERT_COLUMNS, STATE_UPDATE_COLUMNS, None),
    (SUGGESTIONS, "adjustment_suggestions", "public.adjustment_suggestions_guard", "adjustment_suggestions_guard",
     _suggestions_guard_sql, False, SUGGESTION_INSERT_COLUMNS, SUGGESTION_UPDATE_COLUMNS, SUGGESTIONS_SEQUENCE),
)
PINS = {guard: _M4._md5_body(sql()) for _, _, guard, _, sql, *_ in GUARDS}


def _table_block(table: str, label: str, guard: str, trigger: str, delete: bool,  # noqa: PLR0913 - one row of GUARDS
                 inserts: tuple[str, ...], updates: tuple[str, ...]) -> str:
    """0016's table block with DELETE allowed where the store deletes (the guard keeps system rows)."""
    allowed = {"SELECT", "DELETE"} if delete else {"SELECT"}
    return f"""        IF to_regclass('{table}') IS NULL THEN
            problems := problems || 'table {table} is missing'::TEXT;
        ELSE
            IF (SELECT relowner FROM pg_class WHERE oid = '{table}'::regclass)
               IS DISTINCT FROM (SELECT relowner FROM pg_class WHERE oid = '{_M16._M3.TABLE}'::regclass) THEN
                problems := problems || 'table {table} is not owned by the catalogue table owner'::TEXT;
            END IF;
{_M16._PREV._privilege_checks(table, label, allowed)}
{_M16._M3._columns_exactly(table, label, "INSERT", inserts)}
{_M16._M3._columns_exactly(table, label, "UPDATE", updates)}
{_M16._M3._guard_function_checks(guard, security_definer=False)}
{_M16._M8._trigger_check(table, trigger, guard, PINS[guard])}
        END IF;"""  # noqa: S608 constant table names


def _block() -> str:
    tables = "\n".join(_table_block(t, label, g, trig, d, ins, upd)
                       for t, label, g, trig, _, d, ins, upd, _ in GUARDS)
    sequences = "\n".join(_M16._M3._sequence_checks(seq, f"{label} id", usage=True)
                          for _, label, *_, seq in GUARDS if seq)
    return f"""
    {ALLOWLIST_BLOCK_MARKER} (GC-ADJ2 1A): playbooks, active choice, plans, rule state, suggestions: SELECT,
    --    column-limited INSERT and UPDATE exactly as granted, DELETE only on playbooks and the active choice, no
    --    TRUNCATE; the guards enabled with their pinned bodies
    IF phase = 'post' THEN
{tables}
{sequences}
    END IF;
"""


def previous_allowlist_sql() -> str:
    return _M29.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """The predecessor's chain text plus block 23. Fails closed (RuntimeError) on a changed shape or a block 23 in."""
    previous = previous_allowlist_sql()
    if previous.count(_INSERT_BEFORE) != 1 or ALLOWLIST_BLOCK_MARKER in previous or "-- 23." in previous:
        raise RuntimeError("previous allowlist SQL changed shape: cannot add the playbook checks safely")
    return previous.replace(_INSERT_BEFORE, _block() + _INSERT_BEFORE, 1)


def _no_float(text: str) -> None:
    raise RuntimeError(f"system_playbooks.json holds a float ({text}); playbook values are decimal strings")


def seed_rows(path: Path = SEED_FILE) -> list[dict]:
    """The checked-in seed, refused unless it holds each of the 12 types exactly once with a matching body."""
    data = json.loads(path.read_text(encoding="utf-8"), parse_float=_no_float)
    rows = data.get("playbooks") if isinstance(data, dict) else None
    if not isinstance(rows, list) or sorted(r.get("strategy_type") for r in rows) != sorted(TYPE_KEYS):
        raise RuntimeError("system_playbooks.json must hold each of the 12 strategy types exactly once")
    for r in rows:
        body = r.get("body")
        if (not isinstance(body, dict) or body.get("schema") != 1 or body.get("strategy_type") != r["strategy_type"]
                or r.get("status") not in ("draft", "approved") or not isinstance(r.get("name"), str)):
            raise RuntimeError(f"system_playbooks.json: the {r['strategy_type']} entry is not a v1 playbook")
    return rows


def _literal(value: str) -> str:
    if "$seed$" in value:
        raise RuntimeError("system_playbooks.json holds the seed quote tag")
    return f"$seed${value}$seed$"


def _seed_sql() -> list[str]:
    return [f"INSERT INTO {PLAYBOOKS} (user_ref, strategy_type, name, is_system, status, body) VALUES "  # noqa: S608
            f"(NULL, '{r['strategy_type']}', {_literal(r['name'])}, true, '{r['status']}', "
            f"{_literal(json.dumps(r['body'], sort_keys=True, ensure_ascii=False))}::jsonb)"
            for r in seed_rows()]


def _body_checks(type_column: str = "strategy_type") -> str:
    return (f"CHECK (jsonb_typeof(body) = 'object' AND body->>'schema' = '1' "
            f"AND body->>'strategy_type' = {type_column})")


def _create_tables() -> None:
    types = ", ".join(f"'{t}'" for t in TYPE_KEYS)
    outcomes = ", ".join(f"'{o}'" for o in OUTCOMES)
    user_ref = f"user_ref <> '' AND length(user_ref) <= {USER_REF_MAX}"
    op.execute(f"""
        CREATE TABLE {PLAYBOOKS} (
            id            BIGSERIAL   PRIMARY KEY,
            user_ref      TEXT        NULL CHECK (user_ref IS NULL OR ({user_ref})),
            strategy_type TEXT        NOT NULL CHECK (strategy_type IN ({types})),
            name          TEXT        NOT NULL CHECK (name = btrim(name) AND length(name) BETWEEN 1 AND {NAME_MAX}),
            is_system     BOOLEAN     NOT NULL DEFAULT false,
            status        TEXT        NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved')),
            body          JSONB       NOT NULL {_body_checks()},
            version       INTEGER     NOT NULL DEFAULT 1 CHECK (version >= 1),
            created_at    TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            CHECK (is_system = (user_ref IS NULL)),
            UNIQUE (id, strategy_type)
        )
        """)
    op.execute(f"CREATE UNIQUE INDEX {NAME_INDEX} ON {PLAYBOOKS} (coalesce(user_ref, ''), strategy_type, lower(name))")
    op.execute(f"CREATE UNIQUE INDEX {SYSTEM_INDEX} ON {PLAYBOOKS} (strategy_type) WHERE is_system")
    op.execute(f"""
        CREATE TABLE {ACTIVE} (
            user_ref      TEXT        NOT NULL CHECK ({user_ref}),
            strategy_type TEXT        NOT NULL,
            playbook_id   BIGINT      NOT NULL,
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (user_ref, strategy_type),
            FOREIGN KEY (playbook_id, strategy_type) REFERENCES {PLAYBOOKS} (id, strategy_type) ON DELETE CASCADE
        )
        """)
    op.execute(f"""
        CREATE TABLE {PLANS} (
            strategy_id   BIGINT      PRIMARY KEY REFERENCES public.strategies (id),
            playbook_id   BIGINT      NULL REFERENCES {PLAYBOOKS} (id) ON DELETE SET NULL,
            strategy_type TEXT        NOT NULL CHECK (strategy_type IN ({types})),
            body          JSONB       NOT NULL {_body_checks()},
            accepted_at   TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
        )
        """)
    op.execute(f"""
        CREATE TABLE {RULE_STATE} (
            strategy_id   BIGINT      NOT NULL REFERENCES public.strategies (id),
            rule_id       TEXT        NOT NULL CHECK (length(rule_id) BETWEEN 1 AND 40),
            held_at_entry BOOLEAN     NOT NULL,
            seen_clear    BOOLEAN     NOT NULL DEFAULT false,
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (strategy_id, rule_id)
        )
        """)
    op.execute(f"""
        CREATE TABLE {SUGGESTIONS} (
            id             BIGSERIAL   PRIMARY KEY,
            strategy_id    BIGINT      NOT NULL REFERENCES public.strategies (id),
            rule_id        TEXT        NOT NULL CHECK (length(rule_id) BETWEEN 1 AND 40),
            trigger_id     TEXT        NULL CHECK (trigger_id IS NULL OR length(trigger_id) BETWEEN 1 AND 40),
            stage          TEXT        NULL CHECK (stage IS NULL OR length(stage) BETWEEN 1 AND 40),
            value          NUMERIC     NULL,
            threshold      NUMERIC     NULL,
            shown_at       TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            outcome        TEXT        NOT NULL DEFAULT 'open' CHECK (outcome IN ({outcomes})),
            dismiss_reason TEXT        NULL CHECK (dismiss_reason IS NULL OR length(dismiss_reason) BETWEEN 1 AND 200),
            timeline       JSONB       NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(timeline) = 'array')
        )
        """)
    op.execute(f"CREATE UNIQUE INDEX {OPEN_INDEX} ON {SUGGESTIONS} (strategy_id, rule_id) WHERE outcome = 'open'")
    op.execute(f"CREATE INDEX adjustment_suggestions_strategy ON {SUGGESTIONS} (strategy_id, id)")


def _grant(role: str, table: str, guard: str, delete: bool,  # noqa: PLR0913 - one grant set per table
           inserts: tuple[str, ...], updates: tuple[str, ...], sequence: str | None) -> None:
    op.execute(f"REVOKE ALL ON FUNCTION {guard}() FROM PUBLIC")
    op.execute(f'REVOKE ALL ON FUNCTION {guard}() FROM "{role}"')
    op.execute(f"REVOKE ALL ON TABLE {table} FROM PUBLIC")
    op.execute(f'REVOKE ALL ON TABLE {table} FROM "{role}"')
    op.execute(f'GRANT SELECT{", DELETE" if delete else ""} ON TABLE {table} TO "{role}"')
    op.execute(f'GRANT INSERT ({", ".join(inserts)}) ON TABLE {table} TO "{role}"')
    op.execute(f'GRANT UPDATE ({", ".join(updates)}) ON TABLE {table} TO "{role}"')
    if sequence:
        op.execute(f"REVOKE ALL ON SEQUENCE {sequence} FROM PUBLIC")
        op.execute(f'REVOKE ALL ON SEQUENCE {sequence} FROM "{role}"')
        op.execute(f'GRANT USAGE ON SEQUENCE {sequence} TO "{role}"')


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    seed = _seed_sql()  # refuses a bad seed file before any change
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    _create_tables()
    for table, _, guard, trigger, sql, *_ in GUARDS:
        op.execute(sql())
        op.execute(f"CREATE TRIGGER {trigger} BEFORE INSERT OR UPDATE OR DELETE ON {table} "
                   f"FOR EACH ROW EXECUTE FUNCTION {guard}()")
    for statement in seed:
        op.execute(statement)
    for table, _, guard, _, _, delete, inserts, updates, sequence in GUARDS:
        _grant(role, table, guard, delete, inserts, updates, sequence)
    op.execute(extended_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    role = _BASE._app_role()
    op.execute(
        f"""
        DO $do$
        DECLARE
            n BIGINT;
        BEGIN
            SELECT (SELECT count(*) FROM {PLAYBOOKS} WHERE NOT is_system) + (SELECT count(*) FROM {ACTIVE})
                   + (SELECT count(*) FROM {PLANS}) + (SELECT count(*) FROM {RULE_STATE})
                   + (SELECT count(*) FROM {SUGGESTIONS}) INTO n;
            IF n > 0 THEN
                RAISE EXCEPTION 'refusing downgrade: % user playbook, active, plan, rule state or suggestion rows',
                    n USING ERRCODE = '{SQLSTATE}';
            END IF;
        END
        $do$
        """  # noqa: S608 - constant names only
    )
    op.execute(previous_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {_BASE.ALLOWLIST_FUNCTION}(TEXT, TEXT) FROM PUBLIC")
    for table in (SUGGESTIONS, RULE_STATE, PLANS, ACTIVE, PLAYBOOKS):
        op.execute(f"DROP TABLE {table}")
    for _, _, guard, *_ in GUARDS:
        op.execute(f"DROP FUNCTION {guard}()")
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'post')")
