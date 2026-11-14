"""GC-ICFIX issue 13 (ADR-309): the rule's shown state follows the alert gate's open RECORD, not each poll.

Trade 142: T-01 (spot within 0.35 %) fired at 0.3482, then polls read 0.3500 / 0.3496 / 0.3510. Pure: no database
(the store reads are faked). Not covered here, parked (no stored pending sample; see the report): "condition met, alert
not raised yet" and the dropped pending sample."""
from __future__ import annotations

import asyncio
import datetime
from decimal import Decimal as D

import pytest
from ofo.adjustment import playbook_eval as pe
from ofo_app import playbook_store
from ofo_app.routes import adjustment_check as route
from ofo_app.strategy_refused import StrategyRefused
from sqlalchemy.exc import SQLAlchemyError

SHOWN = datetime.datetime(2026, 11, 13, 13, 48, tzinfo=datetime.timezone.utc)


def _rec(rule_id="T-01", trigger="T-01", value="0.3482", threshold="0.3500") -> playbook_store.Suggestion:
    return playbook_store.Suggestion(id=7, strategy_id=142, rule_id=rule_id, trigger_id=trigger, stage="Middle",
                                     value=D(value), threshold=D(threshold), shown_at=SHOWN, outcome="open",
                                     dismiss_reason=None, timeline=[])


def _ev(rule_id="T-01", trigger="T-01", live="0.3510", fired=False, cmp="le", results=(), clear=True):
    rv = pe.RuleValue(rule_id, trigger, D(live), D("0.3500"), cmp, fired)
    return pe.Evaluation("Middle", 1, tuple(results), {}, clear=(rule_id,) if clear else (), values=(rv,))


def _read(monkeypatch, recs, ev, held=None):
    async def open_suggestions(*_a):
        if isinstance(recs, Exception):
            raise recs
        return recs

    async def dismissed_holding(*_a):
        return held or {}

    monkeypatch.setattr(playbook_store, "open_suggestions", open_suggestions)
    monkeypatch.setattr(playbook_store, "dismissed_holding", dismissed_holding)
    return asyncio.run(route.stored_records(None, "u", 142, ev))


def _shown(results, opened):
    return [route.result_out(r, "w", opened) for r in results]


def test_a_open_record_live_value_inside_the_line_still_fired(monkeypatch):
    opened, _d, fired_at, results = _read(monkeypatch, [_rec()], _ev(live="0.3510"))
    (out,) = _shown(results, opened)
    assert (out["kind"], out["rule_id"], out["value"], out["suggestion_id"]) == ("flag", "T-01", D("0.3482"), 7)
    assert fired_at["T-01"] == SHOWN
    assert route.live_values(_ev(live="0.3510"))["T-01"] == D("0.3510")


@pytest.mark.parametrize("live", ["0.3500", "0.3496", "0.3510", "0.3482"])
def test_a_trade_142_polls_around_the_line_never_turn_it_quiet(monkeypatch, live):
    _o, _d, _f, results = _read(monkeypatch, [_rec()], _ev(live=live, fired=live <= "0.3500"))
    assert [r.rule_id for r in results if isinstance(r, pe.Flag)] == ["T-01"]


def test_b_record_cleared_by_the_gate_is_quiet(monkeypatch):
    opened, _d, fired_at, results = _read(monkeypatch, [], _ev(live="0.3510"))
    assert results == [] and opened == {} and fired_at == {}


def test_a_flag_with_its_record_is_unchanged(monkeypatch):
    flag = pe.Flag("T-01", "T-01", "Middle", D("0.3482"), D("0.3500"), "le")
    ev = _ev(live="0.3482", fired=True, results=(flag,), clear=False)
    opened, _d, _f, results = _read(monkeypatch, [_rec()], ev)
    assert list(results) == [flag] and opened == {"T-01": 7}
    assert route.live_values(ev)["T-01"] == D("0.3482")


def test_a_rule_the_check_could_not_evaluate_is_never_invented_from_the_record(monkeypatch):
    nc = pe.NotChecked("T-01", "T-01", "x")
    ev = _ev(results=(nc,), clear=False)
    _o, _d, _f, results = _read(monkeypatch, [_rec()], ev)
    assert list(results) == [nc]


def test_e_a_stop_follows_its_record_the_same_way(monkeypatch):
    rec = _rec("T-06", "T-06", "10.5", "10")
    ev = _ev("T-06", "T-06", live="9.5", cmp="ge")
    opened, _d, fired_at, results = _read(monkeypatch, [rec], ev)
    (out,) = _shown(results, opened)
    assert (out["kind"], out["rule_id"], out["value"]) == ("flag", "T-06", D("10.5000"))
    assert fired_at["T-06"] == SHOWN


def test_f_a_failed_record_read_is_the_could_not_read_state_never_quiet(monkeypatch):
    with pytest.raises(StrategyRefused):
        _read(monkeypatch, SQLAlchemyError("down"), _ev())
