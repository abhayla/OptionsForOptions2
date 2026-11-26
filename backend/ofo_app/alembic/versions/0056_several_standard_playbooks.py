"""Several STANDARD playbooks per strategy type: the one-system-per-type unique index is dropped, each standard playbook
gets a stable slug (P8; ADR-330 (9)).

Spec basis: ADR-330 (9) ("SPEC CHANGE: REQ-158 ... becomes several standard playbooks per strategy type"; the content of
the standard playbooks is the owner's, Q6: this builds the mechanism only, the 12 existing system defaults become the
first standard playbook of each type, names unchanged); ADR-222 (10) / REQ-169 (a standard
playbook's versions); ADR-048.
Copy from: 0055_plan_stop_base.py (allow-list text built on the previous revision's, failing closed) and 0031 (the
playbook guard, which this migration does not touch).

Changes (owner-run, one transaction):
- public.adjustment_playbooks: drops the UNIQUE (strategy_type) WHERE is_system index (0031 SYSTEM_INDEX); adds
  slug TEXT NULL (a short lower-case word-and-dash name, only on a standard playbook) with UNIQUE (strategy_type, slug)
  WHERE is_system; sets slug = '<type>-default' on the 12 existing system rows (their name, body, id unchanged; the
  0031 guard counts the UPDATE as a version bump of the row, which no reader uses: a standard playbook's shown version
  comes from system_playbook_versions).
- system_playbook_versions is NOT re-keyed. It stays keyed by strategy type and holds the history of the type's
  '<type>-default' playbook (REQ-169, the append-only 0034 guard is md5-pinned and is not touched). A further
  standard playbook (any other slug) keeps its body in its own adjustment_playbooks row; the store reads the versions
  table only for the '<type>-default' row. Why: re-keying needs a new primary key and guard on the pinned table, and
  code at e01f747 must keep running against this schema.
- Grants: none (the application role never writes a standard playbook; it has no grant on slug).
- public.ofo_assert_app_role_allowlist: 0055's chain text plus block 36 (the slug column and its unique index exist,
  the one-system index is gone).
- downgrade: refuses (SQLSTATE of 0031, counted) while any type has a second standard playbook; else drops the slug
  index, check and column and restores the one-system index and 0055's allow-list text.

Old-code compatibility: ``playbook_store._SELECT_SYSTEM`` (e01f747) returns the type's one system row; with only the 12
seeded rows nothing changes. A second standard row of a type makes that old query ambiguous: ship the new code first.

Revision ID: 0056_several_standard_playbooks
Revises: 0055_plan_stop_base
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0056_several_standard_playbooks"
down_revision = "0055_plan_stop_base"
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


_M31 = _load("0031_adjustment_playbooks.py", "ofo_migration_0031_for_0056")
_M34 = _load("0034_system_playbook_versions.py", "ofo_migration_0034_for_0056")
_M55 = _load("0055_plan_stop_base.py", "ofo_migration_0055_for_0056")
_BASE = _M31._BASE
TABLE = _M31.PLAYBOOKS
SYSTEM_INDEX = _M31.SYSTEM_INDEX
SLUG_INDEX = "adjustment_playbooks_standard_slug"
SLUG_SHAPE = "adjustment_playbooks_slug_shape"
SLUG_PATTERN = "^[a-z0-9]+(-[a-z0-9]+)*$"
SLUG_MAX = 60
SQLSTATE = _M31.SQLSTATE
ALLOWLIST_BLOCK_MARKER = "-- 36. several standard playbooks"
_INSERT_BEFORE = _M34._INSERT_BEFORE


def previous_allowlist_sql() -> str:
    return _M55.extended_allowlist_sql()


def _block() -> str:
    """Runs inside public.ofo_assert_app_role_allowlist (`problems` the refusals)."""
    return f"""
    {ALLOWLIST_BLOCK_MARKER} (ADR-330 (9)): the standard-playbook slug column and its unique index exist, the
    --    one-system-per-type index is gone
    IF phase = 'post' THEN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public'
                       AND table_name = 'adjustment_playbooks' AND column_name = 'slug') THEN
            problems := problems || 'column {TABLE}.slug is missing'::TEXT;
        END IF;
        IF to_regclass('public.{SLUG_INDEX}') IS NULL THEN
            problems := problems || 'index {SLUG_INDEX} is missing'::TEXT;
        END IF;
        IF to_regclass('public.{SYSTEM_INDEX}') IS NOT NULL THEN
            problems := problems || 'index {SYSTEM_INDEX} still limits a type to one standard playbook'::TEXT;
        END IF;
    END IF;
"""  # noqa: S608 - constant names only


def extended_allowlist_sql() -> str:
    """0055's chain text plus block 36. Fails closed (RuntimeError) on a changed shape or a block 36 already in."""
    previous = previous_allowlist_sql()
    if previous.count(_INSERT_BEFORE) != 1 or ALLOWLIST_BLOCK_MARKER in previous or "-- 36." in previous:
        raise RuntimeError("previous allowlist SQL changed shape: cannot add the standard playbook checks safely")
    return previous.replace(_INSERT_BEFORE, _block() + _INSERT_BEFORE, 1)


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(f"DROP INDEX public.{SYSTEM_INDEX}")
    op.execute(f"ALTER TABLE {TABLE} ADD COLUMN slug TEXT NULL")
    op.execute(f"ALTER TABLE {TABLE} ADD CONSTRAINT {SLUG_SHAPE} CHECK (slug IS NULL OR "
               f"(is_system AND slug ~ '{SLUG_PATTERN}' AND length(slug) <= {SLUG_MAX}))")
    op.execute(f"UPDATE {TABLE} SET slug = strategy_type || '-default' WHERE is_system")  # noqa: S608
    op.execute(f"CREATE UNIQUE INDEX {SLUG_INDEX} ON {TABLE} (strategy_type, slug) WHERE is_system")
    op.execute(extended_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    role = _BASE._app_role()
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'pre')")
    op.execute(
        f"""
        DO $down$
        DECLARE
            n BIGINT;
        BEGIN
            EXECUTE 'LOCK TABLE {TABLE} IN ACCESS EXCLUSIVE MODE';
            SELECT count(*) INTO n FROM (SELECT strategy_type FROM {TABLE} WHERE is_system
                                         GROUP BY strategy_type HAVING count(*) > 1) t;
            IF n > 0 THEN
                RAISE EXCEPTION 'refusing to downgrade {revision}: % strategy types hold several standard playbooks', n
                    USING ERRCODE = '{SQLSTATE}';
            END IF;
        END
        $down$;
        """  # noqa: S608 - constant names only
    )
    op.execute(f"DROP INDEX public.{SLUG_INDEX}")
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT {SLUG_SHAPE}")
    op.execute(f"ALTER TABLE {TABLE} DROP COLUMN slug")
    op.execute(f"CREATE UNIQUE INDEX {SYSTEM_INDEX} ON {TABLE} (strategy_type) WHERE is_system")
    op.execute(previous_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {_BASE.ALLOWLIST_FUNCTION}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {_BASE.ALLOWLIST_FUNCTION}('{role}', 'post')")
