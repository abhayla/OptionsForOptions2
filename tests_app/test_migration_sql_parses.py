"""Every statement migrations 0001-0007 execute parses with PostgreSQL's own parser, before CI's database runs it.

Class (W-056 fix round 1, review C1): SQL written as Python strings is only checked when PostgreSQL first runs it; a
quoted list interpolated inside a single-quoted literal (RAISE EXCEPTION '... 'NFO', 'BFO'') broke the CI upgrade.
Detection: render every upgrade() and downgrade() statement with a recording ``op`` (no database), then parse each
with pglast (libpg_query, PostgreSQL's real parser). DO blocks and LANGUAGE plpgsql function bodies are parsed with
the PL/pgSQL parser too, so a bad literal inside a body is caught. Self-test: a planted C1 statement must fail.
"""

from __future__ import annotations

import importlib.util
import re
import types
from pathlib import Path

import pytest

pglast = pytest.importorskip("pglast", reason="pglast (libpg_query) is not installed; CI installs it from "
                                                "requirements-app.txt and runs this test")

VERSIONS = Path(__file__).resolve().parents[1] / "backend" / "ofo_app" / "alembic" / "versions"
MIGRATIONS = ("0001_baseline_ledger_clock", "0002_audit_store", "0003_catalogue_store", "0004_broker_instruments",
              "0005_contract_lifecycle", "0006_index_segments", "0007_broker_sessions")
_DO = re.compile(r"^\s*DO\s+(\$\w*\$)(.*)\1\s*;?\s*$", re.DOTALL)


def _load(name: str):
    loader_spec = importlib.util.spec_from_file_location(f"ofo_parse_{name}", VERSIONS / f"{name}.py")
    module = importlib.util.module_from_spec(loader_spec)
    loader_spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _patch_op(module, recorder, seen: set[int]) -> None:
    """Point ``op`` at the recorder in the module and in every earlier migration it loaded (0004's downgrade calls
    0003's upgrade, for example)."""
    if id(module) in seen:
        return
    seen.add(id(module))
    if hasattr(module, "op"):
        module.op = recorder
    for value in vars(module).values():
        if isinstance(value, types.ModuleType) and getattr(value, "__name__", "").startswith("ofo_migration"):
            _patch_op(value, recorder, seen)


def _statements(name: str, phase: str) -> list[str]:
    module = _load(name)
    out: list[str] = []
    _patch_op(module, types.SimpleNamespace(execute=lambda sql, *a, **k: out.append(str(sql))), set())
    getattr(module, phase)()
    return out


def _parse_plpgsql(sql: str) -> None:
    """PL/pgSQL parse via libpg_query. Only the parse matters (it raises ParseError on bad syntax); the JSON it returns
    is not decoded, because libpg_query's JSON for some valid bodies is not valid JSON (pglast.parse_plpgsql fails to
    decode it on 0001-0004's real functions)."""
    pglast.parser.parse_plpgsql_json(sql)


def check_parses(sql: str) -> None:
    """Raise if PostgreSQL's parser rejects the statement or any PL/pgSQL body in it."""
    match = _DO.match(sql)
    if match:  # a DO block: its body is PL/pgSQL; wrap it as a function so the PL/pgSQL parser checks it
        body_quote, body = match.group(1), match.group(2)
        _parse_plpgsql(
            f"CREATE FUNCTION ofo_parse_check() RETURNS void LANGUAGE plpgsql AS {body_quote}{body}{body_quote}")
        return
    for raw in pglast.parser.parse_sql(sql):
        stmt = raw.stmt
        if type(stmt).__name__ == "CreateFunctionStmt":
            languages = [o.arg.sval for o in (stmt.options or ()) if o.defname == "language"]
            if languages == ["plpgsql"]:
                _parse_plpgsql(sql)


CASES = [(name, phase, i, sql) for name in MIGRATIONS for phase in ("upgrade", "downgrade")
         for i, sql in enumerate(_statements(name, phase))]


@pytest.mark.parametrize("name, phase, index, sql", CASES, ids=[f"{n}-{p}-{i}" for n, p, i, _ in CASES])
def test_every_migration_statement_parses(name: str, phase: str, index: int, sql: str) -> None:
    check_parses(sql)


def test_every_migration_renders_statements() -> None:
    counts = {(n, p): sum(1 for c in CASES if c[:2] == (n, p)) for n in MIGRATIONS for p in ("upgrade", "downgrade")}
    assert all(v > 0 for v in counts.values()), counts


C1_DO = """
        DO $chk$
        BEGIN
            IF EXISTS (SELECT 1 FROM public.catalogue_contracts WHERE exchange_segment IS NULL) THEN
                RAISE EXCEPTION 'a stored contract has an exchange outside 'NFO', 'BFO'';
            END IF;
        END
        $chk$;
        """
C1_FUNCTION = """
        CREATE FUNCTION public.zz_c1() RETURNS trigger LANGUAGE plpgsql AS $fn$
        BEGIN
            RAISE EXCEPTION 'outside 'NFO', 'BFO'';
        END
        $fn$
        """


@pytest.mark.parametrize("planted", [C1_DO, C1_FUNCTION, "SELECT 'outside 'NFO', 'BFO''"], ids=["do", "fn", "sql"])
def test_self_test_a_planted_c1_quote_bug_fails_the_parse(planted: str) -> None:
    with pytest.raises(pglast.parser.ParseError):
        check_parses(planted)
    check_parses(planted.replace("'NFO', 'BFO'", "NFO, BFO"))  # the same statement without the bug parses
