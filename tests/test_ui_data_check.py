# ruff: noqa: PLR2004, PLR0913 - reference numbers (Hull, hand-computed charges) are the point of the asserts
"""Tests for the independent UI data checker (GC-UI step 1). One test per acceptance item of the brief."""

from __future__ import annotations

import ast
import copy
import datetime as dt
import importlib.util
import json
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


def is_display_row(name):
    return "display" in name and "= per_unit" not in name


def exact_counts(rep):
    """Counts without the display-string rows: the older recorded fixtures predate the server's display keys."""
    c = {u.MATCH: 0, u.MISMATCH: 0, u.NOT_CHECKABLE: 0}
    for f in rep.figures:
        if not is_display_row(f.name):
            c[f.verdict] += 1
    return c


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
    # C-3 (ADR-082 (1)): every part EXACT, GST on the EXACT brokerage + exchange + SEBI (a GST on rounded parts
    # would be 18% x 93.94 = 16.9092), total = exact sum 140.78603242 rounded up once
    legs = [leg("BUY", "CE", 22600, "194.40"), leg("SELL", "CE", 22800, "106.60")]
    c = u.round_trip_charges(legs)
    assert {k: Decimal(str(v)) for k, v in c.items()} == {
        "brokerage": Decimal("80"),
        "stt": Decimal("29.3475"),
        "exchange_transaction": Decimal("13.902889"),
        "gst": Decimal("16.90956342"),
        "stamp": Decimal("0.58695"),
        "sebi": Decimal("0.03913"),
        "exact_total": Decimal("140.78603242"),
        "total": Decimal("140.79"),
    }


def test_c3_charges_total_is_rounded_up_not_half_up():
    """C-3: run1 credit iron condor (2026-10-28 11:29 IST): exact 263.140937008 -> the server's 263.15 (ROUND_UP,
    ADR-082 "rounded up"); half-up would give 263.14 and the old rounded-parts sum gave 263.13."""
    legs = [
        leg("BUY", "PE", 22500, "92.25"),
        leg("SELL", "PE", 22600, "123.65"),
        leg("SELL", "CE", 22800, "155.20"),
        leg("BUY", "CE", 22900, "111.30"),
    ]
    c = u.round_trip_charges(legs)
    assert c["exact_total"] == Decimal("263.140937008")
    assert str(c["total"]) == "263.15"


def _condor_reply_cb():
    """The run1 condor's charges block exactly as the server replied (parts half-even, total rounded up)."""
    return {
        "brokerage": "160.00",
        "stt": "47.03",
        "exchange_transaction": "22.28",
        "gst": "32.82",
        "stamp": "0.94",
        "sebi": "0.06",
        "total": "263.15",
    }


def test_c3_condor_shown_parts_match_and_a_changed_part_is_flagged():
    est, atx, b, a, f = fixture()
    est = copy.deepcopy(est)
    ref = est["legs"][0]
    est["legs"] = [
        dict(ref, **x)
        for x in (
            {"action": "BUY", "instrument": "PE", "strike": "22500.00", "planned_entry": "92.25"},
            {"action": "SELL", "instrument": "PE", "strike": "22600.00", "planned_entry": "123.65"},
            {"action": "SELL", "instrument": "CE", "strike": "22800.00", "planned_entry": "155.20"},
            {"action": "BUY", "instrument": "CE", "strike": "22900.00", "planned_entry": "111.30"},
        )
    ]
    est["charges_breakdown"] = dict(est["charges_breakdown"], **_condor_reply_cb())
    figs = {x.name: x for x in run(est, atx, b, a, f).figures}
    names = [f"charges {k}" for k in u.CHARGE_PARTS] + [
        "charges total",
        "charges total = sum of the reply's own shown components",
    ]
    assert {n: figs[n].verdict for n in names} == dict.fromkeys(names, u.MATCH)
    for part in (*u.CHARGE_PARTS, "total"):
        est2 = copy.deepcopy(est)
        est2["charges_breakdown"][part] = str(Decimal(est2["charges_breakdown"][part]) + Decimal("0.01"))
        figs2 = {x.name: x for x in run(est2, atx, b, a, f).figures}
        assert figs2[f"charges {part}"].verdict == u.MISMATCH, part


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


def test_c1_credit_strategy_total_pnl_percent_is_on_max_loss_not_net_entry():
    """C-1 mutant killer: on a debit spread net entry == max loss, so the two bases agree. Flip s54's actions: a
    credit spread with net credit 5,707.00 and pre-charges max loss 200 x 65 - 5,707 = 7,293.00 (differ)."""
    est, atx, b, a, f = fixture()
    est = copy.deepcopy(est)
    for lg in est["legs"]:
        lg["action"] = "SELL" if lg["action"] == "BUY" else "BUY"
    figs = {x.name: x for x in run(est, atx, b, a, f).figures}
    tot = figs["[estimated_now] total pnl_percent"]
    pnl = Decimal(figs["[estimated_now] total unrealized_pnl"].independent)
    dp = len(str(tot.ours).split(".")[1]) if tot.ours and "." in str(tot.ours) else 0
    q_ = Decimal(1).scaleb(-dp)
    on_max_loss = (pnl / Decimal("7293.00") * 100).quantize(q_, rounding="ROUND_HALF_UP")
    on_net_entry = (pnl / Decimal("5707.00") * 100).quantize(q_, rounding="ROUND_HALF_UP")
    assert on_max_loss != on_net_entry  # the case discriminates
    assert tot.independent == str(on_max_loss)


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
    c = exact_counts(rep)
    assert c[u.MISMATCH] == 0, [f for f in rep.figures if f.verdict == u.MISMATCH and not is_display_row(f.name)]
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
    if label == "charges stt":  # the sum-of-shown-parts check has a 0.04 tolerance (ADR-082 (1)), may not move
        assert changed - {"charges total = sum of the reply's own shown components"} == allowed
    else:
        assert changed == allowed


def test_tamper_expiry_payoff_point_flagged():
    est, atx, b, a, f = fixture()
    atx2 = copy.deepcopy(atx)
    p = atx2["payoff"]["points"][3]
    p["pnl"] = str(Decimal(p["pnl"]) - Decimal("0.01"))
    tam = verdicts(run(est, atx2, b, a, f))
    assert tam[f"[at_expiry] payoff @{p['level']}"] == u.MISMATCH
    assert sum(v == u.MISMATCH for k, v in tam.items() if not is_display_row(k)) == 1


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
    assert exact_counts(rep)[u.MISMATCH] == 0


# ---------------------------------------------------------------- GC-UI F-2: per unit carries the leg sign


def _s54_old_reply():
    return json.loads((FIX / "s54_estimated_now_table_unsigned.json").read_text(encoding="utf-8"))


def _sign_check(reply):
    rep = u.Report("t")
    u.check_per_unit_signs(rep, "estimated_now", reply)
    return rep


def _signed_copy(reply):
    """What the fixed server sends: SELL rows have per_unit and per_unit_display negated."""
    fixed = copy.deepcopy(reply)
    for row in fixed["table"]["rows"]:
        if (row["cells"].get("action") or {}).get("value") == "SELL":
            for gk in u.GREEK_KEYS:
                cell = row["cells"][gk]
                if cell.get("per_unit") is not None:
                    cell["per_unit"] = str(-Decimal(cell["per_unit"]))
                    shown = cell["per_unit_display"]
                    cell["per_unit_display"] = shown[1:] if shown.startswith("-") else "-" + shown
    return fixed


def test_f2_recorded_unsigned_s54_reply_flags_every_sell_greek_and_buy_legs_pass():
    rep = _sign_check(_s54_old_reply())
    bad = [f.name for f in rep.figures if f.verdict == u.MISMATCH]
    assert len(bad) == 4, bad  # the 4 Greeks of SELL leg 2 (per_unit_display agrees with the old unsigned per_unit)
    assert all("leg2" in n for n in bad)
    assert not [f for f in rep.figures if "leg1" in f.name and f.verdict != u.MATCH]


def test_f2_signed_s54_reply_passes():
    rep = _sign_check(_signed_copy(_s54_old_reply()))
    assert rep.counts()[u.MISMATCH] == 0
    assert rep.counts()[u.MATCH] == 16


def test_f2_total_row_and_null_per_unit_are_not_compared():
    reply = _signed_copy(_s54_old_reply())
    reply["table"]["rows"][1]["cells"]["delta"]["per_unit"] = None
    rep = _sign_check(reply)
    assert not [f for f in rep.figures if "TOTAL" in f.name or "leg2 delta" in f.name]


# ---------------------------------------------------------------- display strings (GC-UI checker, REQ-152/153/145)

M = "\N{MINUS SIGN}"  # U+2212, the server's minus on summary money and breakevens
DISP = FIX / "display_s54"  # REAL live s54 reply, funds redacted; summary display keys as the HEAD serializer mints


def _disp():
    return u.load_replay(DISP)


def _disp_rows(rep):
    return {f.name: f for f in rep.figures if "display" in f.name}


def test_d1_real_reply_has_a_verdict_row_for_every_display_string_and_all_match():
    est, atx, before, after, fut = _disp()
    rep = run(est, atx, before, after, fut)
    rows = _disp_rows(rep)
    assert rows["[estimated_now] summary.max_profit_display"].ours == "+7,152"
    assert rows["[estimated_now] summary.max_profit_display"].independent == "+7,152"
    for name in (
        "summary.max_loss_display",
        "summary.time_value_display",
        "summary.intrinsic_value_display",
        "summary.breakevens_display[0]",
        "summary.net_premium.amount_display",
        "margin.needed_display",
        "margin.broker_needed_display",
        "margin.available_display",
        "leg1 iv display",
        "leg1 delta display",
        "leg1 gamma per_unit_display",
        "TOTAL theta display",
    ):
        assert any(n.endswith(name) for n in rows), name
    bad = [f for f in rows.values() if f.verdict != u.MATCH]
    assert not bad, [(f.name, f.ours, f.independent) for f in bad]
    assert len(rows) >= 2 * 25  # per view: 4 summary + breakeven + net + 3 margin + 2 legs x 9 + 4 TOTAL greeks


def test_d2_one_character_changed_is_flagged_alone():
    est, atx, before, after, fut = _disp()
    base = verdicts(run(est, atx, before, after, fut))
    bad = copy.deepcopy(est)
    assert bad["summary"]["max_profit_display"] == "+7,152"
    bad["summary"]["max_profit_display"] = "+7,153"
    now = verdicts(run(bad, atx, before, after, fut))
    changed = {k for k in now if now[k] != base.get(k)}
    assert changed == {"[estimated_now] summary.max_profit_display"}
    assert now["[estimated_now] summary.max_profit_display"] == u.MISMATCH


@pytest.mark.parametrize(
    ("value", "signed", "text"),
    [
        ("7152.21", True, "+7,152"),
        ("-5847.79", True, M + "5,848"),
        ("189000", False, "1,89,000"),  # Indian grouping
        ("6024.50", True, "+6,025"),  # half-up, not half-even
        ("-104.50", True, M + "105"),
        ("0", True, "0"),  # a true zero: no sign
        ("-0.40", True, "0"),  # rounds to zero: no sign, no "-0"
        ("0.40", True, "0"),
        ("5707.00", False, "5,707"),
        ("12345678", True, "+1,23,45,678"),
    ],
)
def test_d3_whole_rupee_rule(value, signed, text):
    assert u.display_whole(Decimal(value), signed=signed) == text


@pytest.mark.parametrize(
    ("level", "spot", "text"),
    [
        ("22400", "22712", f"22,400 ({M}1.4%)"),
        ("23000", "22712", "23,000 (+1.3%)"),
        ("22687.8", "22698.85", f"22,688 ({M}0.0%)"),  # F-4: -0.0487% rounds to 0.0, the sign stays (REQ-153 AC-1)
        ("22700.4", "22698.85", "22,700 (+0.0%)"),  # F-4: +0.0068% likewise
        ("22698.85", "22698.85", "22,699 (0.0%)"),  # a true zero: no sign (REQ-152 AC-4)
        ("20010", "20000", "20,010 (+0.1%)"),  # exactly 0.05: half-up gives 0.1 (half-even would give 0.0)
        ("19990", "20000", f"19,990 ({M}0.1%)"),
        ("22688", None, "22,688"),  # no usable spot: the level alone
        ("22688", "0", "22,688"),
    ],
)
def test_d4_breakeven_rule(level, spot, text):
    assert u.display_breakeven(Decimal(level), None if spot is None else Decimal(spot)) == text


@pytest.mark.parametrize(
    ("kind", "value", "text"),
    [
        ("iv", "0.183667", "18.37%"),  # REQ-145 AC-3
        ("iv", "0.160347", "16.03%"),
        ("iv", "0.14765", "14.77%"),  # tie at the 3rd dp: half-up
        ("delta", "40.0974", "40.10"),
        ("delta", "-28.0536", "-28.05"),
        ("theta", "-0.0004", "0.00"),  # never "-0.00"
        ("gamma", "0.0580", "0.0580"),
        ("vega", "0.125", "0.13"),  # half-up
    ],
)
def test_d5_iv_and_greek_rule(kind, value, text):
    assert u.display_cell(kind, Decimal(value)) == text


def _verdict(shown, exact, expected):
    return u.check_text(u.Report("t"), "x", shown, exact, expected).verdict


def test_d6_answer_states():
    assert _verdict("+7,152", Decimal("7152.21"), "+7,152") == u.MATCH  # present
    assert _verdict(None, None, None) == u.MATCH  # null text, null exact
    assert _verdict("—", None, None) == u.MATCH  # the dash a cell prints for no value
    assert _verdict(None, Decimal("7152.21"), "+7,152") == u.MISMATCH  # text missing while the exact exists
    assert _verdict("+7,152", None, None) == u.MISMATCH  # text where there is no figure
    assert _verdict("0", Decimal("0"), "0") == u.MATCH  # zero
    assert _verdict("+0", Decimal("0"), "0") == u.MISMATCH  # zero with a sign


def test_d7_null_text_with_exact_present_is_flagged_in_a_reply():
    est, atx, before, after, fut = _disp()
    bad = copy.deepcopy(est)
    bad["summary"]["net_premium"]["amount_display"] = None
    bad["table"]["rows"][0]["cells"]["iv"]["display"] = None
    now = verdicts(run(bad, atx, before, after, fut))
    base = verdicts(run(est, atx, before, after, fut))
    assert {k for k in now if now[k] != base.get(k)} == {
        "[estimated_now] summary.net_premium.amount_display",
        "[estimated_now] leg1 iv display",
    }


def test_d8_per_unit_display_and_total_row_ties():
    est, atx, before, after, fut = _disp()
    bad = copy.deepcopy(est)
    bad["table"]["rows"][1]["cells"]["theta"]["per_unit_display"] = "15.73"  # exact 15.7355 shows 15.74
    now = verdicts(run(bad, atx, before, after, fut))
    assert now["[estimated_now] leg2 theta per_unit_display"] == u.MISMATCH
    # a 4 dp position value on the half step may be a rounding either side of the server's unrounded figure
    tie = copy.deepcopy(est)
    cell = tie["table"]["rows"][-1]["cells"]["delta"]
    cell["value"], cell["display"] = "12.0450", "12.04"
    ok = verdicts(run(tie, atx, before, after, fut))
    assert ok["[estimated_now] TOTAL delta display"] == u.MATCH


def test_d9_real_sensex_bull_put_spread_minus_zero_and_negative_value_all_match():
    est, atx, before, after, fut = u.load_replay(FIX / "display_sensex_bps")
    rows = _disp_rows(run(est, atx, before, after, fut))
    shown = {k: f.ours for k, f in rows.items() if k.startswith("[estimated_now] summary.")}
    assert shown["[estimated_now] summary.max_loss_display"] == M + "2,530"
    assert shown["[estimated_now] summary.intrinsic_value_display"] == "0"  # a true zero: no sign
    assert shown["[estimated_now] summary.time_value_display"] == M + "1,586"
    bad = [f.name for f in rows.values() if f.verdict != u.MATCH]
    assert not bad, bad


# ---------------------------------------------------------------- GC-UI C-4: the stated pricing basis after hours

# REAL reply 17:13 IST after the close: "estimated from spot", every quote stale (funds redacted)
CLOSED = FIX / "closed_s54"


def _closed():
    return u.load_replay(CLOSED)


def _iv_rows(rep):
    return {f.name: f for f in rep.figures if " iv (" in f.name}


def test_f5_closed_old_server_reply_flags_exactly_the_stale_mid_ivs():
    """F-5 detection (replaces C-4's "every model figure matches"): the recorded 17:13 reply (the OLD server: IV from
    the stale mid at q = 0) now flags both IV rows - ours is the closing-price (LTP) IV - and nothing else among the
    non-display figures (the Greeks and Estimated Now are priced with the reply's own IV, so they still match); the
    stated pricing basis (spot fallback) still matches."""
    est, atx, before, after, fut = _closed()
    rep = run(est, atx, before, after, fut)
    bad = [f.name for f in rep.figures if f.verdict == u.MISMATCH and not is_display_row(f.name)]
    assert sorted(bad) == sorted(_iv_rows(rep)) and len(bad) == 2, bad
    used = rep.data_rows["D-B35/36 iv basis"]["leg1"]
    assert used["used"] == "ltp, q=0 (spot fallback)" and used["stated_basis"] == "SPOT_FALLBACK"
    assert used["reply_iv"] == "0.147800" and used["ours_mid_spot_q0"] == 0.1478  # the old figure = the stale mid
    assert len([f for f in rep.figures if f.verdict == u.MATCH]) > 100
    basis = [f for f in rep.figures if f.name.startswith("pricing basis")]
    assert basis and all(f.verdict == u.MATCH for f in basis)


def test_c4_an_altered_iv_is_still_flagged():
    est, atx, before, after, fut = _closed()
    est = copy.deepcopy(est)
    est["legs"][0]["iv"] = f"{float(est['legs'][0]['iv']) + 0.01:.6f}"
    v = verdicts(run(est, atx, before, after, fut))
    assert [k for k, x in v.items() if " iv (" in k and x == u.MISMATCH] and "leg1" in str(
        [k for k, x in v.items() if " iv (" in k and x == u.MISMATCH])


def test_c4_stated_parity_on_stale_quotes_is_flagged():
    est, atx, before, after, fut = _closed()
    after = {e: dict(c, greeks_basis="PARITY") for e, c in after.items()}
    est = dict(est, output_label=None)
    v = verdicts(run(est, atx, before, after, fut))
    assert any(k.startswith("pricing basis") and x == u.MISMATCH for k, x in v.items())


def test_c4_stated_spot_fallback_on_live_quotes_is_flagged():
    est, atx, before, after, fut = fixture()
    after = {e: dict(c, greeks_basis="SPOT_FALLBACK") for e, c in after.items()}
    v = verdicts(run(est, atx, before, after, fut))
    assert any(k.startswith("pricing basis") and x == u.MISMATCH for k, x in v.items())


def test_c4_live_reply_is_unchanged_mid_and_parity():
    est, atx, before, after, fut = fixture()
    rep = run(est, atx, before, after, fut)
    assert exact_counts(rep)[u.MISMATCH] == 0
    used = rep.data_rows["D-B35/36 iv basis"]["leg1"]["used"]
    assert used == "mid, parity q"
    assert all(f.verdict == u.MATCH for f in rep.figures if f.name.startswith("pricing basis"))


def _leg(ltp):
    return {"ltp": ltp}


@pytest.mark.parametrize(
    ("quote", "ltp", "expect"),
    [
        ({"bid": "10", "ask": "12", "health": "available"}, "11.5", (11.0, "mid")),  # both sides live: mid
        ({"bid": "10", "ask": None, "health": "available"}, "11.5", (11.5, "ltp")),  # one side live: the LTP
        ({"bid": None, "ask": "12", "health": "available"}, "11.5", (11.5, "ltp")),
        ({"bid": "10", "ask": "12", "health": "stale"}, "11.5", (11.5, "ltp")),  # F-5: a stale book is no live side
        ({"bid": "10", "ask": "12", "health": "delayed"}, "11.5", (11.5, "ltp")),
        ({"bid": "10", "ask": "12", "health": "stale"}, None, (None, None)),  # stale book, no LTP: not checkable
        ({"bid": "0", "ask": "12", "health": "available"}, "11.5", (11.5, "ltp")),  # a 0 side is no live side
        ({"bid": "0", "ask": "0", "health": "stale"}, "11.5", (11.5, "ltp")),  # none live: the LTP
        ({"bid": "12", "ask": "10", "health": "available"}, "11.5", (11.5, "ltp")),  # crossed: the LTP
        ({"bid": "0", "ask": "0", "health": "stale"}, None, (None, None)),  # no LTP, nothing live: not checkable
        ({"bid": "10", "ask": "12", "health": "available"}, None, (11.0, "mid")),
        ({}, "11.5", (11.5, "ltp")),
        ({"bid": "10", "ask": "12"}, "11.5", (11.0, "mid")),  # no health key: an old reply, treated as live
    ],
)
def test_c4_iv_price_answer_states(quote, ltp, expect):
    assert u.iv_price(_leg(ltp), quote) == expect


def test_c4_no_live_side_and_no_ltp_makes_the_iv_not_checkable():
    est, atx, before, after, fut = _closed()
    est = copy.deepcopy(est)
    est["legs"][0]["ltp"] = None
    est["leg_quotes"][0]["bid"] = "0"
    v = verdicts(run(est, atx, before, after, fut))
    iv1 = [x for k, x in v.items() if " iv (" in k and k.startswith("leg1")]
    assert iv1 == [u.NOT_CHECKABLE]


def test_c4_f4_old_server_text_is_flagged_on_the_real_closed_reply():
    est, atx, before, after, fut = _closed()
    rep = run(est, atx, before, after, fut)
    row = _disp_rows(rep)["[estimated_now] summary.breakevens_display[0]"]
    assert row.verdict == u.MISMATCH and row.independent == f"22,688 ({M}0.0%)"


# ---------------------------------------------------------------- GC-UI step 4: second curve, payoff table, SD block
# Fixtures: strategy 54's shape on the real recorded 2026-10-08 NIFTY replay, asked through this tree's app in-process
# (two single views + one call with both_views, sd_bands and payoff_step 50 / absent). No database: no charge rates,
# so the summary's max profit / loss differ by the charges (an artefact of the no-database run, not a new figure).

BOTH = FIX / "both_s54_replay"
BOTH_DEFAULT = FIX / "both_s54_replay_default"


def _both(d=BOTH):
    est, atx, before, after, fut = u.load_replay(d)
    both, step = u.load_both(d)
    return est, atx, before, after, fut, both, step


def _run_both(est, atx, before, after, fut, both, step):
    return u.check_outcome("t", est, atx, before, after, fut, both=both, step_asked=step)


def _both_rows(rep):
    return {f.name: f for f in rep.figures if f.name.startswith("[both]")}


@pytest.mark.parametrize("d", [BOTH, BOTH_DEFAULT])
def test_s4_real_reply_every_new_figure_matches(d):
    rep = _run_both(*_both(d))
    rows = _both_rows(rep)
    assert len(rows) > 100
    assert {f.verdict for f in rows.values()} == {u.MATCH}, [f for f in rows.values() if f.verdict != u.MATCH][:3]
    model = [k for k in rows if k.startswith("[both] payoff_table estimated_now @")]
    assert len(model) == len(_both(d)[5]["payoff_table"]["rows"])  # every Estimated Now cell re-priced by own BSM
    for key in ("[both] SD 1 move", "[both] SD bands", "[both] curves.estimated_now = the estimated_now single-view "
                "points", "[both] curves on the same levels", "[both] payoff_table levels"):
        assert key in rows


def test_s4_default_step_is_the_strike_step_and_the_admin_step_is_flagged():
    """REQ-137 AC-1: absent payoff_step -> NIFTY 50; a reply at the Admin step (100, round 1) is flagged."""
    est, atx, before, after, fut, both, step = _both(BOTH_DEFAULT)
    assert step is None and both["payoff_table"]["step"] == "50"
    bad = copy.deepcopy(both)
    bad["payoff_table"]["step"] = "100"
    bad["payoff_table"]["rows"] = bad["payoff_table"]["rows"][::2]
    rows = _both_rows(_run_both(est, atx, before, after, fut, bad, None))
    assert rows["[both] payoff_table step (asked, else the strike step)"].verdict == u.MISMATCH
    assert rows["[both] payoff_table levels"].verdict == u.MISMATCH


def _tampered(change):
    est, atx, before, after, fut, both, step = _both()
    both = copy.deepcopy(both)
    change(both)
    return {k: f.verdict for k, f in _both_rows(_run_both(est, atx, before, after, fut, both, step)).items()}


def _bump(cell, key="pnl", by="0.01"):
    cell[key] = f"{Decimal(cell[key]) + Decimal(by):f}"


@pytest.mark.parametrize(
    ("change", "flagged"),
    [
        (lambda b: _bump(b["curves"]["estimated_now"]["points"][3]),
         "[both] curves.estimated_now = the estimated_now single-view points"),
        (lambda b: _bump(b["curves"]["at_expiry"]["points"][3]), "[both] curves.at_expiry @21800"),
        (lambda b: _bump(b["curves"]["estimated_now"]["points"][0], "level", "50"), "[both] curves on the same levels"),
        (lambda b: _bump(b["payoff_table"]["rows"][5]["at_expiry"]), "[both] payoff_table at_expiry @21750"),
        (lambda b: _bump(b["payoff_table"]["rows"][7]["estimated_now"], by="5"),
         "[both] payoff_table estimated_now @21850"),
        (lambda b: b["payoff_table"]["rows"][0].update(nearest_spot=True), "[both] payoff_table nearest_spot row"),
        (lambda b: _bump(b["standard_deviation"]["rows"][0], "move", "0.1"), "[both] SD 1 move"),
        (lambda b: _bump(b["standard_deviation"]["rows"][1], "upper", "0.1"), "[both] SD 2 upper"),
        (lambda b: b["standard_deviation"].update(horizon_days=7), "[both] standard_deviation horizon_days"),
        (lambda b: _bump(b["standard_deviation"]["bands"][0], "level", "0.1"), "[both] SD bands"),
        (lambda b: b["payoff_table"]["rows"][2]["at_expiry"].update(display="₹1.00"),
         "[both] payoff_table at_expiry display @21600"),
        (lambda b: b["standard_deviation"]["rows"][0].update(move_display="329.4 (1.4%)"),
         "[both] SD 1 move_display"),
    ],
)
def test_s4_one_altered_new_figure_is_flagged(change, flagged):
    v = _tampered(change)
    assert v[flagged] == u.MISMATCH
    # the altered figure, and at most its own list compare and its display row: never a spray of other rows
    assert sum(1 for x in v.values() if x == u.MISMATCH) <= 3, [k for k, x in v.items() if x == u.MISMATCH]


def test_s4_sd_from_252_days_is_flagged():
    """The trading-day basis (sqrt(days / 252)) instead of section 4's calendar days / 365 is a different figure."""
    est, atx, before, after, fut, both, step = _both()
    sd = copy.deepcopy(both)
    s = sd["standard_deviation"]
    spot, iv, days = Decimal(s["spot"]), Decimal(s["iv"]), s["horizon_days"]
    m = spot * iv * (Decimal(days) / Decimal(252)).sqrt()
    s["rows"][0]["move"] = f"{m.quantize(Decimal('0.1')):f}"
    assert _both_rows(_run_both(est, atx, before, after, fut, sd, step))["[both] SD 1 move"].verdict == u.MISMATCH


def test_s4_sd_rule_is_the_formula_written_out():
    rows = u.sd_rows(Decimal("22533.25"), Decimal("0.1249035"), 5)
    one = Decimal("22533.25") * Decimal("0.1249035") * (Decimal(5) / Decimal(365)).sqrt()
    assert rows[0]["move"] == one.quantize(Decimal("0.1")) and rows[1]["move"] == (2 * one).quantize(Decimal("0.1"))
    assert u.sd_horizon(dt.datetime(2026, 10, 8, 9, 20, tzinfo=u.IST), ["2026-10-19"]) == 7
    assert u.sd_horizon(dt.datetime(2026, 10, 8, 9, 20, tzinfo=u.IST), ["2026-10-13", "2026-10-19"]) == 5
    assert u.sd_horizon(dt.datetime(2026, 10, 13, 15, 0, tzinfo=u.IST), ["2026-10-13"]) == 1


@pytest.mark.parametrize(("value", "text"), [(Decimal("-4056"), "\N{MINUS SIGN}₹4,056.00"), (Decimal("8944"), "₹8,944.00"),
                                             (Decimal("0"), "₹0.00"), (Decimal("123456.785"), "₹1,23,456.79")])
def test_s4_rupee_cell_rule(value, text):
    assert u.display_rupees(value) == text


def test_s4_answer_states():
    est, atx, before, after, fut, both, step = _both()
    # flags off: no both reply -> no new figure rows at all (today's report unchanged)
    assert not _both_rows(u.check_outcome("t", est, atx, before, after, fut))
    # SD without IV / spot: unavailable with a reason and no rows is a match; rows shown anyway is a mismatch
    off = copy.deepcopy(both)
    off["standard_deviation"] = {"available": False, "reason": "x", "horizon_days": None, "iv": None, "spot": None,
                                 "rows": [], "bands": []}
    r = _both_rows(_run_both(est, atx, before, after, fut, off, step))
    assert r["[both] standard_deviation unavailable has a reason and no rows"].verdict == u.MATCH
    off["standard_deviation"]["rows"] = both["standard_deviation"]["rows"]
    r = _both_rows(_run_both(est, atx, before, after, fut, off, step))
    assert r["[both] standard_deviation unavailable has a reason and no rows"].verdict == u.MISMATCH
    # Estimated Now unavailable (no live prices) / calendar At Expiry (ADR-143): an empty column is a match, a value
    # in an unavailable column is a mismatch; the unavailable curve is not checkable, never matched
    for view in ("estimated_now", "at_expiry"):
        un = copy.deepcopy(both)
        next(c for c in un["payoff_table"]["columns"] if c["view"] == view).update(available=False,
                                                                                   unavailable_reason="x")
        un["curves"][view]["available"] = False
        for row in un["payoff_table"]["rows"]:
            row[view] = None
        r = _both_rows(_run_both(est, atx, before, after, fut, un, step))
        assert r[f"[both] curves.{view}"].verdict == u.NOT_CHECKABLE
        empty = [f for k, f in r.items() if k.endswith("empty (column unavailable)")]
        assert empty and {f.verdict for f in empty} == {u.MATCH}
        un["payoff_table"]["rows"][0][view] = both["payoff_table"]["rows"][0][view]
        r = _both_rows(_run_both(est, atx, before, after, fut, un, step))
        assert r[f"[both] payoff_table {view} @21500 empty (column unavailable)"].verdict == u.MISMATCH
    # a both reply that is not computed: one not-checkable row, never a match
    r = _both_rows(_run_both(est, atx, before, after, fut, {"state": "REFUSED", "reason": "r"}, step))
    assert [f.verdict for f in r.values()] == [u.NOT_CHECKABLE]


# ---------------------------------------------------------------- GC-UI D-B48: per-leg paper P&L (independent rule)


def paper_reply():
    """Strategy 54's recorded tracking reply (2026-10-28): BUY 22600 CE 193.70 -> 271.45, SELL 22800 CE 106.35 ->
    156.90, 65 a leg; by hand +5053.75 and -3285.75, total 1768.00."""
    base = {"quantity": 65, "exit_price": None, "pnl_kind": "unbooked"}
    return {
        "strategy_id": 54,
        "state": "LIVE",
        "paper_pnl": "1768.00",
        "booked": "0.00",
        "unbooked": "1768.00",
        "legs": [
            base | {"action": "BUY", "entry_price": "193.70", "current_price": "271.45", "pnl": "5053.75",
                    "pnl_text": "+5,053.75"},
            base | {"action": "SELL", "entry_price": "106.35", "current_price": "156.90", "pnl": "-3285.75",
                    "pnl_text": "−3,285.75"},
        ],
    }


def test_paper_leg_pnl_recorded_reply_matches():
    rep = u.check_paper(paper_reply(), [])
    assert rep.counts()[u.MISMATCH] == 0
    assert verdicts(rep)["paper leg1 pnl"] == u.MATCH and verdicts(rep)["paper leg2 pnl"] == u.MATCH


@pytest.mark.parametrize(("leg_no", "wrong"), [(1, "5053.76"), (2, "3285.75"), (2, "-3285.76")])
def test_paper_leg_pnl_tamper_is_flagged(leg_no, wrong):
    reply = paper_reply()
    reply["legs"][leg_no - 1]["pnl"] = wrong
    assert verdicts(u.check_paper(reply, []))[f"paper leg{leg_no} pnl"] == u.MISMATCH


def test_paper_leg_pnl_missing_never_matches():
    reply = paper_reply()
    del reply["legs"][0]["pnl"]
    assert verdicts(u.check_paper(reply, []))["paper leg1 pnl"] != u.MATCH


def test_paper_leg_pnl_exited_leg_is_valued_at_its_exit_price_and_must_say_booked():
    reply = paper_reply()
    reply["legs"][0] |= {"exit_price": "280.00", "pnl": "5609.50", "pnl_text": "+5,609.50", "pnl_kind": "booked", "current_price": None}
    reply |= {"paper_pnl": "2323.75", "booked": "5609.50", "unbooked": "-3285.75"}
    assert u.check_paper(reply, []).counts()[u.MISMATCH] == 0
    reply["legs"][0]["pnl_kind"] = "unbooked"
    assert verdicts(u.check_paper(reply, []))["paper leg1 pnl kind"] == u.MISMATCH


@pytest.mark.parametrize(("leg_no", "wrong"), [
    (1, "+5,054"), (1, "+5,053.76"), (1, "5,053.75"), (2, "-3,285.75"), (2, "−3,285"), (2, "+3,285.75"),
])
def test_paper_leg_pnl_text_must_equal_the_figure_to_the_paisa(leg_no, wrong):
    reply = paper_reply()
    reply["legs"][leg_no - 1]["pnl_text"] = wrong
    assert verdicts(u.check_paper(reply, []))[f"paper leg{leg_no} pnl text"] == u.MISMATCH


def test_paper_leg_pnl_text_missing_never_matches():
    reply = paper_reply()
    del reply["legs"][0]["pnl_text"]
    assert verdicts(u.check_paper(reply, []))["paper leg1 pnl text"] != u.MATCH


def test_paper_leg_pnl_text_recorded_reply_matches():
    assert verdicts(u.check_paper(paper_reply(), []))["paper leg1 pnl text"] == u.MATCH
    assert verdicts(u.check_paper(paper_reply(), []))["paper leg2 pnl text"] == u.MATCH
