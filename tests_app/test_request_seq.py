"""W-151 (REQ-119 AC-1, server half): each builder-screen request may carry a sequence id ``seq``; the server echoes it
UNCHANGED as ``seq`` in the reply. No seq in the request -> no ``seq`` key in the reply, so every other caller keeps
today's exact keys. A bool, a string, a negative number or one above the INTEGER range is a malformed request.

Spec basis: REQ-119 AC-1 "the server echoes it unchanged in the reply". The three requests: POST
/api/strategies/outcome, POST /api/strategies/leg-edit (margin and the table ride inside these two replies), POST
/strategies/{id}/execute. The live socket push (``outcome_response`` without a seq) keeps today's keys (row 24
versions the socket frames).

Outcome and leg-edit run with no database (the replayed 2026-10-08 feed / the stubbed leg-edit seams); the execute
echo needs the stored strategy, so it runs on the database in CI (as ``test_execute_revision.py``).
"""
from __future__ import annotations

import pytest
from pydantic import BaseModel
from test_execute_revision import _run
from test_leg_edit_route import legs
from test_leg_edit_route import post as leg_edit_post
from test_outcome_route import _body, _post, replayed  # noqa: F401 - ``replayed`` is the module fixture

GOOD = [1, 7, 2**31 - 1]
BAD = [True, "3", -1, 2**31, 1.5]
INPUT_REFUSED = "USER_INPUT_002"  # the catalogue answer for a body the model refuses
STEP = {"control": "step", "index": 2, "direction": 1}


# ---- POST /api/strategies/outcome ---------------------------------------------------------------------------------

@pytest.mark.parametrize("seq", GOOD)
async def test_outcome_echoes_seq_unchanged(replayed, seq):  # noqa: F811
    resp = await _post({**_body(replayed), "seq": seq}, replayed)
    assert resp.status_code == 200, resp.text  # noqa: PLR2004
    body = resp.json()
    assert body["seq"] == seq and type(body["seq"]) is int


async def test_outcome_without_seq_has_no_seq_key_and_otherwise_the_same_answer(replayed):  # noqa: F811
    plain = (await _post(_body(replayed), replayed)).json()
    assert "seq" not in plain
    with_seq = (await _post({**_body(replayed), "seq": 7}, replayed)).json()
    assert {k: v for k, v in with_seq.items() if k != "seq"} == plain  # the seq adds one key and changes nothing


@pytest.mark.parametrize("seq", BAD)
async def test_outcome_refuses_a_malformed_seq(replayed, seq):  # noqa: F811
    resp = await _post({**_body(replayed), "seq": seq}, replayed)
    assert resp.status_code == 422, resp.text  # noqa: PLR2004
    assert resp.json()["code"] == INPUT_REFUSED


# ---- POST /api/strategies/leg-edit --------------------------------------------------------------------------------

@pytest.mark.parametrize("seq", GOOD)
def test_leg_edit_echoes_seq_unchanged(seq):
    status, reply = leg_edit_post({"legs": legs(), "edit": STEP, "seq": seq})
    assert status == 200, reply  # noqa: PLR2004
    assert reply["seq"] == seq and type(reply["seq"]) is int
    assert "seq" not in (reply.get("outcome") or {})  # the echo is the reply's own, once


def test_leg_edit_without_seq_has_no_seq_key_and_otherwise_the_same_answer():
    status, plain = leg_edit_post({"legs": legs(), "edit": STEP})
    assert status == 200 and "seq" not in plain  # noqa: PLR2004
    _, with_seq = leg_edit_post({"legs": legs(), "edit": STEP, "seq": 7})
    assert {k: v for k, v in with_seq.items() if k != "seq"} == plain


@pytest.mark.parametrize("seq", BAD)
def test_leg_edit_refuses_a_malformed_seq(seq):
    status, reply = leg_edit_post({"legs": legs(), "edit": STEP, "seq": seq})
    assert status == 422, reply  # noqa: PLR2004
    assert reply["code"] == INPUT_REFUSED


# ---- POST /strategies/{id}/execute --------------------------------------------------------------------------------

@pytest.mark.usefixtures("order_path_on")
@pytest.mark.parametrize("seq", BAD)
async def test_execute_refuses_a_malformed_seq(seq, monkeypatch):
    from test_execute_revision import (  # noqa: PLC0415 - the shared refusal test, read only here
        test_a_missing_or_malformed_revision_is_a_malformed_request as refused,
    )

    await refused({"action": "ENTRY", "revision": 1, "seq": seq}, monkeypatch)


class _Built(BaseModel):
    plan_number: int
    tags: list[str]
    seq: int | None = None


async def _execute_db_free(monkeypatch, seq):
    """The real route function with the store and the plan builder stubbed (no database, no broker)."""
    import datetime  # noqa: PLC0415
    from types import SimpleNamespace  # noqa: PLC0415

    from ofo_app.routes import execute as route  # noqa: PLC0415
    from test_execute_revision import _FakeDb  # noqa: PLC0415

    async def load(_db, _user, sid):
        return SimpleNamespace(id=sid, revision=3, saved=None)

    async def built(_req, _stored):
        # ExecuteOut's basket is built only from a real basket (BasketPost.of), so this stand-in has ExecuteOut's
        # shape for the keys under test: unset ``seq`` by default, the same pydantic model_fields_set rules
        return _Built(plan_number=9, tags=["T1"])

    monkeypatch.setattr(route.store, "load", load)
    monkeypatch.setattr(route, "_execute", built)
    body = route.ExecuteIn(action="ENTRY", revision=3, **({} if seq is None else {"seq": seq}))
    now = datetime.datetime(2026, 10, 8, 10, 0, tzinfo=datetime.UTC)
    return await route.execute_strategy(7, body, object(), None, lambda: now, _FakeDb(), "u", None)


@pytest.mark.parametrize("seq", GOOD)
async def test_execute_echoes_seq_unchanged_without_a_database(monkeypatch, seq):
    """AC-1: the reply carries the request's seq exactly, and every other key stays as built."""
    out = await _execute_db_free(monkeypatch, seq)
    dumped = out.model_dump(exclude_unset=True)
    assert dumped["seq"] == seq
    assert dumped == {"plan_number": 9, "tags": ["T1"], "seq": seq}


async def test_execute_without_seq_has_no_seq_key_without_a_database(monkeypatch):
    """AC-1: no seq sent -> no seq key (exclude_unset still omits it after the rebuild)."""
    out = await _execute_db_free(monkeypatch, None)
    assert "seq" not in out.model_dump(exclude_unset=True)


@pytest.mark.usefixtures("order_path_on", "app_engine")
@pytest.mark.parametrize("seq", GOOD)
async def test_execute_echoes_seq_unchanged(app_engine, admin_engine, monkeypatch, seq):
    resp, _kite, _rows = await _run(app_engine, admin_engine, monkeypatch,
                                    lambda rev: {"action": "ENTRY", "revision": rev, "seq": seq})
    assert resp.status_code == 200, resp.text  # noqa: PLR2004
    assert resp.json()["seq"] == seq


@pytest.mark.usefixtures("order_path_on", "app_engine")
async def test_execute_without_seq_has_no_seq_key(app_engine, admin_engine, monkeypatch):
    resp, _kite, _rows = await _run(app_engine, admin_engine, monkeypatch,
                                    lambda rev: {"action": "ENTRY", "revision": rev})
    assert resp.status_code == 200 and "seq" not in resp.json(), resp.text  # noqa: PLR2004


# ---- the live socket push -----------------------------------------------------------------------------------------

def test_the_live_push_keeps_todays_keys_even_when_the_subscribe_carried_a_seq(replayed):  # noqa: F811
    """The push path calls ``outcome_response`` with no seq (live_push.py), so a subscribe message that carried one
    still pushes today's keys: no ``seq`` set on the body and none in its JSON."""
    import json  # noqa: PLC0415

    from ofo_app.errors import socket_body  # noqa: PLC0415
    from ofo_app.routes.outcome import OutcomeRequest, OutcomeResponse, outcome_response  # noqa: PLC0415

    body = outcome_response(OutcomeRequest.model_validate({**_body(replayed), "seq": 9}), None)
    assert "seq" not in body.model_fields_set
    frame = json.loads(bytes(socket_body(body, (OutcomeResponse,))).decode("utf-8"))  # the socket's own door
    assert "seq" not in frame and frame["state"] == body.state
