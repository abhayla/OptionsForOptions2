"""P8 (ADR-330 (9)): several standard playbooks per strategy type, and a plan that is a subset of its playbook.

Real PostgreSQL. The content of the standard playbooks is the owner's (Q6): the tests add a second standard ic
playbook (a copy of the first, another name) the way the owner would, with the admin role; the application role never
writes a standard playbook.
"""
from __future__ import annotations

import copy
import json

import pytest
from ofo_app import playbook_store as store
from sqlalchemy import text
from test_strategy_store import _user, _with_draft

SECOND = "ic: second standard"


async def _add_standard(admin_engine, name: str = SECOND, slug: str = "ic-second") -> int:
    """A second standard ic playbook, committed (cleaned by ``_remove_standard``)."""
    async with admin_engine.begin() as c:
        body = (await c.execute(text("SELECT body::text FROM public.adjustment_playbooks "
                                     "WHERE is_system AND strategy_type = 'ic' ORDER BY id LIMIT 1"))).scalar_one()
        return (await c.execute(text(
            "INSERT INTO public.adjustment_playbooks (user_ref, strategy_type, name, is_system, status, body, slug) "
            "VALUES (NULL, 'ic', :name, true, 'approved', CAST(:body AS JSONB), :slug) RETURNING id"),
            {"name": name, "body": body, "slug": slug})).scalar_one()


async def _remove_standard(admin_engine, playbook_id: int) -> None:
    async with admin_engine.begin() as c:
        await c.execute(text("DELETE FROM public.adjustment_playbooks WHERE id = :id AND is_system"),
                        {"id": playbook_id})


@pytest.fixture
async def second(admin_engine):
    playbook_id = await _add_standard(admin_engine)
    try:
        yield playbook_id
    finally:
        await _remove_standard(admin_engine, playbook_id)


async def test_two_standard_ic_playbooks_coexist(second, app_engine):
    async with app_engine.connect() as c:
        rows = await store.list_for_type(c, _user(), "ic")
    standard = [p for p in rows if p.is_system]
    assert len(standard) == 2
    assert {p.name for p in standard} == {"ic: system default", SECOND}
    assert second in {p.id for p in standard}
    assert all(p.body["strategy_type"] == "ic" for p in standard)
