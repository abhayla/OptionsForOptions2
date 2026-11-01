"""System playbook versions: append-only, one row per saved version (REQ-169 AC-2..AC-4; ADR-222 (9), (10)).

Spec basis: ADR-222 (10) "the admin changes a SYSTEM playbook in the same step-by-step playbook editor and saves it as
a new version with history and audit; users still only copy system playbooks"; (9) a change applies at the next check,
saved plans kept; REQ-169 AC-2 "Saving writes a new version (the old one is kept, never overwritten) with who, when and
a required reason ... 'Restore this version' makes an earlier version current as a new version".

Copy from: 0033_user_adjustment_preferences.py (append-only guard, statement-level truncate trigger, grants, allow-list
block) keyed by the strategy type and a version number.

Changes (owner-run, one transaction):
- public.system_playbook_versions: strategy_type (one of the 12), version (1, 2, 3 ... per type, no gap), status
  draft|approved, body JSONB (a v1 body of that type), reason (non-empty, at most 500), saved_by (non-empty, at most
  200), restored_from (NULL, or an earlier version of the same type), saved_at DEFAULT clock_timestamp().
  PRIMARY KEY (strategy_type, version). The CURRENT version of a type is its highest version number.
- Append-only guard (BEFORE INSERT OR UPDATE OR DELETE, SQLSTATE OF034, search_path pinned, md5-pinned in the
  allow-list): every UPDATE and DELETE is refused (a change is a new version); an INSERT must be the type's next
  version (max + 1) and a restored_from must name an earlier stored version; the same function on a statement-level
  BEFORE TRUNCATE trigger refuses TRUNCATE.
- Seed: version 1 of each of the 12 system playbooks from backend/ofo/adjustment/system_playbooks.json (0031's checked
  reader), reason "seed", saved_by "release".
- Grants: the application role gets SELECT and column INSERT on strategy_type, version, status, body, reason, saved_by,
  restored_from (never saved_at: the database clock writes it).
- public.ofo_assert_app_role_allowlist: 0033's chain text plus block 26.
- downgrade: refuses (OF034) while any version above the seed exists.

Known bypasses (out of the threat model): the table owner or a superuser can drop or disable the guard, then edit rows.

Revision ID: 0034_system_playbook_versions
Revises: 0033_user_adjustment_preferences
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from alembic import op

revision = "0034_system_playbook_versions"
down_revision = "0033_user_adjustment_preferences"
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


_M33 = _load("0033_user_adjustment_preferences.py", "ofo_migration_0033_for_0034")
_M31 = _load("0031_adjustment_playbooks.py", "ofo_migration_0031_for_0034")
_M16 = _M33._M16
_M4 = _M33._M4
_BASE = _M33._BASE
_INSERT_BEFORE = _M33._INSERT_BEFORE

SEARCH_PATH = _M16.SEARCH_PATH
SQLSTATE = "OF034"  # an update, a delete, a truncate, or an insert that is not the next version

TABLE = "public.system_playbook_versions"
GUARD = "public.system_playbook_versions_guard"
TRIGGER = "system_playbook_versions_guard"
TRUNCATE_TRIGGER = "system_playbook_versions_no_truncate"
LABEL = "system_playbook_versions"
TYPE_KEYS = _M31.TYPE_KEYS
REASON_MAX = 500
SAVED_BY_MAX = 200
SEED_REASON = "seed"
SEED_BY = "release"
INSERT_COLUMNS = ("strategy_type", "version", "status", "body", "reason", "saved_by", "restored_from")
NO_UPDATE: tuple[str, ...] = ()
ALLOWLIST_BLOCK_MARKER = "-- 26. system playbook versions"


def _guard_sql() -> str:
    return f"""
        CREATE OR REPLACE FUNCTION {GUARD}() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = {SEARCH_PATH}
        AS $fn$
        DECLARE
            latest INTEGER;
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'system playbook versions are insert-only: a change is a new version'
                    USING ERRCODE = '{SQLSTATE}';
            END IF;
            SELECT max(v.version) INTO latest FROM {TABLE} v WHERE v.strategy_type = NEW.strategy_type;
            IF NEW.version IS DISTINCT FROM coalesce(latest, 0) + 1 THEN
                RAISE EXCEPTION 'a system playbook version must be the next number after the newest stored one'
                    USING ERRCODE = '{SQLSTATE}';
            END IF;
            IF NEW.restored_from IS NOT NULL AND (NEW.restored_from < 1 OR NEW.restored_from > coalesce(latest, 0)) THEN
                RAISE EXCEPTION 'a restored version must name an earlier stored version of the same playbook'
                    USING ERRCODE = '{SQLSTATE}';
            END IF;
            RETURN NEW;
        END
        $fn$
        """  # noqa: S608 - constant names only


PIN = _M4._md5_body(_guard_sql())
BEFORE_STATEMENT_TRUNCATE = _M33.BEFORE_STATEMENT_TRUNCATE


def _trigger_checks() -> str:
    """0008's shared check with this table's truncate trigger allowed and checked in its own right (as 0033)."""
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
    {ALLOWLIST_BLOCK_MARKER} (REQ-169): SELECT + column INSERT on {", ".join(INSERT_COLUMNS)} only;
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
    END IF;
"""  # noqa: S608 - constant table and function names only


def previous_allowlist_sql() -> str:
    return _M33.extended_allowlist_sql()


def extended_allowlist_sql() -> str:
    """0033's chain text plus block 26. Fails closed (RuntimeError) on a changed shape or a block 26 already in."""
    previous = previous_allowlist_sql()
    if previous.count(_INSERT_BEFORE) != 1 or ALLOWLIST_BLOCK_MARKER in previous or "-- 26." in previous:
        raise RuntimeError("previous allowlist SQL changed shape: cannot add the system playbook version checks safely")
    return previous.replace(_INSERT_BEFORE, _block() + _INSERT_BEFORE, 1)


def _seed_sql() -> list[str]:
    """Version 1 of each of the 12 system playbooks, from the checked-in seed (0031's checked reader)."""
    lit = _M31._literal
    return [f"INSERT INTO {TABLE} (strategy_type, version, status, body, reason, saved_by) VALUES "  # noqa: S608
            f"('{r['strategy_type']}', 1, '{r['status']}', "
            f"{lit(json.dumps(r['body'], sort_keys=True, ensure_ascii=False))}::jsonb, '{SEED_REASON}', '{SEED_BY}')"
            for r in _M31.seed_rows()]


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    types = ", ".join(f"'{t}'" for t in TYPE_KEYS)
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(
        f"""
        CREATE TABLE {TABLE} (
            strategy_type TEXT        NOT NULL CHECK (strategy_type IN ({types})),
            version       INTEGER     NOT NULL CHECK (version >= 1),
            status        TEXT        NOT NULL CHECK (status IN ('draft', 'approved')),
            body          JSONB       NOT NULL CHECK (jsonb_typeof(body) = 'object' AND body->>'schema' = '1'
                                                      AND body->>'strategy_type' = strategy_type),
            reason        TEXT        NOT NULL CHECK (btrim(reason) <> '' AND length(reason) <= {REASON_MAX}),
            saved_by      TEXT        NOT NULL CHECK (btrim(saved_by) <> '' AND length(saved_by) <= {SAVED_BY_MAX}),
            restored_from INTEGER     NULL,
            saved_at      TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (strategy_type, version)
        )
        """
    )
    op.execute(_guard_sql())
    op.execute(f"CREATE TRIGGER {TRIGGER} BEFORE INSERT OR UPDATE OR DELETE ON {TABLE} "
               f"FOR EACH ROW EXECUTE FUNCTION {GUARD}()")
    op.execute(f"CREATE TRIGGER {TRUNCATE_TRIGGER} BEFORE TRUNCATE ON {TABLE} FOR EACH STATEMENT "
               f"EXECUTE FUNCTION {GUARD}()")
    for statement in _seed_sql():
        op.execute(statement)
    op.execute(f"REVOKE ALL ON FUNCTION {GUARD}() FROM PUBLIC")
    op.execute(f'REVOKE ALL ON FUNCTION {GUARD}() FROM "{role}"')
    op.execute(f"REVOKE ALL ON TABLE {TABLE} FROM PUBLIC")
    op.execute(f'REVOKE ALL ON TABLE {TABLE} FROM "{role}"')
    op.execute(f'GRANT SELECT ON TABLE {TABLE} TO "{role}"')
    op.execute(f'GRANT INSERT ({", ".join(INSERT_COLUMNS)}) ON TABLE {TABLE} TO "{role}"')
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
            EXECUTE 'SELECT count(*) FROM {TABLE} WHERE version > 1' INTO n;
            IF n > 0 THEN
                RAISE EXCEPTION 'refusing to downgrade {revision}: % saved system playbook versions', n
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
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'post')")
