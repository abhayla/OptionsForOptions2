"""Hotfix plan-read-1127 (Lane R2): every READ of the plan picks the T-06 row by the SAME known-kind rule the save
writes by (``_known_kind``: the market's kind, else the stored catalogue's, else NOT KNOWN), through one function.
A stop saved into the monthly row must read back from the monthly row with no market session."""
from __future__ import annotations

import copy
import datetime
import uuid
from decimal import Decimal as D

import test_plan_save_1127 as save_test
from ofo_app import adjustment_readers as readers
from ofo_app import playbook_store
from ofo_app.routes import adjustment_plan as route
from test_adjustment_plan import OK, UNPROCESSABLE, _call, _plan_path, _plan_row, _system_ic, _t06
from test_plan_save_1127 import ROWS_AS_IS, _accepted, _Cat, _no_session

app_db_url = save_test.app_db_url  # the sibling's fixture: the app's engine on the fresh database


async def _saved_monthly(app_db_url, monkeypatch, name):
    """A save with the market closed (no Kite session; the scenario states "monthly") that leaves the monthly row's
    stop (30) as it is. The save answer shows 30 (the monthly row, by ``_known_kind``); a set percent stop writes BOTH
    rows (``set_max_loss_stop``), so only a save that keeps the stop tells the rows apart (weekly row = 50)."""
    sid, own = await _accepted(app_db_url, monkeypatch, f"{name} {uuid.uuid4().hex[:8]}")
    _no_session(monkeypatch, "monthly")
    status, out = await _call("PUT", _plan_path(sid), json={"playbook_id": own.id, "target": "60"})
    assert status == OK, out
    assert _t06((await _plan_row(app_db_url, sid)).body) == ROWS_AS_IS
    assert D(out["plan"]["stop"]) == D("30")  # the save answer: the monthly row
    return sid, own


async def test_read_plan_with_no_session_reads_back_the_saved_monthly_stop(app_db_url, monkeypatch):
    sid, _own = await _saved_monthly(app_db_url, monkeypatch, "Read plan monthly")
    status, out = await _call("GET", _plan_path(sid))
    assert status == OK, out
    assert D(out["plan"]["stop"]) == D("30") and D(out["prefill"]["stop"]) == D("30")


async def test_read_levels_with_no_session_uses_the_saved_kind(app_db_url, monkeypatch):
    sid, _own = await _saved_monthly(app_db_url, monkeypatch, "Read levels monthly")
    seen = []
    real = route.preview_stop_figures

    def spy(body, saved_before, kind, bases, typed_in):
        seen.append(kind)
        return real(body, saved_before, kind, bases, typed_in)
    monkeypatch.setattr(route, "preview_stop_figures", spy)
    status, out = await _call("GET", _plan_path(sid) + "/levels", params={"stop": "45"})
    assert status == OK, out
    assert seen == ["monthly"]


async def test_reset_with_no_session_answers_the_monthly_row_of_the_playbook(app_db_url, monkeypatch):
    sid, _own = await _saved_monthly(app_db_url, monkeypatch, "Reset monthly")
    status, out = await _call("POST", _plan_path(sid) + "/reset")
    assert status == OK, out
    assert _t06((await _plan_row(app_db_url, sid)).body) == ROWS_AS_IS
    assert D(out["plan"]["stop"]) == D("30")  # the monthly row's first stage; the weekly row would say 50


# --- the stored catalogue as the source of the kind (no scenario): a stored FUTURE row on the leg's day = monthly ----

NOT_KNOWN = "Stop not shown: whether this trade expires weekly or monthly is not known right now"
UNREADABLE = "Stop not shown: the contract list could not be read, so the expiry type is not known"


class _Row:
    def __init__(self, name, expiry, future):
        self.currently_listed = True
        self.contract = type("C", (), {"name": name, "expiry": expiry, "is_future": lambda s: future,
                                       "is_option": lambda s: not future})()


def _stored(monkeypatch, *, futures_on, options_on=()):
    """The stored catalogue, built from the strategy's own underlying and leg day once it is read; futures on the
    given day offsets from the leg day (0 = the leg's own day)."""
    seen = {}
    own = route._own_strategy

    async def spy(*a, **k):
        seen["tracked"] = await own(*a, **k)
        return seen["tracked"]
    monkeypatch.setattr(route, "_own_strategy", spy)

    async def load(db):
        t = seen["tracked"]
        leg = t.position.legs[0].expiry
        rows = [_Row(t.position.underlying, leg + datetime.timedelta(days=d), True) for d in futures_on]
        rows += [_Row(t.position.underlying, leg + datetime.timedelta(days=d), False) for d in (0, *options_on)]
        return _Cat(rows)
    monkeypatch.setattr(route, "load_catalogue", load)
    monkeypatch.setattr(readers, "load_catalogue", load)  # R3: the position read uses the same catalogue


async def _accepted_closed(app_db_url, monkeypatch, name):
    """A plan accepted on a strategy, then the market closed with NO scenario kind (the stored catalogue decides)."""
    sid, own = await _accepted(app_db_url, monkeypatch, f"{name} {uuid.uuid4().hex[:8]}")
    _no_session(monkeypatch, None)
    return sid, own


async def test_a_stored_future_row_on_the_leg_day_reads_back_the_monthly_stop(app_db_url, monkeypatch):
    sid, own = await _accepted_closed(app_db_url, monkeypatch, "Stored future")
    _stored(monkeypatch, futures_on=(0, 28))
    status, saved = await _call("PUT", _plan_path(sid), json={"playbook_id": own.id, "target": "60"})
    assert status == OK and D(saved["plan"]["stop"]) == D("30"), saved
    status, out = await _call("GET", _plan_path(sid))
    assert status == OK and D(out["plan"]["stop"]) == D("30") and out["stop_kind_reason"] is None, out


async def test_a_far_month_with_no_future_of_its_month_is_not_known_not_weekly(app_db_url, monkeypatch):
    sid, _own = await _accepted_closed(app_db_url, monkeypatch, "Far month")
    _stored(monkeypatch, futures_on=(-28, -56))  # the listed futures are all earlier than the leg's expiry
    status, out = await _call("GET", _plan_path(sid))
    assert status == OK, out
    assert out["plan"]["stop"] is None and out["prefill"]["stop"] is None and out["plan"]["stop_words"] is None
    assert out["stop_kind_reason"] == NOT_KNOWN


async def test_a_catalogue_database_error_is_not_known_with_its_own_reason(app_db_url, monkeypatch):
    sid, own = await _accepted_closed(app_db_url, monkeypatch, "Catalogue error")

    async def broken(db):
        raise RuntimeError("database down")
    monkeypatch.setattr(route, "load_catalogue", broken)
    status, out = await _call("GET", _plan_path(sid))
    assert status == OK, out
    assert out["plan"]["stop"] is None and out["stop_kind_reason"] == UNREADABLE
    before = await _plan_row(app_db_url, sid)
    status, refused = await _call("PUT", _plan_path(sid), json={"playbook_id": own.id, "stop": "45"})
    assert status == UNPROCESSABLE and refused["what_happened"].startswith("The stop could not be saved")
    assert before == await _plan_row(app_db_url, sid)


async def test_a_percent_stop_is_saved_with_the_kind_unknown_when_both_rows_are_equal(app_db_url, monkeypatch):
    sid, own = await _accepted_closed(app_db_url, monkeypatch, "Rows equal")
    # make both rows say the same first-stage stop (the weekly row is [50,50,40], the monthly [30,30,20])
    status, saved = await _call("PUT", _plan_path(sid), json={"playbook_id": own.id, "stop": "45"})
    assert status == UNPROCESSABLE, saved  # rows differ + kind unknown: refused
    body = copy.deepcopy((await _system_ic(app_db_url)).body)
    body["triggers"]["T-06"]["weekly"] = ["50", "50", "40"]
    body["triggers"]["T-06"]["monthly"] = ["50", "50", "40"]
    async with app_db_url.begin() as conn:
        same = await playbook_store.create(conn, "owner", "ic", f"Alike {uuid.uuid4().hex[:8]}", body)
    status, out = await _call("PUT", _plan_path(sid), json={"playbook_id": same.id, "stop": "45"})
    assert status == OK, out
    assert D(out["plan"]["stop"]) == D("45") and out["stop_kind_reason"] is None


async def test_a_real_database_error_in_the_catalogue_read_leaves_the_session_usable(app_db_url, monkeypatch):
    """Opus review: a real PostgreSQL error aborts the transaction; the reads after it must still answer (no 500)."""
    from sqlalchemy import text  # noqa: PLC0415
    sid, own = await _accepted_closed(app_db_url, monkeypatch, "Real db error")

    async def broken(db):
        await db.execute(text("SELECT 1/0"))  # a real error from the database, not a Python one
    monkeypatch.setattr(route, "load_catalogue", broken)
    status, out = await _call("GET", _plan_path(sid))
    assert status == OK and out["stop_kind_reason"] == UNREADABLE and out["plan"]["stop"] is None, out
    status, refused = await _call("PUT", _plan_path(sid), json={"playbook_id": own.id, "stop": "45"})
    assert status == UNPROCESSABLE and refused["what_happened"].startswith("The stop could not be saved"), refused


async def test_a_rupee_stop_stays_shown_with_the_kind_unknown_and_no_reason(app_db_url, monkeypatch):
    """Opus review: with a rupee stop T-06 is not the stop, so differing T-06 rows must not blank it."""
    sid, own = await _accepted_closed(app_db_url, monkeypatch, "Rupee stays")
    status, saved = await _call("PUT", _plan_path(sid), json={"playbook_id": own.id, "stop_rupees": "100"})
    assert status == OK, saved
    status, out = await _call("GET", _plan_path(sid))
    assert status == OK, out
    assert D(out["plan"]["stop_rupees"]) == D("100") and out["stop_kind_reason"] is None, out
    assert out["plan"]["stop_words"] is not None


async def test_the_levels_warning_for_a_rupee_stop_above_max_loss_stays_with_the_kind_unknown(app_db_url, monkeypatch):
    sid, _own = await _accepted_closed(app_db_url, monkeypatch, "Levels warning")
    status, out = await _call("GET", _plan_path(sid) + "/levels", params={"stop_rupees": "99999999"})
    assert status == OK, out
    assert out["stop"]["warning"] is not None and out["stop"]["words"] is None, out


async def test_the_reason_shows_when_the_plan_is_blanked_though_the_picked_playbook_is_not(app_db_url, monkeypatch):
    sid, _own = await _accepted_closed(app_db_url, monkeypatch, "Reason by plan")
    body = copy.deepcopy((await _system_ic(app_db_url)).body)
    body["triggers"]["T-06"]["weekly"] = ["50", "50", "40"]
    body["triggers"]["T-06"]["monthly"] = ["50", "50", "40"]
    async with app_db_url.begin() as conn:
        same = await playbook_store.create(conn, "owner", "ic", f"Alike2 {uuid.uuid4().hex[:8]}", body)
    status, out = await _call("GET", _plan_path(sid), params={"playbook_id": same.id})
    assert status == OK, out
    assert out["prefill"]["stop"] is not None  # the picked playbook's rows agree: its stop is shown
    assert out["plan"]["stop"] is None and out["stop_kind_reason"] == NOT_KNOWN, out  # the saved plan's is not
