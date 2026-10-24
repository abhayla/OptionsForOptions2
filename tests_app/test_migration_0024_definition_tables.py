"""REQ-077 AC-4 (chunk 2 review, area B): migration 0024's downgrade checks EVERY table that stores a definition.

DB-free: reads every migration file's CREATE TABLE statements and finds each table with a JSONB ``definition`` column;
0024's DEFINITION_TABLES (the one list its downgrade checks) must name exactly that set. A new definition table without
a downgrade check fails here. Fails closed: a CREATE TABLE whose name or body cannot be resolved is an error naming its
file, never a silent skip.
"""
from __future__ import annotations

import importlib.util
import pathlib
import re

VERSIONS_DIR = pathlib.Path(__file__).resolve().parent.parent / "backend" / "ofo_app" / "alembic" / "versions"
CREATE = re.compile(r"CREATE TABLE (?:IF NOT EXISTS )?(\S+) \(")
CLOSE = re.compile(r"^\s*\)\s*$", re.MULTILINE)
DEFINITION_COLUMN = re.compile(r"^\s*definition\s+JSONB\b", re.MULTILINE | re.IGNORECASE)
ADDED_DEFINITION = re.compile(r"ADD COLUMN (?:IF NOT EXISTS )?definition\b", re.IGNORECASE)
KNOWN = {"public.strategies", "public.strategy_history", "public.strategy_versions"}


def _table_name(raw: str, source: str, where: str) -> str:
    """``{NAME}`` resolved through the file's own ``NAME = "..."`` constant; anything else fails closed."""
    placeholder = re.fullmatch(r"\{([A-Z_][A-Z0-9_]*)\}", raw)
    if placeholder is None:
        raise AssertionError(f"{where}: CREATE TABLE name {raw!r} is not a {{CONSTANT}} this test can resolve")
    found = re.search(rf'^{placeholder.group(1)}\s*(?::[^=]+)?=\s*"([^"]+)"', source, re.MULTILINE)
    if found is None:
        raise AssertionError(f"{where}: the constant {placeholder.group(1)} has no plain string value")
    return found.group(1)


def definition_tables_in_migrations() -> set[str]:
    tables: set[str] = set()
    files = sorted(VERSIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.py"))
    assert files, f"no migration files under {VERSIONS_DIR}"
    for path in files:
        source = path.read_text(encoding="utf-8")
        assert not ADDED_DEFINITION.search(source), f"{path.name}: a definition column added by ALTER is not parsed"
        for match in CREATE.finditer(source):
            close = CLOSE.search(source, match.end())
            if close is None:
                raise AssertionError(f"{path.name}: CREATE TABLE {match.group(1)} has no closing line")
            if DEFINITION_COLUMN.search(source[match.end():close.start()]):
                tables.add(_table_name(match.group(1), source, path.name))
    return tables


def _downgrade_tables() -> tuple[str, ...]:
    path = VERSIONS_DIR / "0024_typed_entry_mark.py"
    found = importlib.util.spec_from_file_location("ofo_migration_0024_table_list_test", path)
    assert found is not None and found.loader is not None
    module = importlib.util.module_from_spec(found)
    found.loader.exec_module(module)
    return module.DEFINITION_TABLES


def test_the_downgrade_checks_every_table_that_stores_a_definition():
    """Attack item 2: strategies, strategy_history (0008) and strategy_versions (0022) today; a fourth fails here."""
    found = definition_tables_in_migrations()
    assert found >= KNOWN, found
    assert set(_downgrade_tables()) == found


def test_the_scan_fails_closed_on_a_name_it_cannot_resolve():
    """Standing item (c): an unresolvable CREATE TABLE name is an error naming its source, never skipped."""
    for raw in ("public.loose", "{lower}", "{MISSING}"):
        try:
            _table_name(raw, 'OTHER = "public.other"\n', "fake.py")
        except AssertionError as err:
            assert "fake.py" in str(err)
        else:
            raise AssertionError(f"{raw} was resolved")
