"""Migration 0060 (#753; ADR-250, ADR-252 addendum): ``strategy_adjustment_plans.accepted_at`` is stamped only when the
plan switches to a different playbook; an edit of the plan body alone never moves it.

Spec basis: ADR-250 ("a strategy plan saved before ADR-247 keeps its own stop alerts exactly as saved ... and does NOT
gain the 2x-credit stop ... nothing under a live position changes without the user choosing it"); ADR-252 addendum
("Switching a plan to a newer system playbook version is a new acceptance (accepted_at = the switch time)");
ADR-330 (1) (the stop base is fixed at entry; an edit recomputes it, this fix does not touch that).

Real case: strategy 82 (owner's live iron condor, saved 5 Nov before the ADR-247 version) whose target was edited:
0041's trigger restamped accepted_at, so the plan read as saved after ADR-247 and gained the 2x-credit stop.
Every test runs in one outer transaction that is rolled back.
"""
from __future__ import annotations

import copy
import datetime
import json

import pytest
from ofo_app import adjustment_check as check
from ofo_app import playbook_store as pbs
from ofo_app import settings_in_force as sif
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_strategy_store import _user, _with_draft

DAY = datetime.timedelta(days=1)


@pytest.fixture
async def db(admin_engine):
    async with admin_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def _backdate(db, strategy_id: int, when: datetime.datetime) -> None:
    """The owner's database holds plans saved long ago: set accepted_at as the table owner with the guard off."""
    await db.execute(text("ALTER TABLE public.strategy_adjustment_plans DISABLE TRIGGER USER"))
    await db.execute(text("UPDATE public.strategy_adjustment_plans SET accepted_at = :t WHERE strategy_id = :s"),
                     {"t": when, "s": strategy_id})
    await db.execute(text("ALTER TABLE public.strategy_adjustment_plans ENABLE TRIGGER USER"))


async def _old_plan(db):
    """A strategy-82-shaped plan: an iron condor plan accepted a day before the ADR-247 cutoff."""
    user = _user()
    _, strategy = await _with_draft(db, user)
    system = await pbs.active_for(db, user, "ic")
    await pbs.accept_plan(db, user, strategy.id, system.id)
    cutoff = await pbs.adr247_saved_at(db)
    assert cutoff is not None
    await _backdate(db, strategy.id, cutoff - DAY)
    plan = await pbs.plan_for(db, user, strategy.id)
    assert plan.accepted_at == cutoff - DAY
    return user, strategy, system, plan


async def _resolved(db, user, strategy):
    return await check.resolve(db, user, strategy.id, "ic")


def _with_target(body: dict, target: str) -> dict:
    out = copy.deepcopy(body)
    out["guards"]["profit_target_pct_of_max_profit"] = target
    return out


async def test_core_editing_only_the_target_of_a_pre_adr247_plan_keeps_accepted_at_and_its_stops(db):
    user, strategy, system, old = await _old_plan(db)
    before = await _resolved(db, user, strategy)
    assert before.saved_before_adr247 is True and sif.credit_line_applies(before) is False

    edited = await pbs.accept_plan(db, user, strategy.id, old.playbook_id, _with_target(old.body, "35"))

    assert edited.body["guards"]["profit_target_pct_of_max_profit"] == "35"  # the edit did save
    assert edited.accepted_at == old.accepted_at  # not restamped
    after = await _resolved(db, user, strategy)
    assert after.saved_before_adr247 is True
    assert sif.credit_line_applies(after) is False  # still no 2x-credit stop (ADR-250)
    assert after.playbook_id == system.id


async def test_several_body_edits_with_the_playbook_unchanged_never_move_accepted_at(db):
    user, strategy, _, old = await _old_plan(db)
    body = old.body
    for target in ("40", "45", "50"):
        body = _with_target(body, target)
        plan = await pbs.accept_plan(db, user, strategy.id, old.playbook_id, body)
        assert plan.accepted_at == old.accepted_at


async def test_switching_to_another_playbook_is_a_new_acceptance(db):
    user, strategy, system, old = await _old_plan(db)
    own = await pbs.duplicate(db, user, system.id, "My IC")
    switched = await pbs.accept_plan(db, user, strategy.id, own.id, accepts=True)
    assert switched.playbook_id == own.id
    assert switched.accepted_at > old.accepted_at
    assert switched.accepted_at >= await pbs.adr247_saved_at(db)
    assert await check.plan_saved_before_adr247(db, switched) is False


async def test_a_switch_to_a_playbook_with_the_same_body_still_stamps(db):
    """0041's own case: the body is equal, only the playbook differs."""
    user, strategy, system, old = await _old_plan(db)
    own = await pbs.duplicate(db, user, system.id, "Same body")
    switched = await pbs.accept_plan(db, user, strategy.id, own.id, old.body, accepts=True)
    assert switched.body == old.body and switched.playbook_id == own.id
    assert switched.accepted_at > old.accepted_at


async def test_a_switch_plus_a_body_edit_stamps(db):
    user, strategy, system, old = await _old_plan(db)
    own = await pbs.duplicate(db, user, system.id, "Other")
    switched = await pbs.accept_plan(db, user, strategy.id, own.id, _with_target(old.body, "33"), accepts=True)
    assert switched.accepted_at > old.accepted_at


async def test_an_edit_after_the_cutoff_on_a_new_plan_behaves_as_today(db):
    user = _user()
    _, strategy = await _with_draft(db, user)
    system = await pbs.active_for(db, user, "ic")
    first = await pbs.accept_plan(db, user, strategy.id, system.id)
    assert first.accepted_at >= await pbs.adr247_saved_at(db)
    resolved = await _resolved(db, user, strategy)
    assert resolved.saved_before_adr247 is False and sif.credit_line_applies(resolved) is True
    edited = await pbs.accept_plan(db, user, strategy.id, first.playbook_id, _with_target(first.body, "35"))
    assert edited.accepted_at >= await pbs.adr247_saved_at(db)  # still after the cutoff (0041: restamped; 0060: kept)
    after = await _resolved(db, user, strategy)
    assert after.saved_before_adr247 is False and sif.credit_line_applies(after) is True


async def test_a_sheet_edit_that_re_points_a_null_playbook_plan_keeps_accepted_at(db):
    """Finding 2: an old plan whose playbook was deleted (playbook_id NULL) is re-pointed at the active playbook by a
    PUT sheet edit (accepts False): it must still read as saved before ADR-247, with no 2x-credit line."""
    user, strategy, system, old = await _old_plan(db)
    await db.execute(text("UPDATE public.strategy_adjustment_plans SET playbook_id = NULL WHERE strategy_id = :s"),
                     {"s": strategy.id})  # what ON DELETE SET NULL does
    nulled = await pbs.plan_for(db, user, strategy.id)
    assert nulled.playbook_id is None and nulled.accepted_at == old.accepted_at
    edited = await pbs.accept_plan(db, user, strategy.id, system.id, _with_target(old.body, "35"))
    assert edited.playbook_id == system.id and edited.accepted_at == old.accepted_at
    after = await _resolved(db, user, strategy)
    assert after.saved_before_adr247 is True and sif.credit_line_applies(after) is False


async def test_a_playbook_change_without_the_acceptance_signal_does_not_stamp(db):
    user, strategy, system, old = await _old_plan(db)
    own = await pbs.duplicate(db, user, system.id, "Pointer only")
    moved = await pbs.accept_plan(db, user, strategy.id, own.id)  # accepts False: a sheet edit
    assert moved.playbook_id == own.id and moved.accepted_at == old.accepted_at


async def test_post_with_the_same_playbook_id_is_a_new_acceptance(db):
    user, strategy, _, old = await _old_plan(db)
    again = await pbs.accept_plan(db, user, strategy.id, old.playbook_id, accepts=True)
    assert again.playbook_id == old.playbook_id and again.accepted_at > old.accepted_at
    assert await check.plan_saved_before_adr247(db, again) is False


async def test_reset_to_playbook_on_the_strategy_82_shape_is_a_new_acceptance_with_the_credit_line(db):
    user, strategy, _, old = await _old_plan(db)
    body = copy.deepcopy(old.body)
    body["guards"]["stop_line_pct_of_margin"] = "4"
    body["triggers"]["T-16"]["on"] = True  # the pre-ADR-247 shape: margin stop and T-16 on
    await db.execute(text("ALTER TABLE public.strategy_adjustment_plans DISABLE TRIGGER USER"))
    await db.execute(text("UPDATE public.strategy_adjustment_plans SET body = CAST(:b AS JSONB) "
                          "WHERE strategy_id = :s"), {"b": json.dumps(body), "s": strategy.id})  # saved long ago
    await db.execute(text("ALTER TABLE public.strategy_adjustment_plans ENABLE TRIGGER USER"))
    before = await _resolved(db, user, strategy)
    assert before.saved_before_adr247 is True and sif.credit_line_applies(before) is False
    reset = await pbs.reset_plan(db, user, strategy.id)
    assert reset.accepted_at > old.accepted_at
    after = await _resolved(db, user, strategy)
    assert after.saved_before_adr247 is False and sif.credit_line_applies(after) is True


async def test_the_signal_is_cleared_after_an_acceptance_so_a_later_edit_in_the_same_transaction_keeps(db):
    user, strategy, _, old = await _old_plan(db)
    accepted = await pbs.accept_plan(db, user, strategy.id, old.playbook_id, accepts=True)
    assert (await db.execute(text("SELECT current_setting('ofo.plan_acceptance', true)"))).scalar_one() == "off"
    edited = await pbs.accept_plan(db, user, strategy.id, old.playbook_id, _with_target(old.body, "31"))
    assert edited.accepted_at == accepted.accepted_at


async def test_the_first_save_stamps_without_any_signal(db):
    user = _user()
    _, strategy = await _with_draft(db, user)
    system = await pbs.active_for(db, user, "ic")
    first = await pbs.accept_plan(db, user, strategy.id, system.id)
    assert first.accepted_at >= await pbs.adr247_saved_at(db)


# Which route stamps is pinned at the route level (POST, PUT edit, PUT with accept, Reset, the lock-timeout path) in
# test_plan_accept_routes.py; no source scan here (R2-MINOR-4).


async def test_the_application_role_cannot_set_accepted_at_directly(app_engine):
    async with app_engine.connect() as c:
        outer = await c.begin()
        try:
            got = {priv: (await c.execute(text(
                "SELECT has_column_privilege('ofo_app', 'public.strategy_adjustment_plans', 'accepted_at', :p)"),
                {"p": priv})).scalar_one() for priv in ("INSERT", "UPDATE")}
            assert got == {"INSERT": False, "UPDATE": False}
            user = _user()
            _, strategy = await _with_draft(c, user)
            system = await pbs.active_for(c, user, "ic")
            await pbs.accept_plan(c, user, strategy.id, system.id)
            with pytest.raises(DBAPIError, match="permission denied"):
                async with c.begin_nested():
                    await c.execute(text("UPDATE public.strategy_adjustment_plans "
                                         "SET accepted_at = now() - interval '9 days' WHERE strategy_id = :s"),
                                    {"s": strategy.id})
        finally:
            await outer.rollback()


async def test_the_stop_base_still_follows_an_edit_and_not_this_fix(db):
    """ADR-330 (1): a plan edit stores the new base (COALESCE) and an edit with none keeps the stored one."""
    user, strategy, _, old = await _old_plan(db)
    one = await pbs.accept_plan(db, user, strategy.id, old.playbook_id, _with_target(old.body, "35"), {"max_loss": "1"})
    assert one.stop_base == {"max_loss": "1"} and one.accepted_at == old.accepted_at
    two = await pbs.accept_plan(db, user, strategy.id, old.playbook_id, _with_target(old.body, "36"))
    assert two.stop_base == {"max_loss": "1"} and two.accepted_at == old.accepted_at
    three = await pbs.accept_plan(db, user, strategy.id, old.playbook_id, _with_target(old.body, "36"),
                                  {"max_loss": "2"})
    assert three.stop_base == {"max_loss": "2"} and three.accepted_at == old.accepted_at
