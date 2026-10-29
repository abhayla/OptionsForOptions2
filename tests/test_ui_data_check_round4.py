"""GC-UI step 4 server round 4, item 3: the independent checker's rules for the round 3 / 4 reply blocks.

The checker (scripts/checks/ui_data_check.py) imports nothing from ``ofo``; this test may, to build a REAL reply
(strategy 54 on the recorded 2026-10-08 NIFTY replay) and show the checker's own numbers agree with it, then tamper
the reply and show the checker flags it. Rules: ``open_interest`` rows vs the chain's OI (a missing quote null, never
0), the TOTAL row's net per-unit Entry / LTP, and Decay (its own BSM revaluation at its own next-open rule:
09:15 IST the next weekday; across a holiday the checker says "not checkable").
"""
from __future__ import annotations

import copy
import datetime as dt
import importlib.util
import pathlib
import sys
from decimal import Decimal

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("ui_data_check", ROOT / "scripts" / "checks" / "ui_data_check.py")
u = importlib.util.module_from_spec(_spec)
sys.modules["ui_data_check"] = u
_spec.loader.exec_module(u)

from ofo.outcome import build_outcome  # noqa: E402
from ofo.outcome.serialize import outcome_to_dict  # noqa: E402
from outcome._both_curves_cases import S54, as_json, definition, market, snapshot  # noqa: E402
from outcome.test_same_engine import VALUATION  # noqa: E402

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
FIX = ROOT / "tests" / "fixtures" / "ui_data_check"


@pytest.fixture(scope="module")
def real():
    provider = market()
    d = definition(provider, S54)
    snap = snapshot(provider, d)
    return as_json(outcome_to_dict(build_outcome(d, snap, VALUATION))), snap


def _verdicts(rep, part):
    return [f.verdict for f in rep.figures if part in f.name]


def test_checker_source_imports_nothing_from_ofo():
    text = (ROOT / "scripts" / "checks" / "ui_data_check.py").read_text(encoding="utf-8")
    assert "import ofo" not in text and "from ofo" not in text


@pytest.mark.parametrize(("at", "want"), [
    (dt.datetime(2026, 10, 8, 9, 20, 9, tzinfo=IST), dt.datetime(2026, 10, 9, 9, 15, tzinfo=IST)),  # Thu -> Fri
    (dt.datetime(2026, 10, 9, 16, 0, tzinfo=IST), dt.datetime(2026, 10, 12, 9, 15, tzinfo=IST)),  # Fri -> Mon
    (dt.datetime(2026, 10, 10, 11, 0, tzinfo=IST), dt.datetime(2026, 10, 12, 9, 15, tzinfo=IST)),  # Sat -> Mon
    (dt.datetime(2026, 10, 12, 8, 0, tzinfo=IST), dt.datetime(2026, 10, 12, 9, 15, tzinfo=IST)),  # Mon pre-open
])
def test_checker_next_open_rule_is_the_next_weekday_0915_ist(at, want):
    assert u.next_weekday_open(at) == want


def test_checker_decay_reproduces_the_engines_decay_per_leg_and_total(real):
    """The core: the checker's own formula, clock rule and time basis give the engine's Decay on a real reply."""
    reply, snap = real
    valuation = dt.datetime.fromisoformat(reply["valuation"])
    until = u.next_weekday_open(valuation)
    rows = {r["row_id"]: r["cells"] for r in reply["table"]["rows"]}
    total = 0.0
    for i, leg in enumerate(reply["legs"], start=1):
        fwd = snap.forwards[dt.date.fromisoformat(leg["expiry"])]
        s, q = float(reply["spot_level"]), float(fwd.implied_yield)
        t = u.years_to_expiry(valuation, leg["expiry"])
        unit = u.decay_per_unit(s, float(leg["strike"]), t, float(fwd.rate), q, float(leg["iv"]), leg["instrument"],
                                valuation, until)
        want = unit * leg["quantity"] * (1 if leg["action"] == "BUY" else -1)
        assert float(rows[str(i)]["decay"]["value"]) == pytest.approx(want, abs=0.0001 * leg["quantity"])
        total += want
    assert float(rows["TOTAL"]["decay"]["value"]) == pytest.approx(total, abs=0.0002 * len(reply["legs"]) * 65)


def test_check_outcome_flags_a_wrong_decay_and_matches_the_right_one():
    est, atx, before, after, fut = u.load_replay(FIX)
    first = u.check_outcome("t", est, atx, before, after, fut)
    ours = {f.name: f for f in first.figures if "decay" in f.name and f.name.startswith("leg")}
    assert ours and all(f.verdict == u.NOT_CHECKABLE for f in ours.values())  # recorded before D-B34: no cell
    good, bad = copy.deepcopy(est), copy.deepcopy(est)
    for row in good["table"]["rows"] + bad["table"]["rows"]:
        if row["row_id"] == "TOTAL":
            continue
        fig = next(f for n, f in ours.items() if n.startswith(f"leg{row['row_id']} "))
        row["cells"]["decay"] = {"value": fig.independent}
    for row in bad["table"]["rows"]:
        if row["row_id"] == "2":
            row["cells"]["decay"]["value"] = str(-Decimal(row["cells"]["decay"]["value"]))  # a SELL leg unsigned
    assert set(_verdicts(u.check_outcome("t", good, atx, before, after, fut), "leg")) >= {u.MATCH}
    assert u.MISMATCH in _verdicts(u.check_outcome("t", bad, atx, before, after, fut), "leg2 decay")


def test_check_outcome_marks_decay_not_checkable_across_a_holiday():
    est, atx, before, after, fut = u.load_replay(FIX)
    nxt = u.next_weekday_open(dt.datetime.fromisoformat(est["valuation"])).date()
    rep = u.check_outcome("t", est, atx, before, after, fut, holidays=(nxt,))
    notes = [f.note for f in rep.figures if "decay" in f.name]
    assert notes and all("exchange holiday" in n and "not checkable" in n for n in notes)


def test_total_net_per_unit_matches_a_real_reply_and_flags_a_tampered_one(real):
    reply, _snap = real
    rep = u.Report("t")
    u.check_total_net_per_unit(rep, "v", reply)
    assert [f.verdict for f in rep.figures] == [u.MATCH] * 4  # entry / ltp magnitude + side
    for column, field, value in (("entry_price", "value", "62.41"), ("ltp", "side", "Cr")):
        bad = copy.deepcopy(reply)
        next(r for r in bad["table"]["rows"] if r["row_id"] == "TOTAL")["cells"][column][field] = value
        rep = u.Report("t")
        u.check_total_net_per_unit(rep, "v", bad)
        assert u.MISMATCH in _verdicts(rep, column)


def test_total_net_per_unit_must_be_absent_with_unequal_quantities(real):
    reply, _snap = real
    bad = copy.deepcopy(reply)
    bad["legs"][0]["quantity"] = 130  # the reply still shows a per-unit figure: wrong
    rep = u.Report("t")
    u.check_total_net_per_unit(rep, "v", bad)
    assert _verdicts(rep, "entry_price") == [u.MISMATCH]


def _chain(rows, closed=False):
    return {"2026-10-13": {"market_closed": closed, "rows": rows}}


def _side(oi, health="available"):
    return {"oi": oi, "health": health}


def _oi_reply(rows, available=True):
    return {"open_interest": {"available": available, "unavailable_reason": None if available else "x",
                              "expiry": "2026-10-13", "rows": rows}}


CHAIN = _chain([{"strike": "22600.00", "ce": _side(100), "pe": _side(0)},
                {"strike": "22650.00", "ce": None, "pe": _side(7, health="stale")}])


def test_open_interest_rows_match_the_chain_and_a_missing_quote_is_null():
    rows = [{"strike": "22600", "call_oi": 100, "call_oi_display": "100", "put_oi": 0, "put_oi_display": "0"},
            {"strike": "22650", "call_oi": None, "call_oi_display": u.DASH, "put_oi": None, "put_oi_display": u.DASH}]
    rep = u.Report("t")
    u.check_open_interest(rep, "v", _oi_reply(rows), CHAIN, {})
    assert {f.verdict for f in rep.figures} == {u.MATCH} and len(rep.figures) == 6  # noqa: PLR2004


@pytest.mark.parametrize(("strike", "key", "value"), [
    ("22650", "call_oi", 0),  # a missing quote shown as 0 (round 3's M2)
    ("22650", "put_oi", 7),  # a stale in-hours quote's OI shown as live
    ("22600", "call_oi", 101),  # a wrong count
])
def test_open_interest_flags_a_zero_in_a_missing_place_and_a_wrong_count(strike, key, value):
    rows = [{"strike": "22600", "call_oi": 100, "call_oi_display": "100", "put_oi": 0, "put_oi_display": "0"},
            {"strike": "22650", "call_oi": None, "call_oi_display": u.DASH, "put_oi": None, "put_oi_display": u.DASH}]
    next(r for r in rows if r["strike"] == strike)[key] = value
    rep = u.Report("t")
    u.check_open_interest(rep, "v", _oi_reply(rows), CHAIN, {})
    assert u.MISMATCH in _verdicts(rep, f"{strike} {'CE' if key == 'call_oi' else 'PE'}")


def test_an_unavailable_oi_block_must_have_no_rows_and_flag_off_adds_nothing():
    rep = u.Report("t")
    u.check_open_interest(rep, "v", _oi_reply([{"strike": "22600", "call_oi": 0}], available=False), CHAIN, {})
    assert _verdicts(rep, "no rows") == [u.MISMATCH]
    rep = u.Report("t")
    u.check_open_interest(rep, "v", {}, CHAIN, {})
    assert rep.figures == []


def test_total_per_unit_greeks_match_a_real_reply_and_flag_tampered_or_partial_ones(real):
    """GC-UI T-1: the checker's own weighted sum of the legs' per units equals the TOTAL row's; a tampered total, a
    SELL leg negated twice and a partial total (a leg without a figure but a total with one) are each flagged."""
    reply, _snap = real

    def run(r):
        rep = u.Report("t")
        assert u.check_total_per_unit_greeks(rep, "estimated_now", r) == 5  # noqa: PLR2004 - literal is the pinned value
        return rep

    good = run(reply)
    assert _verdicts(good, "total delta per unit") and set(_verdicts(good, "per unit")) == {u.MATCH}
    bad = copy.deepcopy(reply)
    total = next(r["cells"] for r in bad["table"]["rows"] if r["row_id"] == "TOTAL")
    total["delta"]["per_unit"] = str(Decimal(total["delta"]["per_unit"]) + Decimal("0.01"))
    assert u.MISMATCH in _verdicts(run(bad), "total delta per unit")
    partial = copy.deepcopy(reply)
    leg1 = next(r["cells"] for r in partial["table"]["rows"] if r["row_id"] == "1")
    leg1["vega"]["per_unit"] = None  # the total still shows a figure: a partial sum
    assert u.MISMATCH in _verdicts(run(partial), "total vega per unit")
