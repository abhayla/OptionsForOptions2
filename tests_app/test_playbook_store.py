"""GC-ADJ2 step 1A (REQ-158 AC-1..AC-7, REQ-161 AC-2/AC-3, REQ-112 AC-1/AC-2/AC-4): the playbook store and its
database guards, as the limited application role (the guards are the protection; the store is the polite path).

Spec basis (quoted): REQ-158 AC-3 "a duplicate name is refused with "A playbook named <name> already exists for
<type>""; AC-4 "Exactly one playbook is active per type for each user ... Deleting the active playbook makes the type's
system playbook active and says so"; AC-5 "Deleting or editing a playbook never changes a strategy already tracking";
AC-6 "A system playbook can only be saved as a new playbook". Real PostgreSQL; every test rolls back.
"""
from __future__ import annotations

import copy
from decimal import Decimal

import pytest
from ofo.adjustment.playbook_types import SHOWN_NAMES, TYPE_KEYS
from ofo.errors import render
from ofo_app import playbook_store as pb
from ofo_app import strategy_store as store
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_strategy_store import _user, _with_draft

STAGES = {"weekly": [{"name": "Early", "from": 5, "to": None}, {"name": "Last day", "from": 0, "to": 4}],
          "monthly": [{"name": "Early", "from": 10, "to": None}, {"name": "Last 2 days", "from": 0, "to": 9}]}


def _body(strategy_type: str = "ic", value: str = "0.5") -> dict:
    return {"schema": 1, "strategy_type": strategy_type, "stages": copy.deepcopy(STAGES),
            "triggers": {"T-01": {"on": True, "label": "Spot within this % of a short strike", "unit": "%",
                                  "cmp": "le", "weekly": [value, ""], "monthly": ["1.0", "0.5"]}},
            "rules": [{"id": "T-01", "any_of": ["T-01"]}]}


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def _scalar(db, sql: str, **params):
    return (await db.execute(text(sql), params)).scalar_one()


async def _refused(db, sql: str, match: str, **params) -> None:
    """`match` is a SQLSTATE (OF031: asyncpg keeps it off the message) or a regex on the message."""
    with pytest.raises(DBAPIError, match=None if match.startswith("OF0") else match) as refused:
        async with db.begin_nested():
            await db.execute(text(sql), params)
    if match.startswith("OF0"):
        orig = refused.value.orig
        assert match in {getattr(orig, "sqlstate", None), getattr(orig.__cause__, "sqlstate", None)}


# --- AC-1 / AC-2 / AC-7: the seeded system playbooks -------------------------------------------------------------

async def test_one_system_playbook_per_type_iron_condor_approved_rest_draft(db):
    rows = (await db.execute(text("SELECT strategy_type, name, status, body->>'strategy_type' "
                                  "FROM public.adjustment_playbooks WHERE is_system ORDER BY strategy_type"))).all()
    assert sorted(r[0] for r in rows) == sorted(TYPE_KEYS)
    for strategy_type, name, status, body_type in rows:
        assert name == f"{SHOWN_NAMES[strategy_type]}: system default"
        assert status == ("approved" if strategy_type == "ic" else "draft")
        assert body_type == strategy_type


async def test_a_new_user_sees_only_the_system_playbook_and_it_is_active(db):
    user = _user()
    listed = await pb.list_for_type(db, user, "ic")
    assert [p.is_system for p in listed] == [True]
    assert (await pb.active_for(db, user, "ic")).id == listed[0].id


async def test_playbook_values_are_stored_data_a_changed_row_is_read_back_without_a_release(admin_engine):
    async with admin_engine.connect() as conn:  # the owner (a migration) edits a system row; the store reads it
        trans = await conn.begin()
        try:
            system = await pb.active_for(conn, _user(), "credit")
            changed = _body("credit", "0.9")
            await conn.execute(text("UPDATE public.adjustment_playbooks SET body = CAST(:b AS JSONB) WHERE id = :id"),
                               {"b": pb._dump(changed), "id": system.id})
            again = await pb.active_for(conn, _user(), "credit")
            assert again.body["triggers"]["T-01"]["weekly"] == ["0.9", ""]
            assert again.version == system.version + 1  # the guard bumps the version on every update
        finally:
            await trans.rollback()


# --- AC-3: names -------------------------------------------------------------------------------------------------

async def test_a_duplicate_name_in_any_case_is_refused_with_the_exact_text(db):
    user = _user()
    await pb.create(db, user, "ic", "Iron Condor Safe", _body())
    with pytest.raises(pb.PlaybookStoreError) as refused:
        await pb.create(db, user, "ic", "iron condor safe", _body())
    assert refused.value.code == pb.NAME_TAKEN
    shown = render(refused.value.code, **refused.value.slots)
    assert shown.what_happened == 'A playbook named "iron condor safe" already exists for Iron condor.'
    assert await _scalar(db, "SELECT count(*) FROM public.adjustment_playbooks WHERE user_ref = :u", u=user) == 1


async def test_the_same_name_for_another_type_or_another_user_is_allowed(db):
    user, other = _user(), _user()
    await pb.create(db, user, "ic", "Iron Condor Safe", _body())
    await pb.create(db, user, "credit", "Iron Condor Safe", _body("credit"))
    await pb.create(db, other, "ic", "Iron Condor Safe", _body())
    assert await _scalar(db, "SELECT count(*) FROM public.adjustment_playbooks WHERE lower(name) = 'iron condor safe' "
                             "AND user_ref IN (:a, :b)", a=user, b=other) == 3  # noqa: PLR2004


async def test_the_name_index_refuses_a_case_duplicate_written_past_the_store(db):
    user = _user()
    await pb.create(db, user, "ic", "Iron Condor Safe", _body())
    await _refused(db, "INSERT INTO public.adjustment_playbooks (user_ref, strategy_type, name, body) "
                       "VALUES (:u, 'ic', 'IRON CONDOR SAFE', CAST(:b AS JSONB))", "adjustment_playbooks_name",
                   u=user, b=pb._dump(_body()))


async def test_create_duplicate_rename_and_delete_own_playbooks(db):
    user = _user()
    system = await pb.active_for(db, user, "ic")
    copy_of_system = await pb.duplicate(db, user, system.id, "My IC")
    assert (copy_of_system.is_system, copy_of_system.user_ref, copy_of_system.body) == (False, user, system.body)
    renamed = await pb.rename(db, user, copy_of_system.id, "  My IC 2  ")
    assert renamed.name == "My IC 2"
    other = await pb.create(db, user, "ic", "Other", _body())
    with pytest.raises(pb.PlaybookStoreError) as taken:
        await pb.rename(db, user, other.id, "my ic 2")
    assert taken.value.code == pb.NAME_TAKEN
    answer = await pb.delete(db, user, renamed.id)
    assert (answer.deleted, answer.active_now_system, answer.message) == (renamed.id, False, None)
    assert [p.name for p in await pb.list_for_type(db, user, "ic")] == [system.name, "Other"]


# --- AC-4: one active --------------------------------------------------------------------------------------------

async def test_make_active_twice_keeps_one_row_and_the_last_choice(db):
    user = _user()
    first = await pb.create(db, user, "ic", "First", _body())
    second = await pb.create(db, user, "ic", "Second", _body())
    await pb.make_active(db, user, first.id)
    await pb.make_active(db, user, second.id)
    assert await _scalar(db, "SELECT count(*) FROM public.adjustment_playbook_active WHERE user_ref = :u", u=user) == 1
    assert (await pb.active_for(db, user, "ic")).id == second.id


async def test_a_second_active_row_for_one_user_and_type_is_refused_by_the_key(db):
    user = _user()
    own = await pb.create(db, user, "ic", "Mine", _body())
    await pb.make_active(db, user, own.id)
    system = (await pb.list_for_type(db, user, "ic"))[0]
    await _refused(db, "INSERT INTO public.adjustment_playbook_active (user_ref, strategy_type, playbook_id) "
                       "VALUES (:u, 'ic', :p)", "adjustment_playbook_active_pkey", u=user, p=system.id)


async def test_deleting_the_active_playbook_makes_the_system_one_active_and_says_so(db):
    user = _user()
    own = await pb.create(db, user, "ic", "Mine", _body())
    await pb.make_active(db, user, own.id)
    answer = await pb.delete(db, user, own.id)
    assert answer.active_now_system is True
    assert answer.message == "Iron condor: the system playbook is active again"
    active = await pb.active_for(db, user, "ic")
    assert active.is_system and active.strategy_type == "ic"


async def test_the_active_choice_cannot_point_at_another_users_or_another_types_playbook(db):
    user, other = _user(), _user()
    theirs = await pb.create(db, other, "ic", "Theirs", _body())
    credit = await pb.create(db, user, "credit", "Credit", _body("credit"))
    await _refused(db, "INSERT INTO public.adjustment_playbook_active (user_ref, strategy_type, playbook_id) "
                       "VALUES (:u, 'ic', :p)", "OF031", u=user, p=theirs.id)
    await _refused(db, "INSERT INTO public.adjustment_playbook_active (user_ref, strategy_type, playbook_id) "
                       "VALUES (:u, 'ic', :p)", "foreign key", u=user, p=credit.id)


# --- AC-5: precedence, the plan is a copy ------------------------------------------------------------------------

async def test_a_plan_keeps_its_body_byte_identical_when_its_playbook_is_edited_then_deleted(db):
    user = _user()
    _, stored = await _with_draft(db, user)
    own = await pb.create(db, user, "ic", "Mine", _body("ic", "0.5"))
    plan = await pb.accept_plan(db, user, stored.id, own.id)
    assert plan.body == own.body and plan.playbook_id == own.id
    raw = "SELECT body::text FROM public.strategy_adjustment_plans WHERE strategy_id = :s"
    before = await _scalar(db, raw, s=stored.id)
    await pb.save_in_place(db, user, own.id, _body("ic", "0.2"), own.version)
    assert await _scalar(db, raw, s=stored.id) == before
    await pb.delete(db, user, own.id)
    assert await _scalar(db, raw, s=stored.id) == before
    after = await pb.plan_for(db, user, stored.id)
    assert after is not None and after.playbook_id is None and after.body == plan.body


async def test_accepting_again_replaces_the_strategys_own_plan_and_another_user_sees_none(db):
    user = _user()
    _, stored = await _with_draft(db, user)
    system = await pb.active_for(db, user, "ic")
    await pb.accept_plan(db, user, stored.id, system.id)
    custom = await pb.accept_plan(db, user, stored.id, system.id, _body("ic", "0.4"))
    assert custom.body["triggers"]["T-01"]["weekly"] == ["0.4", ""]
    assert await pb.plan_for(db, _user(), stored.id) is None
    with pytest.raises(store.StrategyStoreError) as missing:
        await pb.accept_plan(db, _user(), stored.id, system.id)
    assert missing.value.code == store.NOT_FOUND


async def test_a_plan_is_never_deleted_and_keeps_its_type(db):
    user = _user()
    _, stored = await _with_draft(db, user)
    await pb.accept_plan(db, user, stored.id, (await pb.active_for(db, user, "ic")).id)
    await _refused(db, "DELETE FROM public.strategy_adjustment_plans WHERE strategy_id = :s", "permission denied",
                   s=stored.id)


# --- AC-6: system playbooks are read-only ------------------------------------------------------------------------

async def test_saving_a_system_playbook_in_place_is_refused_by_the_store(db):
    user = _user()
    system = await pb.active_for(db, user, "ic")
    with pytest.raises(pb.PlaybookStoreError) as refused:
        await pb.save_in_place(db, user, system.id, _body(), system.version)
    assert refused.value.code == pb.SYSTEM_SAVE_IN_PLACE
    assert render(refused.value.code).what_happened == "A system playbook can only be saved as a new playbook."
    with pytest.raises(pb.PlaybookStoreError):
        await pb.delete(db, user, system.id)


async def test_the_application_role_cannot_update_or_delete_a_system_row_in_raw_sql(db):
    await _refused(db, "UPDATE public.adjustment_playbooks SET name = 'Hacked' "
                       "WHERE is_system AND strategy_type = 'ic'", "OF031")
    await _refused(db, "UPDATE public.adjustment_playbooks SET body = body WHERE is_system", "OF031")
    await _refused(db, "DELETE FROM public.adjustment_playbooks WHERE is_system AND strategy_type = 'ic'", "OF031")


async def test_the_application_role_cannot_insert_a_system_row_and_the_owner_cannot_add_a_second(db, admin_engine):
    await _refused(db, "INSERT INTO public.adjustment_playbooks (user_ref, strategy_type, name, is_system, body) "
                       "VALUES (NULL, 'ic', 'Fake', true, CAST(:b AS JSONB))", "permission denied",
                   b=pb._dump(_body()))
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await _refused(conn, "INSERT INTO public.adjustment_playbooks (user_ref, strategy_type, name, is_system, "
                                 "body) VALUES (NULL, 'ic', 'Second system', true, CAST(:b AS JSONB))",
                           "adjustment_playbooks_one_system", b=pb._dump(_body()))
        finally:
            await trans.rollback()


async def test_an_own_playbook_saves_in_place_at_its_version_and_a_stale_version_is_refused(db):
    user = _user()
    own = await pb.create(db, user, "ic", "Mine", _body())
    saved = await pb.save_in_place(db, user, own.id, _body("ic", "0.3"), own.version)
    assert saved.version == own.version + 1 and saved.body["triggers"]["T-01"]["weekly"][0] == "0.3"
    with pytest.raises(pb.PlaybookStoreError) as stale:
        await pb.save_in_place(db, user, own.id, _body("ic", "0.1"), own.version)
    assert stale.value.code == pb.VERSION_CONFLICT
    assert (await pb.get(db, user, own.id)).body["triggers"]["T-01"]["weekly"][0] == "0.3"


# --- every answer state: another user's id, a bad body ------------------------------------------------------------

async def test_another_users_playbook_answers_not_found_everywhere(db):
    other = _user()
    theirs = await pb.create(db, other, "ic", "Theirs", _body())
    user = _user()
    for call in (pb.get(db, user, theirs.id), pb.rename(db, user, theirs.id, "x"), pb.delete(db, user, theirs.id),
                 pb.make_active(db, user, theirs.id), pb.save_in_place(db, user, theirs.id, _body(), 1),
                 pb.duplicate(db, user, theirs.id, "copy"), pb.get(db, user, 10**12)):
        with pytest.raises(pb.PlaybookStoreError) as missing:
            await call
        assert missing.value.code == pb.NOT_FOUND
    assert (await pb.get(db, other, theirs.id)).name == "Theirs"


@pytest.mark.parametrize(("mutate", "field"), [
    (lambda b: b.update(schema=2), "schema"),
    (lambda b: b.update(strategy_type="credit"), "strategy_type"),
    (lambda b: b["triggers"]["T-01"].update(weekly=["0.5"]), "triggers.T-01.weekly"),
    (lambda b: b["triggers"]["T-01"].update(weekly=[0.5, ""]), "triggers.T-01.weekly.0"),
    (lambda b: b["triggers"]["T-01"].update(weekly=["half", ""]), "triggers.T-01.weekly.0"),
    (lambda b: b["rules"].append({"id": "R-2", "all_of": ["T-99"]}), "rules.1"),
    (lambda b: b.pop("stages"), "stages"),
])
async def test_an_invalid_body_is_refused_naming_the_field_and_nothing_is_written(db, mutate, field):
    user = _user()
    body = _body()
    mutate(body)
    with pytest.raises(pb.PlaybookStoreError) as refused:
        await pb.create(db, user, "ic", "Bad", body)
    assert (refused.value.code, refused.value.slots["field"]) == (pb.BODY_INVALID, field)
    shown = render(refused.value.code, **refused.value.slots).what_happened
    assert shown == f"The playbook value {field} is not valid."
    assert await _scalar(db, "SELECT count(*) FROM public.adjustment_playbooks WHERE user_ref = :u", u=user) == 0


# --- F-71 rule memory and REQ-112 suggestion records --------------------------------------------------------------

async def test_rule_state_records_held_at_entry_once_and_seen_clear_only_turns_on(db):
    user = _user()
    _, stored = await _with_draft(db, user)
    await pb.put_rule_state(db, user, stored.id, "T-01", held_at_entry=True, seen_clear=False)
    await pb.put_rule_state(db, user, stored.id, "T-01", held_at_entry=False, seen_clear=True)
    await pb.put_rule_state(db, user, stored.id, "T-01", held_at_entry=False, seen_clear=False)
    assert await pb.rule_state(db, user, stored.id) == {"T-01": (True, True)}
    await _refused(db, "UPDATE public.adjustment_rule_state SET seen_clear = false WHERE strategy_id = :s", "OF031",
                   s=stored.id)


async def test_one_open_suggestion_per_rule_and_one_final_outcome(db):
    user = _user()
    _, stored = await _with_draft(db, user)
    first = await pb.open_suggestion(db, user, stored.id, "T-01", trigger_id="T-01", stage="Early",
                                     value=Decimal("0.42"), threshold=Decimal("0.5"))
    again = await pb.open_suggestion(db, user, stored.id, "T-01", trigger_id="T-01", stage="Early",
                                     value=Decimal("0.40"), threshold=Decimal("0.5"))
    assert again.id == first.id and first.outcome == "open" and first.value == Decimal("0.42")
    dismissed = await pb.dismiss(db, user, first.id, "Already hedged")
    assert (dismissed.outcome, dismissed.dismiss_reason) == ("dismissed", "Already hedged")
    assert [e["outcome"] for e in dismissed.timeline] == ["open", "dismissed"]
    with pytest.raises(store.StrategyStoreError):
        await pb.act_on(db, user, first.id)
    await _refused(db, "UPDATE public.adjustment_suggestions SET outcome = 'lapsed' WHERE id = :id", "OF031",
                   id=first.id)
    with pytest.raises(store.StrategyStoreError):
        await pb.dismiss(db, _user(), (await pb.open_suggestion(db, user, stored.id, "T-02", trigger_id=None,
                                                                 stage=None, value=None, threshold=None)).id)


async def test_a_suggestion_timeline_is_append_only(db):
    user = _user()
    _, stored = await _with_draft(db, user)
    opened = await pb.open_suggestion(db, user, stored.id, "platform", trigger_id=None, stage=None, value=None,
                                      threshold=None)
    await _refused(db, """UPDATE public.adjustment_suggestions SET timeline = '[{"outcome": "dismissed"}]'::jsonb
                          WHERE id = :id""", "OF031", id=opened.id)
    await _refused(db, "UPDATE public.adjustment_suggestions SET timeline = '[]'::jsonb WHERE id = :id", "OF031",
                   id=opened.id)
    await db.execute(text("""UPDATE public.adjustment_suggestions SET timeline = timeline || '[{"note": 1}]'::jsonb
                             WHERE id = :id"""), {"id": opened.id})
    await _refused(db, "DELETE FROM public.adjustment_suggestions WHERE id = :id", "permission denied", id=opened.id)
    assert len((await pb.suggestions(db, user, stored.id))[0].timeline) == 2  # noqa: PLR2004
