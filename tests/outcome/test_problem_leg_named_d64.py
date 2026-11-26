"""GC-ICLIVE D-64 remainder: the payoff refusal names an unusable leg as the trader knows it ("NIFTY 13 Oct 22600
CE"), never by its raw instrument id, and on expiry day after the close it says when the leg settles. Real
function: build_outcome on the recorded 2026-10-08 replay (13 Oct expiry); the valuation moves to the day of
expiry.
"""
from __future__ import annotations

import datetime
import re

from ofo.outcome import build_outcome, read_snapshot
from ofo.outcome.serialize import outcome_to_dict
from ofo.settings import defaults
from ofo.timeutil import IST
from outcome._both_curves_cases import _FQ, S54, as_json, definition, market
from outcome.test_same_engine import RATE

RAW_ID = re.compile(r"\b(NSE_FO|BFO|NSE|BSE)[:_][A-Z_]*:?\d+")
LINE = "Market closed. Open legs that expire today settle at 15:45."


def _refusal(hour: int, minute: int, day: int = 13) -> str:
    provider = market()
    d = definition(provider, S54)
    at = datetime.datetime(2026, 10, day, hour, minute, tzinfo=IST)
    snap = read_snapshot(provider, "NIFTY", [p.instrument_id for p in d.legs], at, RATE, quality=_FQ)
    body = as_json(outcome_to_dict(build_outcome(d, snap, snap.valuation, settings=defaults())))
    return " | ".join(_texts(body))


def _texts(node, key=""):
    """Every string the screen can read: all values except the id fields the browser keys on (instrument_id)."""
    if isinstance(node, dict):
        return [t for k, v in node.items() for t in _texts(v, k)]
    if isinstance(node, list):
        return [t for v in node for t in _texts(v, key)]
    return [node] if isinstance(node, str) and key != "instrument_id" else []


def test_core_after_the_close_on_expiry_day_the_line_replaces_the_raw_error():
    text = _refusal(15, 35)
    assert LINE in text
    assert not RAW_ID.search(text) and "cannot be used" not in text


def test_an_expired_leg_is_named_as_the_trader_knows_it():
    text = _refusal(10, 0, day=14)  # the day after the expiry: no settlement line, the leg is named
    assert "NIFTY 13 Oct 22600 CE cannot be used: expired" in text
    assert not RAW_ID.search(text) and LINE not in text


def test_after_the_settlement_time_there_is_no_line_and_still_no_raw_id():
    text = _refusal(15, 50)
    assert LINE not in text and not RAW_ID.search(text)
    assert "NIFTY 13 Oct 22600 CE cannot be used: expired" in text


def test_before_the_close_there_is_no_refusal_line():
    assert LINE not in _refusal(11, 0)


def test_no_refusal_is_built_with_the_raw_id_template():
    """Scan: the raw-id template is never rendered by the service; refusals use the one named-leg function."""
    import pathlib  # noqa: PLC0415
    path = pathlib.Path(__file__).resolve().parents[2] / "backend/ofo/outcome/service.py"
    source = path.read_text(encoding="utf-8")
    assert 'render_explanation("outcome_problem_leg",' not in source
