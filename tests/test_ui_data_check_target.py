"""GC-TP step 6c: the independent checker recomputes the what-if target (REQ-084 AC-4) with its own BSM.

The replies are REAL (captured from the real route by step 6b): `outcome-target.json` (22,500 at 2026-10-10 12:00)
and `outcome-target-expiry.json` (22,500 at expiry, 2026-10-13 15:30). Their legs, spot, IV and quotes are the inputs.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXDIR = ROOT / "frontend" / "tests" / "fixtures"
_spec = importlib.util.spec_from_file_location("ui_data_check_t", ROOT / "scripts" / "checks" / "ui_data_check.py")
u = importlib.util.module_from_spec(_spec)
sys.modules["ui_data_check_t"] = u
_spec.loader.exec_module(u)


def _load(name):
    return json.loads((FIXDIR / name).read_text(encoding="utf-8"))


def _verdicts(rep):
    return {f.name: f.verdict for f in rep.figures}


def test_real_target_reply_matches_every_figure():
    rep = u.check_target(_load("outcome-target.json"))
    v = _verdicts(rep)
    assert v["target P&L (open legs only)"] == u.MATCH
    assert v["target breakevens"] == u.MATCH
    for n in ("delta", "gamma", "theta", "vega"):
        assert v[f"target {n}"] == u.MATCH
    # no booked figure was given: the expected basis is open legs only, and no booked row is printed (ADR-209)
    assert "target P&L (open legs + booked)" not in v
    assert u.MISMATCH not in v.values()


def test_real_target_at_expiry_matches():
    rep = u.check_target(_load("outcome-target-expiry.json"))
    v = _verdicts(rep)
    assert v["target P&L (open legs only)"] == u.MATCH
    assert v["target breakevens"] == u.MATCH
    assert u.MISMATCH not in v.values()


def test_one_flipped_figure_is_exactly_that_mismatch():
    reply = copy.deepcopy(_load("outcome-target.json"))
    reply["target"]["pnl"]["value"] = "1297.85"
    v = _verdicts(u.check_target(reply))
    assert [k for k, x in v.items() if x == u.MISMATCH] == ["target P&L (open legs only)"]
    reply = copy.deepcopy(_load("outcome-target.json"))
    reply["target"]["greeks"]["total"]["vega"] = "-300.0000"
    v = _verdicts(u.check_target(reply))
    assert [k for k, x in v.items() if x == u.MISMATCH] == ["target vega"]
    reply = copy.deepcopy(_load("outcome-target.json"))
    reply["target"]["breakevens"][1] = "22850.00"
    v = _verdicts(u.check_target(reply))
    assert [k for k, x in v.items() if x == u.MISMATCH] == ["target breakevens"]


def test_reply_without_target_figures_is_not_checkable():
    for name in ("outcome-target-plain.json", "outcome-condor.json"):
        rep = u.check_target(_load(name))
        assert [f.verdict for f in rep.figures] == [u.NOT_CHECKABLE]
        assert rep.counts()[u.MATCH] == 0


def test_booked_is_the_expected_basis_when_given():
    """ADR-209: with --booked the reply must carry open legs + booked; the open-legs figure is only a note."""
    reply = _load("outcome-target.json")
    v = _verdicts(u.check_target(reply, booked="200"))
    assert "target P&L (open legs only)" not in v
    assert v["target P&L (open legs + booked)"] == u.MISMATCH  # the fixture's P&L is open legs only
    reply["target"]["pnl"]["value"] = "1297.85"  # = open legs 1,097.85 + booked 200
    v = _verdicts(u.check_target(reply, booked="200"))
    assert v["target P&L (open legs + booked)"] == u.MATCH


#: the model prices each leg to the paisa, so the curve moves in steps of up to 0.01 x quantity per leg (65 -> 0.65)
CURVE_STEP_RS = 1.0


def test_booked_shifts_the_breakeven_crossings():
    """The shifted crossings are where the open-legs curve equals -booked; shift 0 gives the plain crossings."""
    reply = _load("outcome-target.json")
    legs, tg = reply["legs"], reply["target"]
    qmap = u.target_q_by_expiry(reply, u.RISK_FREE_RATE)
    level, at = float(tg["level"]), u.dt.datetime.fromisoformat(tg["at"])
    plain = u.target_breakevens(legs, qmap, at, u.RISK_FREE_RATE, level * 0.5, level * 1.5)
    assert plain == u.target_breakevens(legs, qmap, at, u.RISK_FREE_RATE, level * 0.5, level * 1.5, shift=0.0)
    shifted = u.target_breakevens(legs, qmap, at, u.RISK_FREE_RATE, level * 0.5, level * 1.5, shift=200.0)
    assert shifted and shifted != plain
    for x in shifted:
        assert abs(float(u._target_model(legs, qmap, x, at, u.RISK_FREE_RATE)[0]) + 200.0) < CURVE_STEP_RS
