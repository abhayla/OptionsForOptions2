"""GC-IC1 6a (ADR-240 (3)) screen / worker inputs (pure, no DB): ``adjustment_check.held_legs`` reads every open leg's
engine Greeks from ``MarketInputs.leg_greeks`` (a symbol absent -> None, never a delta of 0); ``entry_day`` is the IST
date of the strategy's first stored order (``adjustment_readers.entered_at``); ``trigger_words`` names a situation
record by the playbook's own situation name."""
from __future__ import annotations

import datetime
from decimal import Decimal as D
from types import SimpleNamespace

from ofo.adjustment import playbook_eval as pe
from ofo.adjustment.approaches import Position, PositionLeg
from ofo.engine.black_scholes import Greeks
from ofo.timeutil import IST
from ofo_app import adjustment_check as check
from ofo_app.adjustment_readers import entered_at

EXP = datetime.date(2026, 11, 3)
Z = D(0)


def _position() -> Position:
    return Position("NIFTY", 75, "weekly", EXP, (
        PositionLeg("SELL", "CE", D(23450), EXP, 2, D(60), "NIFTY26N0323450CE"),
        PositionLeg("BUY", "CE", D(23650), EXP, 2, D(20), "NIFTY26N0323650CE")))


def test_held_legs_carry_the_engine_greeks_and_lots_and_none_when_absent():
    g = Greeks(D("0.45"), Z, Z, Z)
    market = SimpleNamespace(leg_greeks={"NIFTY26N0323450CE": g})
    held = check.held_legs(_position(), market)
    assert held == (pe.HeldLeg(g, "SELL", 2), pe.HeldLeg(None, "BUY", 2))


def test_entry_day_is_the_ist_date_of_the_first_order():
    # 2026-10-27 20:00 UTC is 28 Oct 01:30 IST: the IST date, never the UTC one
    first = datetime.datetime(2026, 10, 27, 20, 0, tzinfo=datetime.UTC)
    later = datetime.datetime(2026, 10, 29, 5, 0, tzinfo=datetime.UTC)
    orders = [SimpleNamespace(created_at=later), SimpleNamespace(created_at=first)]
    at = entered_at(orders)
    assert at == first
    assert check.entry_day(SimpleNamespace(entered_at=at)) == datetime.date(2026, 10, 28)
    assert entered_at([]) is None and check.entry_day(SimpleNamespace(entered_at=None)) is None
    assert first.astimezone(IST).date() == datetime.date(2026, 10, 28)


def test_trigger_words_name_a_situation_record_by_the_playbook():
    body = {"situations": [{"id": "S-02", "name": "Trending day"}, {"id": "S-12", "name": "Big win early"}]}
    assert check.trigger_words(body, "sit.S-02") == ("Trending day", None)
    assert check.trigger_words(body, "sit.S-12") == ("Big win early", "%")
    assert check.trigger_words(body, "sit.S-03") == (None, None)
