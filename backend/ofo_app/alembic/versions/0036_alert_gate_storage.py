"""Alert-gate storage: a record's "worse" marker and the held crossings (REQ-170 AC-3/AC-4; ADR-237 (5); GC-ALERT1).

Spec basis: ADR-237 (5) "A held crossing (REQ-170 AC-4) is a row in a new insert-only table (strategy, rule, stage,
value, threshold, reason daily_limit | quiet_time, held_at by the database clock), and a record's 'worse' marker
(none | last | dismissed) is a new insert-only column of adjustment_suggestions; one migration, guarded like the
suggestion table (no update, no delete), Tier A." ADR-048 (the limited application role); ADR-023 (database clock).

Copy from: 0031_adjustment_playbooks.py (the suggestion guard and its allow-list block), 0035_strategy_alert_style.py
(append-only table, statement-level truncate trigger, grants, allow-list block 27).

Changes (owner-run, one transaction, the API stopped):
- public.adjustment_suggestions gains ``worse TEXT NULL CHECK (worse IN ('last','dismissed'))`` (NULL = none). The
  suggestion guard is re-created with ``worse`` in its never-changes list (an UPDATE of it is refused, OF031, like the
  other recorded columns); the application role gets column INSERT on it, never UPDATE. Block 23's suggestion part in
  the allow-list chain is rewritten to the new guard pin and the new INSERT column list (fails closed when that text
  is not found exactly once).
- public.adjustment_held_crossings: id, strategy_id (a stored strategy), rule_id, trigger_id, stage, value,
  threshold, reason daily_limit | quiet_time, held_at (the guard sets it from clock_timestamp() on every insert).
  Append-only guard (SQLSTATE OF036, search_path pinned, md5-pinned): every UPDATE and DELETE refused; the same
  function on a BEFORE TRUNCATE statement trigger refuses TRUNCATE. Grants: SELECT, column INSERT on strategy_id,
  rule_id, trigger_id, stage, value, threshold, reason; USAGE on the id sequence.
- public.ofo_assert_app_role_allowlist: 0035's chain text (block 23 rewritten as above) plus block 28.
- downgrade: refuses (OF036) while a held row or a suggestion with a "worse" marker exists.

Known bypasses (out of the threat model): the table owner or a superuser can drop or disable a guard.

Revision ID: 0036_alert_gate_storage
Revises: 0035_strategy_alert_style
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0036_alert_gate_storage"
down_revision = "0035_strategy_alert_style"
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


_M35 = _load("0035_strategy_alert_style.py", "ofo_migration_0035_for_0036")
_M31 = _load("0031_adjustment_playbooks.py", "ofo_migration_0031_for_0036")
_M16 = _M35._M16
_M4 = _M35._M4
_BASE = _M35._BASE
_INSERT_BEFORE = _M35._INSERT_BEFORE

SEARCH_PATH = _M16.SEARCH_PATH
SQLSTATE = "OF036"
WORSE = ("last", "dismissed")  # = alert_gate.Opened.worse values (a test asserts they are equal)
REASONS = ("daily_limit", "quiet_time")  # = alert_gate.HELD_DAILY_LIMIT, HELD_QUIET_TIME (a test asserts it)

SUGGESTIONS = _M31.SUGGESTIONS
SUGGESTION_GUARD = "public.adjustment_suggestions_guard"
SUGGESTION_TRIGGER = "adjustment_suggestions_guard"
SUGGESTION_LABEL = "adjustment_suggestions"
SUGGESTION_INSERT_COLUMNS = (*_M31.SUGGESTION_INSERT_COLUMNS, "worse")
SUGGESTION_UPDATE_COLUMNS = _M31.SUGGESTION_UPDATE_COLUMNS

TABLE = "public.adjustment_held_crossings"
SEQUENCE = "public.adjustment_held_crossings_id_seq"
GUARD = "public.adjustment_held_crossings_guard"
TRIGGER = "adjustment_held_crossings_guard"
TRUNCATE_TRIGGER = "adjustment_held_crossings_no_truncate"
LABEL = "adjustment_held_crossings"
INSERT_COLUMNS = ("strategy_id", "rule_id", "trigger_id", "stage", "value", "threshold", "reason")
NO_UPDATE: tuple[str, ...] = ()
ALLOWLIST_BLOCK_MARKER = "-- 28. alert gate held crossings"

_OLD_KEEP = ("NEW.shown_at)", "OLD.threshold, OLD.shown_at)")
_NEW_KEEP = ("NEW.shown_at, NEW.worse)", "OLD.threshold, OLD.shown_at, OLD.worse)")


def suggestions_guard_sql() -> str:
    """0031's suggestion guard with ``worse`` in the never-changes comparison (fails closed on a changed shape)."""
    sql = _M31._suggestions_guard_sql()
    for old, new in zip(_OLD_KEEP, _NEW_KEEP, strict=True):
        if sql.count(old) != 1:
            raise RuntimeError("0031's suggestion guard changed shape: cannot add worse to its unchanged columns")
        sql = sql.replace(old, new, 1)
    return sql


OLD_SUGGESTION_PIN = _M31.PINS[SUGGESTION_GUARD]
SUGGESTION_PIN = _M4._md5_body(suggestions_guard_sql())


def _old_suggestion_block() -> str:
    return _M31._table_block(SUGGESTIONS, SUGGESTION_LABEL, SUGGESTION_GUARD, SUGGESTION_TRIGGER, False,
                             _M31.SUGGESTION_INSERT_COLUMNS, SUGGESTION_UPDATE_COLUMNS)


def _new_suggestion_block() -> str:
    """Block 23's suggestion part with the new pin and the new INSERT columns; fails closed on a changed shape."""
    block = _old_suggestion_block()
    old_cols = _M16._M3._columns_exactly(SUGGESTIONS, SUGGESTION_LABEL, "INSERT", _M31.SUGGESTION_INSERT_COLUMNS)
    new_cols = _M16._M3._columns_exactly(SUGGESTIONS, SUGGESTION_LABEL, "INSERT", SUGGESTION_INSERT_COLUMNS)
    if block.count(OLD_SUGGESTION_PIN) != 1 or block.count(old_cols) != 1:
        raise RuntimeError("0031's suggestion allow-list block changed shape: cannot re-pin it safely")
    return block.replace(OLD_SUGGESTION_PIN, SUGGESTION_PIN, 1).replace(old_cols, new_cols, 1)


def _guard_sql() -> str:
    return f"""
        CREATE OR REPLACE FUNCTION {GUARD}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = {SEARCH_PATH}
        AS $fn$
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'held crossings are insert-only: never updated, deleted or truncated'
                    USING ERRCODE = '{SQLSTATE}';
            END IF;
            NEW.held_at := clock_timestamp();
            RETURN NEW;
        END
        $fn$
        """


PIN = _M4._md5_body(_guard_sql())
BEFORE_STATEMENT_TRUNCATE = _M35.BEFORE_STATEMENT_TRUNCATE


def _trigger_checks() -> str:
    """0008's shared check with this table's truncate trigger allowed and checked in its own right (as 0035)."""
    shared = _M16._M8._trigger_check(TABLE, TRIGGER, GUARD, PIN)
    plain = f"AND tgname <> '{TRIGGER}')"
    if shared.count(plain) != 1:
        raise RuntimeError("the shared trigger check changed shape: cannot allow the truncate trigger safely")
    shared = shared.replace(plain, f"AND tgname NOT IN ('{TRIGGER}', '{TRUNCATE_TRIGGER}'))")
    row = f"FROM pg_trigger WHERE tgrelid = '{TABLE}'::regclass AND tgname = '{TRUNCATE_TRIGGER}'"
    return shared + f"""
            IF NOT EXISTS (SELECT 1 {row} AND tgenabled = 'O') THEN
                problems := problems || 'trigger {TRUNCATE_TRIGGER} is missing or not enabled'::TEXT;
            ELSIF (SELECT tgfoid {row}) IS DISTINCT FROM to_regprocedure('{GUARD}()')
                  OR (SELECT tgtype::int {row}) IS DISTINCT FROM {BEFORE_STATEMENT_TRUNCATE}
                  OR (SELECT tgqual IS NOT NULL OR tgattr::text <> '' OR tgnargs <> 0 {row}) THEN
                problems := problems || 'trigger {TRUNCATE_TRIGGER} is not a plain BEFORE TRUNCATE trigger'::TEXT;
            END IF;"""  # noqa: S608 - constant names only


def _block() -> str:
    """Runs inside public.ofo_assert_app_role_allowlist (`r` the role row, `problems` the refusals, `col` TEXT)."""
    return f"""
    {ALLOWLIST_BLOCK_MARKER} (REQ-170 AC-4): SELECT + column INSERT on {", ".join(INSERT_COLUMNS)} only;
    --    no UPDATE / DELETE / TRUNCATE; the guard trigger enabled with its pinned body, no EXECUTE on it
    IF phase = 'post' THEN
        IF to_regclass('{TABLE}') IS NULL THEN
            problems := problems || 'table {TABLE} is missing'::TEXT;
        ELSE
            IF (SELECT relowner FROM pg_class WHERE oid = '{TABLE}'::regclass)
               IS DISTINCT FROM (SELECT relowner FROM pg_class WHERE oid = '{_M16._M3.TABLE}'::regclass) THEN
                problems := problems || 'table {TABLE} is not owned by the catalogue table owner'::TEXT;
            END IF;
{_M16._PREV._privilege_checks(TABLE, LABEL, {"SELECT"})}
{_M16._M3._columns_exactly(TABLE, LABEL, "INSERT", INSERT_COLUMNS)}
{_M16._M3._columns_exactly(TABLE, LABEL, "UPDATE", NO_UPDATE)}
{_M16._M3._guard_function_checks(GUARD, security_definer=False)}
{_trigger_checks()}
        END IF;
{_M16._M3._sequence_checks(SEQUENCE, f"{LABEL} id", usage=True)}
    END IF;
"""  # noqa: S608 - constant table and function names only


def previous_allowlist_sql() -> str:
    return _M35.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """0035's chain text, block 23's suggestion part re-pinned, plus block 28. Fails closed on a changed shape."""
    previous = previous_allowlist_sql()
    old = _old_suggestion_block()
    if previous.count(_INSERT_BEFORE) != 1 or ALLOWLIST_BLOCK_MARKER in previous or "-- 28." in previous \
            or previous.count(old) != 1:
        raise RuntimeError("previous allowlist SQL changed shape: cannot add the alert-gate checks safely")
    text = previous.replace(old, _new_suggestion_block(), 1)
    return text.replace(_INSERT_BEFORE, _block() + _INSERT_BEFORE, 1)


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    worse = ", ".join(f"'{w}'" for w in WORSE)
    reasons = ", ".join(f"'{r}'" for r in REASONS)
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(f"ALTER TABLE {SUGGESTIONS} ADD COLUMN worse TEXT NULL CHECK (worse IS NULL OR worse IN ({worse}))")
    op.execute(suggestions_guard_sql())
    op.execute(f'GRANT INSERT (worse) ON TABLE {SUGGESTIONS} TO "{role}"')
    op.execute(
        f"""
        CREATE TABLE {TABLE} (
            id          BIGSERIAL   PRIMARY KEY,
            strategy_id BIGINT      NOT NULL REFERENCES public.strategies (id),
            rule_id     TEXT        NOT NULL CHECK (length(rule_id) BETWEEN 1 AND 40),
            trigger_id  TEXT        NULL CHECK (trigger_id IS NULL OR length(trigger_id) BETWEEN 1 AND 40),
            stage       TEXT        NULL CHECK (stage IS NULL OR length(stage) BETWEEN 1 AND 40),
            value       NUMERIC     NULL,
            threshold   NUMERIC     NULL,
            reason      TEXT        NOT NULL CHECK (reason IN ({reasons})),
            held_at     TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
        )
        """
    )
    op.execute(f"CREATE INDEX adjustment_held_crossings_strategy ON {TABLE} (strategy_id, id)")
    op.execute(_guard_sql())
    op.execute(f"CREATE TRIGGER {TRIGGER} BEFORE INSERT OR UPDATE OR DELETE ON {TABLE} "
               f"FOR EACH ROW EXECUTE FUNCTION {GUARD}()")
    op.execute(f"CREATE TRIGGER {TRUNCATE_TRIGGER} BEFORE TRUNCATE ON {TABLE} FOR EACH STATEMENT "
               f"EXECUTE FUNCTION {GUARD}()")
    op.execute(f"REVOKE ALL ON FUNCTION {GUARD}() FROM PUBLIC")
    op.execute(f'REVOKE ALL ON FUNCTION {GUARD}() FROM "{role}"')
    op.execute(f"REVOKE ALL ON TABLE {TABLE} FROM PUBLIC")
    op.execute(f'REVOKE ALL ON TABLE {TABLE} FROM "{role}"')
    op.execute(f'GRANT SELECT ON TABLE {TABLE} TO "{role}"')
    op.execute(f'GRANT INSERT ({", ".join(INSERT_COLUMNS)}) ON TABLE {TABLE} TO "{role}"')
    op.execute(f"REVOKE ALL ON SEQUENCE {SEQUENCE} FROM PUBLIC")
    op.execute(f'REVOKE ALL ON SEQUENCE {SEQUENCE} FROM "{role}"')
    op.execute(f'GRANT USAGE ON SEQUENCE {SEQUENCE} TO "{role}"')
    op.execute(extended_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    op.execute(
        f"""
        DO $down$
        DECLARE
            n BIGINT;
        BEGIN
            EXECUTE 'LOCK TABLE {TABLE} IN ACCESS EXCLUSIVE MODE';
            EXECUTE 'LOCK TABLE {SUGGESTIONS} IN ACCESS EXCLUSIVE MODE';
            EXECUTE 'SELECT (SELECT count(*) FROM {TABLE}) '
                    '+ (SELECT count(*) FROM {SUGGESTIONS} WHERE worse IS NOT NULL)' INTO n;
            IF n > 0 THEN
                RAISE EXCEPTION 'refusing to downgrade {revision}: % held crossings or worse-marked suggestions', n
                    USING ERRCODE = '{SQLSTATE}';
            END IF;
        END
        $down$;
        """  # noqa: S608 - constant names only
    )
    role = _BASE._app_role()
    op.execute(previous_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {_BASE.ALLOWLIST_FUNCTION}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"DROP TABLE {TABLE}")
    op.execute(f"DROP FUNCTION {GUARD}()")
    op.execute(f'REVOKE INSERT (worse) ON TABLE {SUGGESTIONS} FROM "{role}"')
    op.execute(_M31._suggestions_guard_sql())
    op.execute(f"ALTER TABLE {SUGGESTIONS} DROP COLUMN worse")
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'post')")
