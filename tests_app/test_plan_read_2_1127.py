"""Lane R3 (hotfix plan-read-2-1127). Items 1 and 2: the expiry kind of a stored trade is read from the stored
catalogue by ONE rule (``adjustment_readers.expiry_kind_of``); a kind that cannot be known is "" and the live check
then checks nothing (never the weekly row by default).

Real shape of item 1: futures listed for 24 Nov, 29 Dec and 26 Jan; a leg expiring 30 Mar 2027 read as weekly."""
from __future__ import annotations

import datetime
from decimal import Decimal as D
from types import SimpleNamespace

import pytest
import t19_support as t19
import test_stop_base_fixed as base
from ofo.adjustment import stop_lines as sl
from ofo.marketdata.spot_source import SpotAnswer
from ofo_app import adjustment_check as check
from ofo_app import adjustment_readers as readers
from ofo_app.routes.adjustment import MarketInputs

seams = base.seams  # the sibling's fixture: stored orders and contracts without a database
import test_plan_save_1127 as save_test  # noqa: E402

app_db_url = save_test.app_db_url  # the sibling's fixture: the app's engine on the fresh database

F1, F2, F3 = datetime.date(2026, 11, 24), datetime.date(2026, 12, 29), datetime.date(2027, 1, 26)
FUTURES = frozenset({F1, F2, F3})


def test_a_far_month_with_no_future_of_its_month_is_not_known_not_weekly():
    assert readers.expiry_kind_of(datetime.date(2027, 3, 30), [], FUTURES, None) == ""


def test_the_kind_of_a_leg_inside_the_listed_futures_is_still_read():
    assert readers.expiry_kind_of(F2, [], FUTURES, None) == "monthly"
    assert readers.expiry_kind_of(datetime.date(2026, 12, 8), [], FUTURES, None) == "weekly"


def test_no_future_listed_at_all_is_not_known():
    assert readers.expiry_kind_of(F2, [], frozenset(), None) == ""


def test_a_scenario_that_states_the_kind_wins():
    scn = SimpleNamespace(data={"expiry_kind": "monthly"})
    assert readers.expiry_kind_of(datetime.date(2027, 3, 30), [], FUTURES, scn) == "monthly"


# ---- item 2: the position of a STORED trade carries its kind, so the live check reads the row of that kind ----------
class _Row:
    def __init__(self, name, expiry, future):
        self.currently_listed = True
        self.contract = SimpleNamespace(name=name, expiry=expiry, is_future=lambda: future,
                                        is_option=lambda: not future)


class _Cat:
    def __init__(self, rows):
        self.rows = rows

    def all_entries(self):
        return self.rows


def _catalogue(monkeypatch, futures):
    async def load(_db, _name=None):
        return _Cat([_Row("NIFTY", d, True) for d in futures] + [_Row("NIFTY", base.EXPIRY, False)])
    monkeypatch.setattr(readers, "load_catalogue", load, raising=False)


def _weekly_monthly_body() -> dict:
    body = base.plan_body()
    body["triggers"][sl.TRIGGER_MAX_LOSS]["weekly"] = ["50"] * 3
    body["triggers"][sl.TRIGGER_MAX_LOSS]["monthly"] = ["30"] * 3
    return body


def _stop_percent(tracked, body):
    """The T-06 percent the live check's ``state_of`` reads for this stored trade with NO market kind (the market
    reader had no session): the real builder, the real stop lines."""
    market = MarketInputs((), {}, None, None, None, None, None, base.NOW)  # expiry_kind "" (no session)
    resolved = check.Resolved("plan", body, 9, None, False, saved_before_adr247=False)
    state = check.state_of(tracked, market, SpotAnswer(D("23800"), "feed", base.NOW), None, t19.RATES, True, body,
                           config=t19.PREFS.approach, user_values=None, strategy_layer=None, entry_facts=None,
                           resolved=resolved)
    lines = {x.kind: x for x in state.stops.lines} if state.stops is not None else {}
    return lines.get(sif_max_loss()), state


def sif_max_loss():
    from ofo_app import settings_in_force as sif  # noqa: PLC0415
    return sif.STOP_MAX_LOSS


def test_a_stored_monthly_trade_reads_the_monthly_row_with_no_market_kind(seams, monkeypatch):
    """CORE (item 2). The leg day is also a future day: monthly. Before the fix the position's kind was "" and the
    live check used the weekly row (50 %, not 30 %)."""
    _catalogue(monkeypatch, (base.EXPIRY,))
    seams.plan = base._plan(body=_weekly_monthly_body())
    tracked = base._read(seams, base.ENTRY)
    assert tracked.position.expiry_kind == "monthly"
    line, state = _stop_percent(tracked, _weekly_monthly_body())
    assert state.expiry_kind == "monthly"
    assert line is not None and line.figure == D("30")


def test_a_stored_weekly_trade_reads_the_weekly_row(seams, monkeypatch):
    _catalogue(monkeypatch, (base.EXPIRY + datetime.timedelta(days=-14), base.EXPIRY + datetime.timedelta(days=28)))
    seams.plan = base._plan(body=_weekly_monthly_body())
    tracked = base._read(seams, base.ENTRY)
    assert tracked.position.expiry_kind == "weekly"
    line, _state = _stop_percent(tracked, _weekly_monthly_body())
    assert line is not None and line.figure == D("50")


@pytest.mark.parametrize("futures", [(), (datetime.date(2026, 10, 27),)])
def test_a_kind_that_cannot_be_known_checks_no_stop_and_never_reads_weekly(seams, monkeypatch, futures):
    """No future listed, or the leg is past the last listed future: the position's kind stays "" and the live check
    checks NO percent stop (not checked), never the weekly row. FD5 3.6: the stop lines now exist for an unknown kind
    (so a kind-free stop such as the 2x credit has its result), but the percent line carries no figure and says why."""
    _catalogue(monkeypatch, futures)
    seams.plan = base._plan(body=_weekly_monthly_body())
    tracked = base._read(seams, base.ENTRY)
    assert tracked.position.expiry_kind == ""
    line, state = _stop_percent(tracked, _weekly_monthly_body())
    assert line is None or (line.figure is None and line.reason == "stop_expiry_kind_unknown")
    assert state.days_left is None


def test_a_catalogue_read_that_fails_leaves_the_kind_empty(seams, monkeypatch):
    async def broken(_db, _name=None):
        raise RuntimeError("database down")
    monkeypatch.setattr(readers, "load_catalogue", broken, raising=False)
    seams.plan = base._plan(body=_weekly_monthly_body())
    assert base._read(seams, base.ENTRY).position.expiry_kind == ""


# ---- review findings (Opus, 27 Nov): the nearest leg decides, as the check counts its days ----
def test_the_kind_is_read_for_the_nearest_leg_not_the_first_one_ordered(monkeypatch):
    import asyncio  # noqa: PLC0415

    async def load(_db, _name=None):
        return _Cat([_Row("NIFTY", d, True) for d in FUTURES])
    monkeypatch.setattr(readers, "load_catalogue", load, raising=False)
    far, near = SimpleNamespace(expiry=F2), SimpleNamespace(expiry=datetime.date(2026, 12, 2))
    # the far long leg was bought first: it is legs[0]; the check counts days to the nearest leg (2 Dec = weekly)
    assert asyncio.run(readers._stored_kind_or_empty(None, "NIFTY", (far, near))) == "weekly"
    assert asyncio.run(readers._stored_kind_or_empty(None, "NIFTY", (near, far))) == "weekly"


def test_the_entry_state_has_no_day_count_when_the_kind_is_not_known(seams, monkeypatch):
    _catalogue(monkeypatch, ())
    seams.plan = base._plan(body=_weekly_monthly_body())
    tracked = base._read(seams, base.ENTRY)
    _line, state = _stop_percent(tracked, _weekly_monthly_body())
    assert state.days_left is None
    held = check._entry_state(base.NOW, D("23800"), None, state, tracked.position)
    assert held.days_left is None


# ---- item 4 (OBS-26): a save whose answer never reached the browser (timed out) was stored, and the next read must
# return the stored plan COMPLETE (rules, settings, stops, exits) on the right row ----
async def test_a_saved_plan_whose_answer_was_lost_reads_back_complete_on_the_monthly_row(app_db_url, monkeypatch):
    import test_plan_read_1127 as read_test  # noqa: PLC0415
    from test_adjustment_plan import OK, _call, _plan_path  # noqa: PLC0415
    sid, own = await read_test._saved_monthly(app_db_url, monkeypatch, "Lost answer")
    # the browser never saw the save answer (its 30 s timeout): only the stored row and a fresh read remain
    status, saved = await _call("PUT", _plan_path(sid), json={"playbook_id": own.id, "target": "55"})
    assert status == OK, saved
    status, read = await _call("GET", _plan_path(sid))
    assert status == OK, read
    for field in ("triggers", "settings", "stops", "triggers_reason", "stop_kind_reason"):
        assert read[field] == saved[field], field  # the read-back is the answer the save would have given
    assert read["triggers"], "the rules must be read back, not empty"
    assert read["settings"], "the settings must be read back, not empty"
    assert read["stops"]["lines"], "the stop lines must be read back, not empty"
    assert D(read["plan"]["stop"]) == D("30") and read["plan"]["target"] == "55"  # monthly row, the new target
    again = (await _call("GET", _plan_path(sid)))[1]
    assert again == read  # reading twice is the same answer (no state in the read)
