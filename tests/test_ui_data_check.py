# ruff: noqa: PLR2004, PLR0913 - reference numbers (Hull, hand-computed charges) are the point of the asserts
"""Tests for the independent UI data checker (GC-UI step 1). One test per acceptance item of the brief."""

from __future__ import annotations

import ast
import copy
import datetime as dt
import importlib.util
import math
import os
import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
# UI_DATA_CHECK_PATH points the suite at a scratch mutant copy (Tier A mutation run); unset = the real file
CHECKER = Path(os.environ.get("UI_DATA_CHECK_PATH") or ROOT / "scripts" / "checks" / "ui_data_check.py")
FIX = ROOT / "tests" / "fixtures" / "ui_data_check"

_spec = importlib.util.spec_from_file_location("ui_data_check", CHECKER)
u = importlib.util.module_from_spec(_spec)
sys.modules["ui_data_check"] = u
_spec.loader.exec_module(u)


def leg(action, kind, strike, entry, qty=65, expiry="2026-11-03"):
    return {
        "action": action,
        "instrument": kind,
        "strike": str(strike),
        "planned_entry": str(entry),
        "quantity": qty,
        "expiry": expiry,
    }


def fixture():
    est, atx, before, after, fut = u.load_replay(FIX)
    return est, atx, before, after, fut


def run(est, atx, before, after, fut):
    return u.check_outcome("t", est, atx, before, after, fut)


def verdicts(rep):
    return {f.name: f.verdict for f in rep.figures}


# ---------------------------------------------------------------- maths


def test_hull_reference():
    assert round(u.bsm_price(42, 40, 0.5, 0.10, 0.0, 0.20, "CE"), 2) == 4.76
    assert round(u.bsm_price(42, 40, 0.5, 0.10, 0.0, 0.20, "PE"), 2) == 0.81


def test_iv_round_trip():
    for kind in ("CE", "PE"):
        p = u.bsm_price(22700, 22800, 6 / 365, 0.065, 0.01, 0.1543, kind)
        assert abs(u.implied_vol(p, 22700, 22800, 6 / 365, 0.065, 0.01, kind) - 0.1543) < 1e-6
    assert u.implied_vol(0.0001, 22700, 20000, 6 / 365, 0.065, 0.0, "CE") is None  # below intrinsic: no IV


def test_greek_basis_theta_per_day_vega_per_vol_point():
    s, k, t, r, q, v = 22700.0, 22700.0, 6 / 365, 0.065, 0.0, 0.16
    g = u.bsm_greeks(s, k, t, r, q, v, "CE")
    h = 1e-6
    dprice_dt = (u.bsm_price(s, k, t - h, r, q, v, "CE") - u.bsm_price(s, k, t + h, r, q, v, "CE")) / (2 * h)
    assert abs(g["theta"] - dprice_dt / 365) < 1e-3
    dv = u.bsm_price(s, k, t, r, q, v + 0.01, "CE") - u.bsm_price(s, k, t, r, q, v, "CE")
    assert abs(g["vega"] - dv) < 0.05


def test_time_is_calendar_days_to_1530_ist():
    val = dt.datetime(2026, 10, 28, 15, 30, tzinfo=u.IST)
    # 28 Oct -> 3 Nov = 6 calendar days (4 trading days): calendar days / 365
    assert abs(u.years_to_expiry(val, "2026-11-03") - 6 / 365) < 1e-12


STRIKES = tuple(range(22200, 23250, 50))


def _synthetic_chain(spot, fwd, t, r, sigma=0.15, strikes=STRIKES, two_sided=True):
    rows = []
    s_eff = fwd * math.exp(-r * t)  # S e^{-qT}
    q = r - math.log(fwd / spot) / t
    for k in strikes:
        c = u.bsm_price(spot, k, t, r, q, sigma, "CE")
        p = u.bsm_price(spot, k, t, r, q, sigma, "PE")
        assert s_eff > 0
        rows.append(
            {
                "strike": f"{k}.00",
                "ce": {"bid": f"{c - 0.05:.4f}", "ask": f"{c + 0.05:.4f}"},
                "pe": {"bid": f"{p - 0.05:.4f}" if two_sided else None, "ask": f"{p + 0.05:.4f}"},
            }
        )
    return {"state": "LIVE", "spot": str(spot), "rows": rows}


def test_parity_forward_on_synthetic_chain():
    t, r = 6 / 365, 0.065
    ch = _synthetic_chain(22700.0, 22760.0, t, r)
    f, q, n, why = u.parity_forward(ch, t, r)
    assert why is None and n == 21
    assert abs(f - 22760.0) < 1e-3  # quotes carry 4 dp
    assert abs(q - (r - math.log(22760 / 22700) / t)) < 1e-5


def test_parity_impossible_falls_back_to_spot_and_says_so():
    t, r = 6 / 365, 0.065
    ch = _synthetic_chain(22700.0, 22760.0, t, r, two_sided=False)
    f, q, n, why = u.parity_forward(ch, t, r)
    assert n == 0 and q == 0.0 and "parity impossible" in why
    assert abs(f - 22700.0 * math.exp(r * t)) < 1e-6


# ---------------------------------------------------------------- payoff, breakevens, extremes


def test_breakeven_bull_call_spread():
    legs = [leg("BUY", "CE", 22600, "194.40"), leg("SELL", "CE", 22800, "106.60")]
    assert u.breakevens(legs) == [Decimal("22687.80")]
    mx, mn, pu, lu = u.extremes(legs)
    assert (mx, mn, pu, lu) == (Decimal("7293.00"), Decimal("-5707.00"), False, False)


def test_breakeven_iron_condor_two():
    legs = [
        leg("BUY", "PE", 22500, "60"),
        leg("SELL", "PE", 22600, "90"),
        leg("SELL", "CE", 22800, "100"),
        leg("BUY", "CE", 22900, "60"),
    ]
    # credit 70: BEs 22600-70 and 22800+70
    assert u.breakevens(legs) == [Decimal("22530.00"), Decimal("22870.00")]


def test_naked_short_call_unlimited_loss():
    legs = [leg("SELL", "CE", 22800, "106.60")]
    _mx, _mn, pu, lu = u.extremes(legs)
    assert lu is True and pu is False
    assert u.breakevens(legs) == [Decimal("22906.60")]


def test_charges_hand_example():
    # hand: turnover 2 x (12,636 + 6,929) = 39,130; brokerage 4 x 20; STT 0.15% x 19,565 = 29.3475;
    # exchange 0.03553% x 39,130 = 13.9029; SEBI 39,130 / 1e6 = 0.0391; stamp 0.003% x 19,565 = 0.5870;
    # GST 18% x (80 + 13.90 + 0.04) = 16.9092
    legs = [leg("BUY", "CE", 22600, "194.40"), leg("SELL", "CE", 22800, "106.60")]
    c = u.round_trip_charges(legs)
    assert {k: str(v) for k, v in c.items()} == {
        "brokerage": "80.00",
        "stt": "29.35",
        "exchange_transaction": "13.90",
        "gst": "16.91",
        "stamp": "0.59",
        "sebi": "0.04",
        "total": "140.79",
    }


def test_max_profit_and_loss_include_charges():
    est, atx, b, a, f = fixture()
    rep = run(est, atx, b, a, f)
    figs = {x.name: x for x in rep.figures}
    assert figs["max_profit (incl. charges)"].independent == "7152.21"  # 7,293.00 - 140.79
    assert figs["max_loss (incl. charges)"].independent == "5847.79"  # 5,707.00 + 140.79


def test_c1_total_pnl_percent_basis_is_unrealized_over_max_loss():
    """C-1: REQ-035 owner Q233: TOTAL P&L % = unrealized P&L / max loss; the leg rows keep unrealized / entry value."""
    est, atx, b, a, f = fixture()
    figs = {x.name: x for x in run(est, atx, b, a, f).figures}
    tot = figs["[estimated_now] total pnl_percent"]
    assert "max loss" in tot.note and "Q233" in tot.note
    pnl = Decimal(figs["[estimated_now] total unrealized_pnl"].independent)
    dp = len(str(tot.ours).split(".")[1]) if tot.ours and "." in str(tot.ours) else 0
    expected = (pnl / Decimal("5707.00") * 100).quantize(Decimal(1).scaleb(-dp), rounding="ROUND_HALF_UP")
    assert tot.independent == str(expected)  # 5,707.00 = the s54 spread's pre-charges max loss


def test_c2_margin_needed_is_not_checkable_never_matched():
    est, atx, b, a, f = fixture()
    figs = {x.name: x for x in run(est, atx, b, a, f).figures}
    if (est.get("margin") or {}).get("needed") is not None:
        assert figs["margin needed"].verdict == u.NOT_CHECKABLE and "option_premium" in figs["margin needed"].note
    else:
        assert "margin needed" not in figs


# ---------------------------------------------------------------- independence


def test_checker_imports_nothing_from_the_app():
    tree = ast.parse(CHECKER.read_text(encoding="utf-8"))
    bad = []
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        elif isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", "")) in (
            "import_module",
            "__import__",
        ):
            names = [getattr(a, "value", "") for a in node.args]
        bad += [n for n in names if str(n).split(".")[0] in ("ofo", "ofo_app", "backend")]
    assert bad == []
    assert "sys.path" not in CHECKER.read_text(encoding="utf-8")


# ---------------------------------------------------------------- real reply: baseline + tamper


def test_real_reply_baseline_all_match():
    rep = run(*fixture())
    c = rep.counts()
    assert c[u.MISMATCH] == 0, [f for f in rep.figures if f.verdict == u.MISMATCH]
    assert c[u.MATCH] > 100


@pytest.mark.parametrize(
    "path,label",
    [
        (("summary", "max_loss"), "max_loss (incl. charges)"),
        (("summary", "max_profit"), "max_profit (incl. charges)"),
        (("summary", "charges"), "summary charges"),
        (("summary", "net_premium", "amount"), "net_premium amount"),
        (("charges_breakdown", "stt"), "charges stt"),
    ],
)
def test_tamper_one_figure_by_one_paisa_is_flagged_alone(path, label):
    est, atx, b, a, f = fixture()
    est2 = copy.deepcopy(est)
    node = est2
    for p in path[:-1]:
        node = node[p]
    node[path[-1]] = str(Decimal(node[path[-1]]) + Decimal("0.01"))
    base, tam = verdicts(run(est, atx, b, a, f)), verdicts(run(est2, atx, b, a, f))
    changed = {k for k in base if base[k] != tam.get(k)}
    assert tam[label] == u.MISMATCH
    allowed = {label}
    if label == "charges stt":
        allowed.add("charges total = sum of the reply's own shown components")
    assert changed == allowed


def test_tamper_expiry_payoff_point_flagged():
    est, atx, b, a, f = fixture()
    atx2 = copy.deepcopy(atx)
    p = atx2["payoff"]["points"][3]
    p["pnl"] = str(Decimal(p["pnl"]) - Decimal("0.01"))
    tam = verdicts(run(est, atx2, b, a, f))
    assert tam[f"[at_expiry] payoff @{p['level']}"] == u.MISMATCH
    assert sum(v == u.MISMATCH for v in tam.values()) == 1


def test_estimated_now_uses_the_parity_q():
    """A synthetic chain with a large implied yield: the reply's points priced with that q must match; a checker
    that ignores q (prices at spot) would be ~11 index points off."""
    est, atx, _b, _a, f = fixture()
    est = copy.deepcopy(est)
    val = dt.datetime.fromisoformat(est["valuation"])
    t = u.years_to_expiry(val, "2026-11-03")
    r, spot = u.RISK_FREE_RATE, float(est["spot_level"])
    fwd = spot * math.exp((r - 0.03) * t)
    ch = _synthetic_chain(spot, fwd, t, r)
    ch["expiry"] = "2026-11-03"
    q = r - math.log(fwd / spot) / t
    for p in est["payoff"]["points"]:
        tot = Decimal(0)
        for lg in est["legs"]:
            px = u.money(u.bsm_price(float(p["level"]), float(lg["strike"]), t, r, q, float(lg["iv"]), "CE"))
            tot += (px - Decimal(lg["planned_entry"])) * lg["quantity"] * (1 if lg["action"] == "BUY" else -1)
        p["pnl"] = str(u.money(tot))
    rep = run(est, atx, {"2026-11-03": ch}, {"2026-11-03": ch}, f)
    pts = [x for x in rep.figures if x.name.startswith("[estimated_now] payoff")]
    assert pts and all(x.verdict == u.MATCH for x in pts), [x for x in pts if x.verdict != u.MATCH][:2]


# ---------------------------------------------------------------- answer states -> not checkable, never match


@pytest.mark.parametrize("state", ["FROM_ENTRIES", "NOT_CONNECTED", "REFUSED"])
def test_reply_state_not_computed(state):
    est, atx, b, a, f = fixture()
    est = dict(est, state=state)
    rep = run(est, atx, b, a, f)
    assert rep.figures and all(x.verdict == u.NOT_CHECKABLE for x in rep.figures)


def test_leg_ltp_null():
    est, atx, b, a, f = fixture()
    est = copy.deepcopy(est)
    est["legs"][0]["ltp"] = None
    v = verdicts(run(est, atx, b, a, f))
    assert v["[estimated_now] leg1 current_value"] == u.NOT_CHECKABLE
    assert v["[estimated_now] leg1 unrealized_pnl"] == u.NOT_CHECKABLE


def test_leg_iv_null():
    est, atx, b, a, f = fixture()
    est = copy.deepcopy(est)
    est["legs"][1]["iv"] = None
    rep = run(est, atx, b, a, f)
    v = verdicts(rep)
    assert v["leg2 iv"] == u.NOT_CHECKABLE
    assert v["[estimated_now] payoff points"] == u.NOT_CHECKABLE


def test_empty_payoff():
    est, atx, b, a, f = fixture()
    est, atx = copy.deepcopy(est), copy.deepcopy(atx)
    est["payoff"]["points"] = []
    atx["payoff"]["points"] = []
    v = verdicts(run(est, atx, b, a, f))
    assert v["[estimated_now] payoff points"] == u.NOT_CHECKABLE
    assert v["[at_expiry] payoff points"] == u.NOT_CHECKABLE


@pytest.mark.parametrize(
    "field,label",
    [
        ("max_loss", "max_loss (incl. charges)"),
        ("max_profit", "max_profit (incl. charges)"),
        ("charges", "summary charges"),
    ],
)
def test_summary_field_null_is_not_a_match(field, label):
    est, atx, b, a, f = fixture()
    est = copy.deepcopy(est)
    est["summary"][field] = None
    v = verdicts(run(est, atx, b, a, f))
    assert v[label] == u.NOT_CHECKABLE


def test_parity_impossible_reply_still_checked_and_labelled():
    est, atx, b, _a, f = fixture()
    dead = {e: dict(c, rows=[]) for e, c in b.items()}
    rep = run(est, atx, dead, dead, f)
    fw = rep.data_rows["forwards"]["2026-11-03"]
    assert "parity impossible" in fw["reason_before"]


def test_no_chain_for_an_expiry_makes_model_figures_not_checkable():
    est, atx, _b, _a, f = fixture()
    rep = run(est, atx, {}, {}, f)
    v = verdicts(rep)
    assert v["model figures (IV, Greeks, Estimated Now)"] == u.NOT_CHECKABLE
    assert rep.counts()[u.MISMATCH] == 0
