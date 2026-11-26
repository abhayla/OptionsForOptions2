"""P8 (ADR-330 (9)): several standard playbooks per strategy type, and a plan that is a subset of its playbook.

Real PostgreSQL. The content of the standard playbooks is the owner's (Q6): the tests add a second standard ic
playbook (a copy of the first, another name) the way the owner would, with the admin role; the application role never
writes a standard playbook.
"""
from __future__ import annotations

import copy
import json

import pytest
from ofo.adjustment import plan_diff
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
    assert len(standard) == len({"Iron condor: system default", SECOND})
    assert {p.name for p in standard} == {"Iron condor: system default", SECOND}
    assert second in {p.id for p in standard}
    assert all(p.body["strategy_type"] == "ic" for p in standard)


def _tweaked(body: dict, value: str = "9.5") -> dict:
    """The same body with one trigger's first value changed and another trigger switched off."""
    out = copy.deepcopy(body)
    ids = sorted(out["triggers"])
    first = next(t for t in ids if out["triggers"][t].get("monthly"))
    out["triggers"][first]["monthly"][0] = value
    other = next(t for t in ids if t != first and out["triggers"][t]["on"])
    out["triggers"][other]["on"] = False
    return out


def _dump(body: dict) -> str:
    return json.dumps(body, sort_keys=True)


async def test_a_user_is_offered_both_standard_playbooks_and_his_own_and_only_of_his_type(second, app_engine):
    user = _user()
    async with app_engine.connect() as c:
        outer = await c.begin()
        try:
            first = await store.active_for(c, user, "ic")
            own = await store.create(c, user, "ic", "My own ic", first.body)
            other_user_own = await store.create(c, _user(), "ic", "Someone else's", first.body)
            offered = await store.list_for_type(c, user, "ic")
            credit = await store.list_for_type(c, user, "credit")
            assert next(p.id for p in offered if p.is_system) == first.id  # the type's default stays first
            assert {p.id for p in offered} == {first.id, second, own.id}
            assert other_user_own.id not in {p.id for p in offered}
            assert credit
            assert not {p.id for p in credit} & {p.id for p in offered}
            assert all(p.strategy_type == "credit" for p in credit)
        finally:
            await outer.rollback()


async def test_a_plan_is_unaffected_by_an_edit_or_the_removal_of_its_playbook(app_engine):
    user = _user()
    async with app_engine.connect() as c:
        outer = await c.begin()
        try:
            _, strategy = await _with_draft(c, user)
            base = (await store.active_for(c, user, "ic")).body
            own = await store.create(c, user, "ic", "Source", base)
            plan = await store.accept_plan(c, user, strategy.id, own.id)
            await store.save_in_place(c, user, own.id, _tweaked(base), own.version)
            assert (await store.plan_for(c, user, strategy.id)).body == plan.body
            await store.delete(c, user, own.id)
            after = await store.plan_for(c, user, strategy.id)
            assert after.body == plan.body
            assert after.playbook_id is None
        finally:
            await outer.rollback()


async def test_reset_with_the_source_deleted_or_never_set_is_refused_and_the_plan_stays(app_engine):
    user = _user()
    async with app_engine.connect() as c:
        outer = await c.begin()
        try:
            _, strategy = await _with_draft(c, user)
            base = (await store.active_for(c, user, "ic")).body
            own = await store.create(c, user, "ic", "Source", base)
            await store.accept_plan(c, user, strategy.id, own.id, _tweaked(base))
            await store.delete(c, user, own.id)  # the plan keeps its body; playbook_id becomes NULL
            before = await store.plan_for(c, user, strategy.id)
            assert before.playbook_id is None
            with pytest.raises(store.PlaybookStoreError) as refused:  # no playbook pointer: refused, not a no-op
                await store.reset_plan(c, user, strategy.id)
            assert refused.value.code == store.NOT_FOUND
            assert (await store.plan_for(c, user, strategy.id)).body == before.body == _tweaked(base)
            with pytest.raises(store.PlaybookStoreError) as nothing:  # no plan at all
                await store.reset_plan(c, user, strategy.id + 10**6)
            assert nothing.value.code == store.NOT_FOUND
        finally:
            await outer.rollback()


async def test_reset_copies_the_playbook_back_recomputes_the_stop_base_and_the_diff_shows_it(second, app_engine):
    user = _user()
    async with app_engine.connect() as c:
        outer = await c.begin()
        try:
            _, strategy = await _with_draft(c, user)
            source = await store.get(c, user, second)
            plan = await store.accept_plan(c, user, strategy.id, second, _tweaked(source.body), {"max_loss": "1"})
            shown = plan_diff.diff(plan.body, source.body)
            assert len(shown["changed"]) == 1
            assert len(shown["switched_off"]) == 1
            back = await store.reset_plan(c, user, strategy.id, {"max_loss": "2"})
            assert back.body == source.body
            assert back.playbook_id == second
            assert back.stop_base == {"max_loss": "2"}
            assert plan_diff.diff(back.body, source.body) == {"changed": [], "switched_off": []}
        finally:
            await outer.rollback()


async def test_three_ic_strategies_run_three_different_plans(second, app_engine):
    async with app_engine.connect() as c:
        outer = await c.begin()
        try:
            first = await store.active_for(c, _user(), "ic")
            other = await store.get(c, _user(), second)
            bodies = []
            for source, body in ((first, first.body), (other, _tweaked(other.body)),
                                 (first, _tweaked(first.body, "7.25"))):
                user = _user()
                _, strategy = await _with_draft(c, user)
                await store.accept_plan(c, user, strategy.id, source.id, body)
                bodies.append(_dump((await store.plan_for(c, user, strategy.id)).body))
            assert len(set(bodies)) == len(bodies)
        finally:
            await outer.rollback()


async def test_save_this_plan_with_a_name_makes_an_own_playbook_and_adds_no_list_of_plans(app_engine):
    user = _user()
    tables = text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY 1")
    async with app_engine.connect() as c:
        outer = await c.begin()
        try:
            _, strategy = await _with_draft(c, user)
            source = await store.active_for(c, user, "ic")
            plan = await store.accept_plan(c, user, strategy.id, source.id, _tweaked(source.body))
            before = (await c.execute(tables)).all()
            saved = await store.create(c, user, "ic", "From my plan", plan.body)
            assert saved.user_ref == user
            assert not saved.is_system
            assert saved.slug is None
            assert saved.body == plan.body
            assert (await c.execute(tables)).all() == before
            assert saved.id in {p.id for p in await store.list_for_type(c, user, "ic")}
        finally:
            await outer.rollback()


async def test_check_the_plan_refuses_an_added_condition_naming_it(app_engine):
    user = _user()
    async with app_engine.connect() as c:
        outer = await c.begin()
        try:
            _, strategy = await _with_draft(c, user)
            source = await store.active_for(c, user, "ic")
            body = copy.deepcopy(source.body)
            body["triggers"]["T-77"] = copy.deepcopy(next(iter(body["triggers"].values())))
            with pytest.raises(store.PlaybookStoreError) as refused:
                await store.accept_plan(c, user, strategy.id, source.id, body)
            assert refused.value.code == store.BODY_INVALID
            assert refused.value.slots == {"field": "triggers.T-77"}
            assert await store.plan_for(c, user, strategy.id) is None
        finally:
            await outer.rollback()
