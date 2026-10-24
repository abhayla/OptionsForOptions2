"""REQ-134 (W-157, part 29b): a saved strategy's name, Save As, rename and the enriched own-user list, through the API.

Spec basis (quoted): REQ-134 AC-1 "1 to 40 characters after trimming spaces; an empty name is refused with \"Give the
strategy a name\". Two strategies of one user may share a name; each keeps its own id."; AC-2 "Save As ... creates a new
strategy with the current legs and planned entries ... and leaves the original exactly as it was saved"; AC-3 "Renaming
changes only the name; it adds a history entry (\"Renamed from X to Y\") and never changes legs, prices, tracking state
or version"; AC-4 "name, underlying, the first leg's contract plus \"and N more\" ... whether it is being tracked";
AC-6 "Every list and search reads only the signed-in user's own strategies".

Sensibull: screens 115-120 (Save / Save As / Saved Strategies), 270-272. The name comes back as quoted user text
(ADR-003): `"NIFTY Oct condor"` with its outer quotes, which the browser strips to edit it.

Real PostgreSQL only (ADR-048); every test rolls back.
"""

from __future__ import annotations

import datetime
import json
from http import HTTPStatus

import pytest
from sqlalchemy import text

from ofo_app import strategy_store as store
from test_strategy_followups import _ConnMaker
from test_strategy_store import WING, _app, _body, _client, _history_rows, _user, _with_draft

DEFINITION_AND_REVISION = text(
    "SELECT definition::text, revision, updated_at, name FROM public.strategies WHERE id = :id")
EMPTY_NAME_CODE = "STRATEGY_VALIDATION_430"
INVALID_NAME_CODE = "STRATEGY_VALIDATION_431"
NOT_FOUND_CODE = "USER_INPUT_003"
CONFLICT_CODE = "STRATEGY_VALIDATION_409"
MISSING_ID = 987654321
SHARED_NAME_COUNT = 2
SECOND_REVISION = 2
LEG_COUNT = 4  # the four-leg condor fixture


def quoted(name: str) -> str:
    """The API's shape of a name: the user's words between quotes (ADR-003); the outer quotes are stripped to edit."""
    return f'"{name}"'


async def _snapshot(conn, strategy_id: int) -> tuple:
    return tuple((await conn.execute(DEFINITION_AND_REVISION, {"id": strategy_id})).one())


async def _post(ac, ids, name=None, **extra):
    body = _body(ids, **extra)
    if name is not None:
        body["name"] = name
    return await ac.post("/strategies", json=body)


# --- AC-1: the name at first save --------------------------------------------------------------------------------


async def test_ac1_a_strategy_saved_with_a_name_lists_and_loads_with_that_name(app_engine):
    """AC-1: "NIFTY Oct condor" saved appears in the list and on load with that name; trimmed; omitted = the default."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids, first = await _with_draft(conn, user := _user())
            async with _client(_app(_ConnMaker(conn), user)) as ac:
                named = await _post(ac, ids, "  NIFTY Oct condor  ")
                assert named.status_code == HTTPStatus.CREATED, named.text
                assert named.json()["name"] == quoted("NIFTY Oct condor")
                default = await _post(ac, ids)
                assert default.json()["name"] == quoted("New Strategy")
                listed = (await ac.get("/strategies")).json()["strategies"]
                assert {s["id"]: s["name"] for s in listed} == {
                    first.id: quoted("New Strategy"), named.json()["id"]: quoted("NIFTY Oct condor"),
                    default.json()["id"]: quoted("New Strategy")}
                loaded = await ac.get(f"/strategies/{named.json()['id']}")
                assert loaded.json()["name"] == quoted("NIFTY Oct condor")
        finally:
            await trans.rollback()


@pytest.mark.parametrize("name", ["", "   ", " \t "])
async def test_ac1_an_empty_name_is_refused_with_the_catalogue_message_and_stores_nothing(app_engine, name):
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids, _ = await _with_draft(conn, user := _user())
            async with _client(_app(_ConnMaker(conn), user)) as ac:
                before = len((await ac.get("/strategies")).json()["strategies"])
                refused = await _post(ac, ids, name)
                assert (refused.status_code, refused.json()["code"]) == (422, EMPTY_NAME_CODE), refused.text
                assert refused.json()["what_happened"] == "Give the strategy a name"
                assert len((await ac.get("/strategies")).json()["strategies"]) == before
        finally:
            await trans.rollback()


@pytest.mark.parametrize("name,ok", [("a", True), ("x" * 40, True), ("x" * 41, False), ("two\nlines", False),
                                     ("<script>" + "alert(1);" * 60 + "</script>", False)])
async def test_ac1_name_length_boundaries_through_the_api(app_engine, name, ok):
    """Attack 4/6: 1 and 40 characters are stored; 41, a line break and a very long script text are refused (422)."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids, _ = await _with_draft(conn, user := _user())
            async with _client(_app(_ConnMaker(conn), user)) as ac:
                response = await _post(ac, ids, name)
                if ok:
                    assert (response.status_code, response.json()["name"]) == (201, quoted(name))
                else:
                    assert (response.status_code, response.json()["code"]) == (422, INVALID_NAME_CODE), response.text
        finally:
            await trans.rollback()


async def test_ac1_markup_in_a_name_comes_back_as_plain_json_text(app_engine):
    """Attack 6: a name with markup is stored as typed and comes back as a JSON string value, in the closed shape."""
    markup = "<img src=x onerror=alert(1)>"
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids, _ = await _with_draft(conn, user := _user())
            async with _client(_app(_ConnMaker(conn), user)) as ac:
                created = await _post(ac, ids, markup)
                listed = await ac.get("/strategies")
            assert created.headers["content-type"].startswith("application/json")
            assert created.json()["name"] == quoted(markup)
            assert quoted(markup) in [s["name"] for s in listed.json()["strategies"]]
            assert set(created.json()) >= {"id", "name", "revision"}  # the closed StrategyOut, nothing extra
        finally:
            await trans.rollback()


async def test_ac1_two_strategies_of_one_user_may_share_a_name_and_keep_their_ids(app_engine):
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids, _ = await _with_draft(conn, user := _user())
            async with _client(_app(_ConnMaker(conn), user)) as ac:
                one, two = await _post(ac, ids, "Same"), await _post(ac, ids, "Same")
                assert (one.status_code, two.status_code) == (201, 201)
                assert one.json()["id"] != two.json()["id"]
                listed = (await ac.get("/strategies")).json()["strategies"]
                assert [s["name"] for s in listed].count(quoted("Same")) == SHARED_NAME_COUNT
        finally:
            await trans.rollback()


# --- AC-2: Save As -----------------------------------------------------------------------------------------------


async def test_ac2_save_as_creates_a_second_strategy_and_leaves_the_original_byte_identical(app_engine):
    """Attack 2: the original's stored definition text, revision and last-saved time are identical before and after;
    the copy has a new id, the same legs, and editing the copy never changes the original."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids, original = await _with_draft(conn, user := _user())
            before = await _snapshot(conn, original.id)
            async with _client(_app(_ConnMaker(conn), user)) as ac:
                copy = await _post(ac, ids, "New Strategy copy")
                assert copy.status_code == HTTPStatus.CREATED and copy.json()["id"] != original.id, copy.text
                assert await _snapshot(conn, original.id) == before
                edited = await ac.put(f"/strategies/{copy.json()['id']}",
                                      json=_body(ids, wing=WING, expected_revision=1))
                assert edited.status_code == HTTPStatus.OK, edited.text
            assert await _snapshot(conn, original.id) == before
            legs = lambda r: [(leg["contract_id"], leg["action"], leg["quantity"]) for leg in r["definition"]["legs"]]  # noqa: E731
            assert legs(copy.json()) == legs(await store_view(conn, user, original.id))
        finally:
            await trans.rollback()


async def store_view(conn, user: str, strategy_id: int) -> dict:
    async with _client(_app(_ConnMaker(conn), user)) as ac:
        return (await ac.get(f"/strategies/{strategy_id}")).json()


# --- AC-3: rename ------------------------------------------------------------------------------------------------


async def test_ac3_rename_changes_only_the_name_and_adds_one_history_entry(app_engine):
    """The definition text, revision and last-saved time are unchanged; one history entry reads Renamed from X to Y
    (quoted, in labelled slots); the same name again writes nothing."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids, stored = await _with_draft(conn, user := _user())
            before = await _snapshot(conn, stored.id)
            async with _client(_app(_ConnMaker(conn), user)) as ac:
                renamed = await ac.patch(f"/strategies/{stored.id}/name",
                                         json={"name": " Condor wider ", "expected_revision": 1})
                assert renamed.status_code == HTTPStatus.OK, renamed.text
                assert renamed.json()["name"] == quoted("Condor wider") and renamed.json()["revision"] == 1
                after = await _snapshot(conn, stored.id)
                assert after[:3] == before[:3] and after[3] == "Condor wider"
                history = (await ac.get(f"/strategies/{stored.id}/history")).json()["entries"]
                assert [e["change_summary"] for e in history] == [f'Renamed from {quoted("New Strategy")} to '
                                                                  f'{quoted("Condor wider")}']
                assert history[0]["definition"]["legs"][0]["contract_id"] == ids["NIFTY26O1322800CE"]
                rows = await _history_rows(conn, stored.id)
                again = await ac.patch(f"/strategies/{stored.id}/name",
                                       json={"name": "Condor wider", "expected_revision": 1})
                assert again.status_code == HTTPStatus.OK
                assert await _history_rows(conn, stored.id) == rows
        finally:
            await trans.rollback()


async def test_ac3_a_sentence_like_name_is_shown_back_only_in_the_labelled_from_to_fields(app_engine):
    """ADR-003: 'You should buy now' is stored as the user's words and appears only quoted inside the from/to slots of
    the rename line, never as platform wording."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            _, stored = await _with_draft(conn, user := _user())
            sentence = "You should buy now"
            async with _client(_app(_ConnMaker(conn), user)) as ac:
                renamed = await ac.patch(f"/strategies/{stored.id}/name",
                                         json={"name": sentence, "expected_revision": 1})
                assert renamed.json()["name"] == quoted(sentence)
                (entry,) = (await ac.get(f"/strategies/{stored.id}/history")).json()["entries"]
            assert entry["change_summary"] == f'Renamed from {quoted("New Strategy")} to {quoted(sentence)}'
            assert entry["change_summary"].count(sentence) == 1
        finally:
            await trans.rollback()


async def test_ac3_a_stale_revision_is_refused_409_and_writes_nothing(app_engine):
    """Attack 5: a rename based on an old revision changes no name and adds no history."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            ids, stored = await _with_draft(conn, user := _user())
            async with _client(_app(_ConnMaker(conn), user)) as ac:
                edited = await ac.put(f"/strategies/{stored.id}", json=_body(ids, wing=WING, expected_revision=1))
                assert edited.json()["revision"] == SECOND_REVISION
                before, rows = await _snapshot(conn, stored.id), await _history_rows(conn, stored.id)
                stale = await ac.patch(f"/strategies/{stored.id}/name", json={"name": "Late", "expected_revision": 1})
                assert (stale.status_code, stale.json()["code"]) == (409, CONFLICT_CODE), stale.text
            assert await _snapshot(conn, stored.id) == before and await _history_rows(conn, stored.id) == rows
        finally:
            await trans.rollback()


@pytest.mark.parametrize("name,code", [("", EMPTY_NAME_CODE), ("   ", EMPTY_NAME_CODE), ("x" * 41, INVALID_NAME_CODE)])
async def test_ac3_a_rename_follows_the_same_name_rules(app_engine, name, code):
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            _, stored = await _with_draft(conn, user := _user())
            before = await _snapshot(conn, stored.id)
            async with _client(_app(_ConnMaker(conn), user)) as ac:
                refused = await ac.patch(f"/strategies/{stored.id}/name", json={"name": name, "expected_revision": 1})
                assert (refused.status_code, refused.json()["code"]) == (422, code), refused.text
            assert await _snapshot(conn, stored.id) == before
        finally:
            await trans.rollback()


async def test_ac3_a_strategy_with_a_stored_version_can_be_renamed_and_its_version_rows_do_not_change(admin_engine):
    """Attack 5: the strategy has a stored version row (migration 0022); the rename leaves every version row, the
    revision and the definition as they were, and the rename never reads the execution state (so a strategy that sent
    a basket is renamed the same way). The fill-and-return path itself needs a clean catalogue, which the shared
    test database does not have; tests_app/test_strategy_versions_app.py covers an executed strategy in CI."""
    versions = text("SELECT number, state, definition::text, outcome, confirmed_at, reconciled_at "
                    "FROM public.strategy_versions WHERE strategy_id = :s ORDER BY number")
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            _, stored = await _with_draft(conn, user := _user())
            await conn.execute(text("INSERT INTO public.strategy_versions (strategy_id, number, state, definition, "
                                    "definition_schema_version) SELECT id, 1, 'proposed', definition, "
                                    "definition_schema_version FROM public.strategies WHERE id = :s"), {"s": stored.id})
            rows, before = (await conn.execute(versions, {"s": stored.id})).all(), await _snapshot(conn, stored.id)
            assert len(rows) == 1
            async with _client(_app(_ConnMaker(conn), user)) as ac:
                renamed = await ac.patch(f"/strategies/{stored.id}/name",
                                         json={"name": "Has a version", "expected_revision": 1})
                assert renamed.status_code == HTTPStatus.OK, renamed.text
            after = await _snapshot(conn, stored.id)
            assert after[:3] == before[:3] and after[3] == "Has a version"
            assert (await conn.execute(versions, {"s": stored.id})).all() == rows
        finally:
            await trans.rollback()


# --- AC-6: only the signed-in user's own strategies --------------------------------------------------------------


async def test_ac6_another_user_cannot_list_read_or_rename_a_strategy_and_the_answer_equals_a_missing_id(app_engine):
    """Attack 1: user B's list holds none of A's rows or names; B's rename and read of A's id answer exactly what a
    missing id answers (404, same body); A's name is unchanged."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            _, mine = await _with_draft(conn, user := _user())
            async with _client(_app(_ConnMaker(conn), user)) as ac:
                await ac.patch(f"/strategies/{mine.id}/name", json={"name": "Private condor", "expected_revision": 1})
            before = await _snapshot(conn, mine.id)
            async with _client(_app(_ConnMaker(conn), "someone-else")) as ac:
                listed = await ac.get("/strategies")
                read = await ac.get(f"/strategies/{mine.id}")
                rename = await ac.patch(f"/strategies/{mine.id}/name", json={"name": "Stolen", "expected_revision": 1})
                missing = await ac.patch(f"/strategies/{MISSING_ID}/name",
                                         json={"name": "Stolen", "expected_revision": 1})
            assert listed.json() == {"strategies": []} and "Private" not in listed.text
            assert (read.status_code, read.json()["code"]) == (404, NOT_FOUND_CODE)
            assert (rename.status_code, rename.json()) == (missing.status_code, missing.json()) == (404, missing.json())
            assert "Private" not in rename.text + read.text
            assert await _snapshot(conn, mine.id) == before
        finally:
            await trans.rollback()


# --- AC-4: the enriched list ---------------------------------------------------------------------------------------


async def test_ac4_the_list_carries_underlying_first_leg_leg_count_and_the_tracked_state(app_engine, admin_engine):
    """Per strategy: name, underlying, the first leg's contract terms, leg_count (the browser writes "... and 3 more"),
    last-saved time and tracked read from the real tracking table (a strategy with a tracking row: true)."""
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            _, tracked = await _with_draft(conn, user := _user())
            _, untracked = await _with_draft(conn, user)
            await conn.execute(text("INSERT INTO public.strategy_tracking (strategy_id, strategy_revision, "
                                    "price_health, prices_at) VALUES (:id, 1, 'available', now())"), {"id": tracked.id})
            async with _client(_app(_ConnMaker(conn), user)) as ac:
                listed = await ac.get("/strategies")
            by_id = {s["id"]: s for s in listed.json()["strategies"]}
            row = by_id[tracked.id]
            assert row["underlying"] == "NIFTY" and row["leg_count"] == LEG_COUNT
            assert row["first_leg"] == {"instrument": "CE", "strike": "22800.00", "expiry": "2026-10-13"}
            assert datetime.datetime.fromisoformat(row["updated_at"]) == tracked.updated_at
            assert (row["tracked"], by_id[untracked.id]["tracked"]) == (True, False)
        finally:
            await trans.rollback()


async def test_ac4_when_the_tracking_read_fails_the_list_answers_and_tracked_is_unknown(app_engine, monkeypatch):
    """Standing item (d): a failed tracking read never reads "not tracked"; the rows still come back."""
    from ofo_app import tracking_store  # noqa: PLC0415

    async def broken(conn, ids):
        raise RuntimeError("tracking store unreachable")

    monkeypatch.setattr(tracking_store, "tracked_ids", broken)
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            _, stored = await _with_draft(conn, user := _user())
            async with _client(_app(_ConnMaker(conn), user)) as ac:
                listed = await ac.get("/strategies")
            assert listed.status_code == HTTPStatus.OK
            assert [(s["id"], s["tracked"]) for s in listed.json()["strategies"]] == [(stored.id, None)]
        finally:
            await trans.rollback()


async def test_ac4_the_list_reads_only_the_signed_in_users_rows_in_the_store(app_engine):
    """Store level: the list is scoped by user_ref (mutation target: the WHERE clause)."""
    async with app_engine.connect() as conn:
        trans = await conn.begin()
        try:
            _, mine = await _with_draft(conn, user := _user())
            await store.rename(conn, user, mine.id, "Mine", expected_revision=1)
            _, theirs = await _with_draft(conn, other := _user())
            assert [(s.id, s.name) for s in await store.list_strategies(conn, user)] == [(mine.id, "Mine")]
            assert [s.id for s in await store.list_strategies(conn, other)] == [theirs.id]
            assert json.dumps([s.name for s in await store.list_strategies(conn, "nobody")]) == "[]"
        finally:
            await trans.rollback()
