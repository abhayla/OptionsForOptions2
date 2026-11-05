"""REQ-169 AC-1..AC-4: the admin's system playbook versions (migration 0034, ``ofo_app.system_playbook_store``,
``routes.system_playbooks``) and the checker reading the CURRENT version.

Spec basis: ADR-222 (10) "the admin changes a SYSTEM playbook in the same step-by-step playbook editor and saves it as a
new version with history and audit; users still only copy system playbooks"; (9) applies at the next check, saved
plans kept; REQ-169 AC-2 "the old one is kept, never overwritten ... 'Restore this version' makes an earlier version
current as a new version".

Real input: the checked-in iron condor system playbook (PB-04, ADR-216): T-06 "Loss reaches this % of max loss" is 50
in the weekly Early stage. Every test runs inside one outer transaction that is rolled back (the version table is
insert-only: a committed row would stay for ever); a route's commit is a savepoint release.
"""
from __future__ import annotations

import copy
from decimal import Decimal
from http import HTTPStatus

import pytest
from fastapi import APIRouter, HTTPException
from httpx import ASGITransport, AsyncClient
from ofo.adjustment import playbook_eval as pe
from ofo.errors.explanations import render_explanation
from ofo_app import adjustment_check as check
from ofo_app import playbook_store as pbs
from ofo_app import system_playbook_store as sys_store
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from test_settings_route import _unguarded_writes
from test_strategy_store import _user, _with_draft

D = Decimal
ADMIN = "admin-test"
VERSIONS = text("SELECT count(*) FROM public.system_playbook_versions")
AUDIT = text("SELECT count(*) FROM public.audit_events WHERE event_type = 'admin_change_recorded'")
LAST_AUDIT = text("SELECT payload->>'action', payload->>'reason', actor FROM public.audit_events "
                  "WHERE event_type = 'admin_change_recorded' ORDER BY seq DESC LIMIT 1")
#: a weekly Early check of an iron condor at 47% of its max loss: flags at a 45 limit, not at the seeded 50
STATE_47 = pe.StrategyState(stops=None, expiry_kind="weekly", days_left=6, hhmm="10:00", spot=D("22500"), pnl=D("-470"),
                            max_loss=D("1000"), prices_fresh=True)
CLEARED = {"T-06": {"held_at_entry": False, "seen_clear": True}}
#: the iron condor's CURRENT version on a fresh database: the seed (1) plus migration 0040's ADR-247 version (2)
ICV = 2


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


def _t06(body: dict) -> str:
    return body["triggers"]["T-06"]["weekly"][0]


def _edited(body: dict, value: str = "45") -> dict:
    out = copy.deepcopy(body)
    out["triggers"]["T-06"]["weekly"][0] = value
    return out


def _t06_flag(body: dict) -> list:
    ev = pe.evaluate(body, STATE_47, CLEARED, None, gap_until="09:30")
    return [(r.threshold, r.value) for r in ev.results if isinstance(r, pe.Flag) and r.rule_id == "T-06"]


async def _count(db, query) -> int:
    return (await db.execute(query)).scalar_one()


# ---- the core proof (AC-2, AC-4) -----------------------------------------------------------------------------------

async def test_core_proof_new_version_reaches_the_next_check_copies_and_plans_unchanged_restore_appends(db):
    user = _user()
    system = await pbs.active_for(db, user, "ic")
    assert system.is_system and system.version == ICV and _t06(system.body) == "50"
    copy_before = await pbs.duplicate(db, user, system.id, "My IC")  # a user's copy made before the change
    _, planned = await _with_draft(db, user)
    await pbs.accept_plan(db, user, planned.id, system.id)  # a saved plan made before the change
    tracked_user = _user()
    _, tracked = await _with_draft(db, tracked_user)  # a strategy tracked on the system playbook itself (no plan)
    assert _t06((await check.resolve(db, tracked_user, tracked.id, "ic")).body) == "50"
    assert _t06_flag((await check.resolve(db, tracked_user, tracked.id, "ic")).body) == []  # 47 < 50: no flag
    audits = await _count(db, AUDIT)

    saved = await sys_store.save(db, ADMIN, "ic", _edited(system.body), "  tighter stop  after review ", ICV)

    assert (saved.version, saved.status, saved.reason, saved.saved_by) == (
        ICV + 1, "approved", "tighter stop after review", ADMIN)
    history = await sys_store.history(db, "ic")
    assert [(v.version, _t06(v.body)) for v in history][:2] == [(ICV + 1, "45"), (ICV, "50")]  # kept, not overwritten
    assert await _count(db, AUDIT) == audits + 1
    action, reason, actor = (await db.execute(LAST_AUDIT)).one()
    assert (action, actor) == (sys_store.AUDIT_SAVED, ADMIN) and "tighter stop after review" in reason
    # AC-4: the system-tracked strategy checks against 45 at its next check; the copy and the plan keep 50
    resolved = await check.resolve(db, tracked_user, tracked.id, "ic")
    assert (resolved.source, _t06(resolved.body)) == ("system", "45")
    assert _t06_flag(resolved.body) == [(D("45"), D("47"))]
    assert _t06((await pbs.get(db, user, copy_before.id)).body) == "50"
    plan = await check.resolve(db, user, planned.id, "ic")
    assert (plan.source, _t06(plan.body)) == ("plan", "50")
    assert (await pbs.get(db, user, system.id)).version == saved.version  # reads as its current version

    restored = await sys_store.restore(db, ADMIN, "ic", ICV, "back to the approved numbers", ICV + 1)
    assert (restored.version, restored.restored_from, _t06(restored.body)) == (ICV + 2, ICV, "50")
    assert [v.version for v in await sys_store.history(db, "ic")][:3] == [ICV + 2, ICV + 1, ICV]  # appends only
    assert _t06((await check.resolve(db, tracked_user, tracked.id, "ic")).body) == "50"
    assert (await db.execute(LAST_AUDIT)).one()[0] == sys_store.AUDIT_RESTORED


async def test_seed_is_version_one_of_all_twelve_with_the_reason_seed(db):
    rows = (await db.execute(text(
        "SELECT v.strategy_type, v.version, v.status, v.reason, v.body = p.body, v.status = p.status "
        "FROM public.system_playbook_versions v JOIN public.adjustment_playbooks p "
        "ON p.strategy_type = v.strategy_type AND p.is_system WHERE v.version = 1 ORDER BY 1"))).all()
    assert len(rows) == 12  # noqa: PLR2004 - the 12 strategy types
    assert all(r[1] == 1 and r[3] == "seed" and r[4] and r[5] for r in rows)


async def test_approve_marks_a_draft_approved_as_a_new_version_shown_on_the_playbook(db):
    user = _user()
    assert (await pbs.active_for(db, user, "ifly")).status == "draft"
    approved = await sys_store.approve(db, ADMIN, "ifly", "owner read the numbers", 1)
    assert (approved.version, approved.status, approved.body["status"]) == (2, "approved", "approved")
    assert approved.body["triggers"] == (await sys_store.version(db, "ifly", 1)).body["triggers"]  # same numbers
    shown = await pbs.active_for(db, user, "ifly")
    assert (shown.status, shown.version) == ("approved", 2)
    with pytest.raises(pbs.PlaybookStoreError) as again:
        await sys_store.approve(db, ADMIN, "ifly", "again", 2)
    assert again.value.code == sys_store.ALREADY_APPROVED


@pytest.mark.parametrize("reason", ["", "   ", "x" * 501, None])
async def test_a_version_without_a_reason_is_refused_and_nothing_is_written(db, reason):
    body = (await sys_store.current(db, "ic")).body
    before = await _count(db, VERSIONS)
    with pytest.raises(pbs.PlaybookStoreError) as refused:
        await sys_store.save(db, ADMIN, "ic", _edited(body), reason, ICV)
    assert refused.value.code == sys_store.REASON_REQUIRED and await _count(db, VERSIONS) == before


async def test_a_save_on_a_stale_base_version_is_refused(db):
    body = (await sys_store.current(db, "ic")).body
    await sys_store.save(db, ADMIN, "ic", _edited(body), "first", ICV)
    with pytest.raises(pbs.PlaybookStoreError) as refused:
        await sys_store.save(db, ADMIN, "ic", _edited(body, "40"), "second admin", ICV)
    assert refused.value.code == sys_store.VERSION_STALE and (await sys_store.current(db, "ic")).version == ICV + 1


async def test_a_save_cannot_change_the_approval_state(db):
    body = (await sys_store.current(db, "ifly")).body
    with pytest.raises(pbs.PlaybookStoreError) as refused:
        await sys_store.save(db, ADMIN, "ifly", {**body, "status": "approved"}, "sneak approval", 1)
    assert (refused.value.code, refused.value.slots) == (pbs.BODY_INVALID, {"field": "status"})


# ---- append-only (database guard) ------------------------------------------------------------------------------------

@pytest.mark.parametrize("sql", [
    "UPDATE public.system_playbook_versions SET reason = 'edited' WHERE strategy_type = 'ic'",
    "DELETE FROM public.system_playbook_versions WHERE strategy_type = 'ic'",
    "TRUNCATE public.system_playbook_versions",
])
async def test_the_application_role_cannot_update_delete_or_truncate(db, sql):
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(text(sql))


@pytest.mark.parametrize("sql", [
    "UPDATE public.system_playbook_versions SET reason = 'edited'",
    "DELETE FROM public.system_playbook_versions",
    "TRUNCATE public.system_playbook_versions",
    "INSERT INTO public.system_playbook_versions (strategy_type, version, status, body, reason, saved_by) "
    "SELECT strategy_type, 7, status, body, 'gap', 'owner' FROM public.system_playbook_versions "
    "WHERE strategy_type = 'ic' AND version = 1",
    "INSERT INTO public.system_playbook_versions (strategy_type, version, status, body, reason, saved_by, "
    "restored_from) SELECT strategy_type, 3, status, body, 'bad restore', 'owner', 5 "
    "FROM public.system_playbook_versions WHERE strategy_type = 'ic' AND version = 1",
])
async def test_the_guard_refuses_even_the_owner(admin_engine, sql):
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            with pytest.raises(DBAPIError) as info:
                await conn.execute(text(sql))
            assert getattr(info.value.orig, "sqlstate", None) == "OF034"
        finally:
            await trans.rollback()


# ---- the routes (AC-1: admin only, the editor's validation, Test before Save) --------------------------------------

class Env:
    def __init__(self, app, client, conn):
        self.app, self.client, self.conn = app, client, conn


@pytest.fixture
async def env(app_engine):
    from ofo_app.db import get_db  # noqa: PLC0415
    from ofo_app.main import create_app  # noqa: PLC0415
    from ofo_app.routes.broker import current_user_ref  # noqa: PLC0415

    conn = await app_engine.connect()
    trans = await conn.begin()
    session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
    app = create_app()

    async def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[current_user_ref] = lambda: ADMIN
    try:
        async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False),
                               base_url="http://test") as client:
            yield Env(app, client, conn)
    finally:
        await session.close()
        await trans.rollback()
        await conn.close()


BASE = "/api/system-playbooks/ic"


async def _ic_body(env) -> dict:
    return (await sys_store.current(env.conn, "ic")).body


def _writes(body: dict) -> list[tuple[str, dict]]:
    return [(f"{BASE}/versions", {"body": _edited(body), "reason": "r", "base_version": ICV}),
            (f"{BASE}/versions/1/restore", {"reason": "r", "base_version": ICV}),
            ("/api/system-playbooks/ifly/approve", {"reason": "r", "base_version": 1})]


async def test_every_route_depends_on_the_one_admin_guard_and_a_new_unguarded_route_is_named():
    from ofo_app.routes import settings as settings_route  # noqa: PLC0415
    from ofo_app.routes import system_playbooks as route  # noqa: PLC0415

    assert _unguarded_writes(route.router) == []
    for r in route.router.routes:  # reads too: history is admin-only
        assert any(d.call is settings_route.require_admin for d in r.dependant.dependencies), r.path
    probe = APIRouter()
    probe.add_api_route("/x", lambda: None, methods=["POST"])
    assert _unguarded_writes(probe) == ["['POST'] /x"]  # fails closed: a new write route without the guard is named


async def test_a_non_admin_is_refused_on_every_route_and_nothing_is_written(env):
    from ofo_app.routes.settings import require_admin  # noqa: PLC0415

    def deny():
        raise HTTPException(status_code=403)  # the door takes a plain int status

    body = await _ic_body(env)
    env.app.dependency_overrides[require_admin] = deny
    before, audits = await _count(env.conn, VERSIONS), await _count(env.conn, AUDIT)
    for path, payload in _writes(body):
        assert (await env.client.post(path, json=payload)).status_code == HTTPStatus.FORBIDDEN, path
    assert (await env.client.get(f"{BASE}/versions")).status_code == HTTPStatus.FORBIDDEN
    assert (await _count(env.conn, VERSIONS), await _count(env.conn, AUDIT)) == (before, audits)


async def test_the_admin_saves_restores_and_approves_over_http(env):
    body = await _ic_body(env)
    saved = await env.client.post(f"{BASE}/versions", json={"body": _edited(body), "reason": "why",
                                                            "base_version": ICV})
    assert saved.status_code == HTTPStatus.CREATED, saved.text
    assert (saved.json()["version"], saved.json()["current"], saved.json()["saved_by"]) == (ICV + 1, True, ADMIN)
    history = (await env.client.get(f"{BASE}/versions")).json()["versions"]
    assert [(v["version"], v["current"]) for v in history][:2] == [(ICV + 1, True), (ICV, False)]
    restored = await env.client.post(f"{BASE}/versions/1/restore", json={"reason": "undo", "base_version": ICV + 1})
    assert (restored.status_code, restored.json()["version"], restored.json()["restored_from"]) == (201, ICV + 2, 1)
    approved = await env.client.post("/api/system-playbooks/ifly/approve", json={"reason": "ok", "base_version": 1})
    assert (approved.status_code, approved.json()["status"], approved.json()["draft"]) == (201, "approved", False)


async def test_this_apis_refusals_answer_their_catalogue_reason(env):
    body = await _ic_body(env)
    cases = [
        (f"{BASE}/versions", {"body": _edited(body), "reason": " ", "base_version": ICV}, 422,
         render_explanation("system_playbook_refused_reason")),
        (f"{BASE}/versions", {"body": _edited(body), "reason": "r", "base_version": 9}, 409,
         render_explanation("system_playbook_refused_stale", version=ICV)),
        (f"{BASE}/versions/9/restore", {"reason": "r", "base_version": ICV}, 404,
         render_explanation("system_playbook_refused_version", version=9)),
        (f"{BASE}/approve", {"reason": "r", "base_version": ICV}, 409,
         render_explanation("system_playbook_refused_approved")),  # PB-04 is approved (ADR-216)
    ]
    before = await _count(env.conn, VERSIONS)
    for path, payload, status, reason in cases:
        resp = await env.client.post(path, json=payload)
        assert (resp.status_code, resp.json()["reason"]) == (status, str(reason)), path
    assert await _count(env.conn, VERSIONS) == before


async def test_an_invalid_body_is_refused_with_the_same_answer_as_the_user_editor(env):
    """REQ-160: one validator. The same bad body to a user's save and to the system save: same status, same text."""
    body = await _ic_body(env)
    own = await env.client.post("/api/playbooks", json={"type": "ic", "name": "Mine", "body": body})
    assert own.status_code == HTTPStatus.CREATED, own.text
    gap = copy.deepcopy(body)
    gap["stages"]["weekly"][1]["from"] = 3  # Middle 3..4 leaves day 2 in no stage
    bad_value = _edited(body, "fifty")
    unknown_key = {**body, "colour": "red"}
    before = await _count(env.conn, VERSIONS)
    for bad in (gap, bad_value, unknown_key):
        user = await env.client.put(f"/api/playbooks/{own.json()['id']}", json={"body": bad, "version": 1})
        system = await env.client.post(f"{BASE}/versions", json={"body": bad, "reason": "r", "base_version": ICV})
        assert user.status_code == system.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, (user.text, system.text)
        assert user.json() == system.json()
    assert await _count(env.conn, VERSIONS) == before


async def test_test_before_save_answers_without_saving(env):
    body = await _ic_body(env)
    before, audits = await _count(env.conn, VERSIONS), await _count(env.conn, AUDIT)
    resp = await env.client.post("/api/playbooks/test", json={"type": "ic", "body": _edited(body)})
    assert resp.status_code == HTTPStatus.OK, resp.text
    assert resp.json()["type"] == "ic"
    assert (await _count(env.conn, VERSIONS), await _count(env.conn, AUDIT)) == (before, audits)
    assert _t06((await sys_store.current(env.conn, "ic")).body) == "50"
