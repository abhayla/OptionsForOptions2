"""GC-ADJ2 step 2: the playbook routes on a fresh migrated database (REQ-158 AC-3, AC-4, AC-6, AC-7, REQ-159 AC-1).
One test per route and per refusal, each with the exact catalogue text. The user is the session's: ``current_user_ref``
is overridden to a holder so a second user can be driven; no body carries a user. Playbooks a test creates stay in the
fresh database, so every test uses its own names.
"""
from __future__ import annotations

import copy
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from ofo.adjustment.playbook_types import SHOWN_NAMES, TYPE_KEYS
from ofo_app import playbook_store
from ofo_app.db import get_db
from ofo_app.routes import playbooks as playbook_routes
from ofo_app.routes.broker import V1_OWNER_REF, current_user_ref
from sqlalchemy.ext.asyncio import AsyncSession

OK, CREATED, NOT_FOUND, CONFLICT, UNPROCESSABLE, SERVER_ERROR = 200, 201, 404, 409, 422, 500
NOT_FOUND_TEXT = "This playbook was not found."
SYSTEM_TEXT = "A system playbook can only be saved as a new playbook."
CHANGED_TEXT = "This playbook was changed since you opened it."
OTHER = "other-user"


class Api:
    def __init__(self, http: AsyncClient, who: dict[str, str]) -> None:
        self.http, self.who = http, who

    async def call(self, method: str, path: str, user: str = V1_OWNER_REF, **kw: Any) -> Any:
        self.who["user"] = user
        return await self.http.request(method, path, **kw)

    async def system(self, key: str) -> dict:
        rows = (await self.call("GET", f"/api/playbooks?type={key}")).json()["playbooks"]
        return rows[0]

    async def body_of(self, playbook_id: int) -> dict:
        return (await self.call("GET", f"/api/playbooks/{playbook_id}")).json()["body"]

    async def make(self, name: str, key: str = "ic", user: str = V1_OWNER_REF) -> dict:
        body = await self.body_of((await self.system(key))["id"])
        made = await self.call("POST", "/api/playbooks", user, json={"type": key, "name": name, "body": body})
        assert made.status_code == CREATED, made.text
        return made.json()


@pytest.fixture
async def api(db_session: AsyncSession) -> AsyncIterator[Api]:
    from ofo_app.main import create_app  # noqa: PLC0415

    app = create_app()
    who = {"user": V1_OWNER_REF}

    async def override_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[current_user_ref] = lambda: who["user"]
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield Api(http, who)
    app.dependency_overrides.clear()


def unquoted(shown: str) -> str:
    """A name is shown as the user's own words in double quotes (REQ-134 AC-4 convention): strip them to compare."""
    assert shown[0] == shown[-1] == '"'
    return shown[1:-1]


def _text(response: Any) -> str:
    return response.json()["what_happened"]


def _stages(body: dict, weekly: list[tuple[str, int, int | None]]) -> dict:
    body = copy.deepcopy(body)
    body["stages"]["weekly"] = [{"name": n, "from": f, "to": t} for n, f, t in weekly]
    return body


# --- reads -------------------------------------------------------------------------------------------------------


async def test_types_lists_the_twelve_with_the_active_and_system_flag(api):
    response = await api.call("GET", "/api/playbooks/types")
    assert response.status_code == OK
    rows = response.json()["types"]
    assert [r["key"] for r in rows] == list(TYPE_KEYS)
    assert [r["name"] for r in rows] == [SHOWN_NAMES[k] for k in TYPE_KEYS]
    assert all(r["has_system"] for r in rows)
    ic = next(r for r in rows if r["key"] == "ic")
    assert ic["active_id"] == (await api.system("ic"))["id"]


async def test_list_puts_the_system_playbook_first_then_own_by_name(api):
    await api.make("List zeta")
    await api.make("List alpha")
    rows = (await api.call("GET", "/api/playbooks?type=ic")).json()["playbooks"]
    assert rows[0]["is_system"] is True and rows[0]["status"] == "approved" and rows[0]["draft"] is False
    assert rows[0]["active"] is True
    names = [unquoted(r["name"]) for r in rows[1:]]
    assert names == sorted(names, key=str.lower)
    assert {"List alpha", "List zeta"} <= set(names)
    assert set(rows[0]) == {"id", "name", "type", "type_name", "is_system", "status", "draft", "active", "version",
                            "updated_at"}


async def test_a_draft_system_playbook_is_labelled_draft_and_a_copy_of_it_is_not(api):
    system = await api.system("strangle")
    assert system["is_system"] is True and system["status"] == "draft" and system["draft"] is True
    copy_ = await api.call("POST", f"/api/playbooks/{system['id']}/duplicate", json={"name": "Strangle mine"})
    assert copy_.status_code == CREATED
    mine = copy_.json()
    assert mine["is_system"] is False and mine["draft"] is False and mine["status"] is None
    assert "DRAFT IS A SYSTEM-PLAYBOOK LABEL ONLY" in playbook_routes.__doc__
    listed = (await api.call("GET", "/api/playbooks?type=strangle")).json()["playbooks"]
    assert [r["draft"] for r in listed if not r["is_system"]] == [False] * (len(listed) - 1)


async def test_read_one_returns_the_body(api):
    system = await api.system("ic")
    response = await api.call("GET", f"/api/playbooks/{system['id']}")
    assert response.status_code == OK
    body = response.json()["body"]
    assert body["strategy_type"] == "ic" and body["schema"] == 1 and set(body["stages"]) == {"weekly", "monthly"}


# --- create / name refusal (the core) ---------------------------------------------------------------------------------


async def test_same_name_in_another_case_and_with_spaces_is_refused_with_the_exact_text(api):
    first = await api.make("IC Safe")
    assert first["name"] == '"IC Safe"' and first["draft"] is False and first["status"] is None
    body = first["body"]
    for typed in ("ic safe", "  IC SAFE  "):
        response = await api.call("POST", "/api/playbooks", json={"type": "ic", "name": typed, "body": body})
        assert response.status_code == CONFLICT
        assert _text(response) == f"A playbook named {typed.strip()} already exists for Iron condor."
    other_type = await api.call("POST", "/api/playbooks", json={
        "type": "strangle", "name": "IC Safe", "body": await api.body_of((await api.system("strangle"))["id"])})
    assert other_type.status_code == CREATED  # the same name for another type is fine


async def test_duplicate_and_rename_refuse_a_taken_name(api):
    one, two = await api.make("Dup one"), await api.make("Dup two")
    dup = await api.call("POST", f"/api/playbooks/{one['id']}/duplicate", json={"name": "dup TWO"})
    assert dup.status_code == CONFLICT and _text(dup) == "A playbook named dup TWO already exists for Iron condor."
    ren = await api.call("PATCH", f"/api/playbooks/{two['id']}", json={"name": "DUP ONE"})
    assert ren.status_code == CONFLICT and _text(ren) == "A playbook named DUP ONE already exists for Iron condor."
    fresh = await api.call("PATCH", f"/api/playbooks/{two['id']}", json={"name": "Dup renamed"})
    assert fresh.status_code == OK and fresh.json()["name"] == '"Dup renamed"'
    same = await api.call("PATCH", f"/api/playbooks/{two['id']}", json={"name": "dup RENAMED"})
    assert same.status_code == OK  # its own name in another case is not a clash


# --- save in place -------------------------------------------------------------------------------------------------


async def test_save_in_place_bumps_the_version_and_a_stale_version_is_refused(api):
    mine = await api.make("Save mine")
    body = _stages(mine["body"], [("Early", 6, None), ("Middle", 2, 5), ("Last day", 0, 1)])
    saved = await api.call("PUT", f"/api/playbooks/{mine['id']}", json={"body": body, "version": mine["version"]})
    assert saved.status_code == OK
    assert saved.json()["version"] == mine["version"] + 1
    assert saved.json()["body"]["stages"]["weekly"][0] == {"name": "Early", "from": 6, "to": None}
    stale = await api.call("PUT", f"/api/playbooks/{mine['id']}", json={"body": body, "version": mine["version"]})
    assert stale.status_code == CONFLICT and _text(stale) == CHANGED_TEXT


async def test_save_in_place_of_a_system_playbook_is_refused_and_the_row_is_unchanged(api):
    system = await api.system("ic")
    body = await api.body_of(system["id"])
    payload = {"body": body, "version": system["version"]}
    response = await api.call("PUT", f"/api/playbooks/{system['id']}", json=payload)
    assert response.status_code == CONFLICT and _text(response) == SYSTEM_TEXT
    after = await api.system("ic")
    assert (after["version"], after["updated_at"]) == (system["version"], system["updated_at"])
    assert await api.body_of(system["id"]) == body
    renamed = await api.call("PATCH", f"/api/playbooks/{system['id']}", json={"name": "Mine now"})
    assert renamed.status_code == CONFLICT and _text(renamed) == SYSTEM_TEXT
    deleted = await api.call("DELETE", f"/api/playbooks/{system['id']}")
    assert deleted.status_code == CONFLICT and _text(deleted) == SYSTEM_TEXT


# --- activate and delete -------------------------------------------------------------------------------------------


async def test_activate_then_delete_says_the_system_playbook_is_active_again(api):
    mine = await api.make("Active mine")
    activated = await api.call("POST", f"/api/playbooks/{mine['id']}/activate")
    assert activated.status_code == OK and activated.json()["active"] is True
    listed = (await api.call("GET", "/api/playbooks?type=ic")).json()["playbooks"]
    assert [r["id"] for r in listed if r["active"]] == [mine["id"]]
    deleted = await api.call("DELETE", f"/api/playbooks/{mine['id']}")
    assert deleted.status_code == OK
    assert deleted.json() == {"deleted": True, "active_now_system": True,
                              "message": "Iron condor: the system playbook is active again"}
    after = (await api.call("GET", "/api/playbooks?type=ic")).json()["playbooks"]
    assert [(r["is_system"], r["active"]) for r in after if r["active"]] == [(True, True)]
    assert mine["id"] not in [r["id"] for r in after]
    gone = await api.call("GET", f"/api/playbooks/{mine['id']}")
    assert gone.status_code == NOT_FOUND


async def test_delete_of_a_playbook_that_is_not_active_says_nothing_about_the_system_one(api):
    mine = await api.make("Passive mine")
    deleted = await api.call("DELETE", f"/api/playbooks/{mine['id']}")
    assert deleted.status_code == OK
    assert deleted.json() == {"deleted": True, "active_now_system": False, "message": None}


# --- another user's playbook and absent ids ---------------------------------------------------------------------------


async def test_another_users_playbook_is_not_found_on_every_route_and_nothing_is_written(api):
    mine = await api.make("Private mine")
    path = f"/api/playbooks/{mine['id']}"
    body = mine["body"]
    calls = [("GET", path, None), ("PUT", path, {"body": body, "version": mine["version"]}),
             ("PATCH", path, {"name": "Stolen"}), ("DELETE", path, None), ("POST", f"{path}/activate", None),
             ("POST", f"{path}/duplicate", {"name": "Stolen copy"})]
    for method, url, payload in calls:
        response = await api.call(method, url, OTHER, **({} if payload is None else {"json": payload}))
        assert response.status_code == NOT_FOUND, (method, url)
        assert _text(response) == NOT_FOUND_TEXT
    still = await api.call("GET", path)
    assert still.json()["name"] == '"Private mine"' and still.json()["version"] == mine["version"]
    assert [r["name"] for r in (await api.call("GET", "/api/playbooks?type=ic", OTHER)).json()["playbooks"]
            if not r["is_system"]] == []
    active = await api.call("GET", "/api/playbooks/types", OTHER)
    assert next(r for r in active.json()["types"] if r["key"] == "ic")["active_id"] != mine["id"]


@pytest.mark.parametrize("bad_id", [0, 987654321, 10**30])
async def test_an_absent_id_is_not_found(api, bad_id):
    for method in ("GET", "DELETE"):
        response = await api.call(method, f"/api/playbooks/{bad_id}")
        assert response.status_code == NOT_FOUND and _text(response) == NOT_FOUND_TEXT


# --- stage gap / overlap ---------------------------------------------------------------------------------------------


async def test_create_and_save_refuse_an_overlap_and_a_gap_naming_the_days(api):
    mine = await api.make("Stages mine")
    overlap = _stages(mine["body"], [("Early", 5, None), ("Near", 2, 4), ("Last", 0, 4)])
    gap = _stages(mine["body"], [("Early", 7, None), ("Near", 2, 4), ("Last", 0, 1)])
    for label, body, text in (("overlap", overlap, "Days 2 to 4 are in both Last and Near (weekly expiries)."),
                              ("gap", gap, "Days 5 to 6 are in no stage (weekly expiries).")):
        created = await api.call("POST", "/api/playbooks", json={"type": "ic", "name": f"Stage {label}", "body": body})
        assert created.status_code == UNPROCESSABLE and _text(created) == text
        saved = await api.call("PUT", f"/api/playbooks/{mine['id']}", json={"body": body, "version": mine["version"]})
        assert saved.status_code == UNPROCESSABLE and _text(saved) == text
    after = await api.call("GET", f"/api/playbooks/{mine['id']}")
    assert after.json()["version"] == mine["version"] and after.json()["body"] == mine["body"]
    listed = (await api.call("GET", "/api/playbooks?type=ic")).json()["playbooks"]
    assert not [r for r in listed if unquoted(r["name"]).startswith("Stage ")]


# --- answer states of the body and the request ------------------------------------------------------------------------


async def test_a_body_that_is_empty_not_an_object_or_has_an_unknown_field_is_refused(api):
    good = await api.body_of((await api.system("ic"))["id"])
    surprise = {**good, "surprise": 1}
    ambiguous = {**good, "stages": {**good["stages"], "weekly_again": good["stages"]["weekly"]}}
    wrong_type = {**good, "strategy_type": "strangle"}
    cases = [({}, "The playbook value schema is not valid."),
             (surprise, "The playbook value body is not valid."),
             (ambiguous, "The playbook value stages is not valid."),
             (wrong_type, "The playbook value strategy_type is not valid.")]
    for body, text in cases:
        response = await api.call("POST", "/api/playbooks", json={"type": "ic", "name": "Bad body", "body": body})
        assert response.status_code == UNPROCESSABLE and _text(response) == text, body.keys()
    not_object = await api.call("POST", "/api/playbooks", json={"type": "ic", "name": "Bad body", "body": [1]})
    assert not_object.status_code == UNPROCESSABLE
    assert not [r for r in (await api.call("GET", "/api/playbooks?type=ic")).json()["playbooks"]
                if unquoted(r["name"]) == "Bad body"]


async def test_an_unknown_type_an_unknown_request_field_and_a_bad_name_are_refused(api):
    good = await api.body_of((await api.system("ic"))["id"])
    unknown_type = await api.call("POST", "/api/playbooks", json={"type": "zzz", "name": "X", "body": good})
    assert unknown_type.status_code == UNPROCESSABLE
    assert _text(unknown_type) == "The playbook value strategy_type is not valid."
    listed = await api.call("GET", "/api/playbooks?type=zzz")
    assert listed.status_code == UNPROCESSABLE
    with_user = await api.call("POST", "/api/playbooks", json={"type": "ic", "name": "X", "body": good,
                                                                  "user_ref": OTHER})
    assert with_user.status_code == UNPROCESSABLE  # a user in the body is refused, never read
    for name in ("", "   ", "n" * 81, 'has "quote"'):
        response = await api.call("POST", "/api/playbooks", json={"type": "ic", "name": name, "body": good})
        assert response.status_code == UNPROCESSABLE, name
        assert _text(response) == "The playbook value name is not valid.", name
    ok = await api.call("POST", "/api/playbooks", json={"type": "ic", "name": "n" * 80, "body": good})
    assert ok.status_code == CREATED


async def test_a_store_failure_is_never_a_200_and_nothing_is_written(api, monkeypatch):
    good = await api.body_of((await api.system("ic"))["id"])

    async def broken(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("database went away")

    monkeypatch.setattr(playbook_store, "create", broken)
    response = await api.call("POST", "/api/playbooks", json={"type": "ic", "name": "Never saved", "body": good})
    assert response.status_code == SERVER_ERROR
    assert "what_happened" in response.json() and "database went away" not in response.text
    monkeypatch.undo()
    assert not [r for r in (await api.call("GET", "/api/playbooks?type=ic")).json()["playbooks"]
                if unquoted(r["name"]) == "Never saved"]
