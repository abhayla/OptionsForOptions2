"""GC-MERGE1 (#649) guard: every test file runs on its own copy of the migrated database (tests_app/conftest.py
``_fresh_database_per_file``), so a file's result never depends on the files that ran before it."""
from __future__ import annotations

import os

import conftest
import pytest
from sqlalchemy import text


def test_the_per_file_database_fixture_is_autouse_and_module_scoped(request):
    assert "_fresh_database_per_file" in request.fixturenames  # autouse: no file can forget it
    defs = request._fixturemanager.getfixturedefs("_fresh_database_per_file", request.node)
    assert defs and defs[-1].scope == "module"  # once per test FILE


def test_a_failed_copy_raises_and_leaves_no_record():
    """Fail closed: a copy that cannot be made is an error for the file, never a quiet fall-back to the shared DB."""
    before = list(conftest.CLONES_MADE)
    with pytest.raises(Exception):  # noqa: B017 - any refusal (no server, no privilege) must raise
        conftest.clone_for_file("postgresql+asyncpg://nobody:x@127.0.0.1:1/ofo_test",
                                "postgresql+asyncpg://ofo_app:x@127.0.0.1:1/ofo_test")
    assert before == conftest.CLONES_MADE


async def test_this_file_runs_on_its_own_copy(app_engine, admin_engine):
    if not conftest.CLONES_MADE:
        pytest.fail("TEST_ADMIN_DATABASE_URL is set but no per-file copy was made")
    mine = conftest.CLONES_MADE[-1]
    assert len(set(conftest.CLONES_MADE)) == len(conftest.CLONES_MADE)  # each file had a different database
    async with app_engine.connect() as conn:
        assert (await conn.execute(text("SELECT current_database()"))).scalar_one() == mine
    async with admin_engine.connect() as conn:
        assert (await conn.execute(text("SELECT current_database()"))).scalar_one() == mine
    for name in ("TEST_DATABASE_URL", "TEST_ADMIN_DATABASE_URL"):
        assert conftest._db_name(os.environ[name]) == mine
