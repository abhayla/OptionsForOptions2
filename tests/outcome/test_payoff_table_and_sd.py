"""GC-UI step 4 server, items 2 and 3.

Item 2 (REQ-137 AC-1/AC-2, D-B24/D-B25): a payoff table at a user-picked interval of 10/25/50/100 index points with
both P&L columns (Estimated Now and At Expiry), each value from the one engine; absent -> the underlying's strike step
(REQ-137 AC-1: NIFTY 50, SENSEX 100). It is separate from the per-leg scenario table, which keeps its Admin step.

Item 3 (REQ-083 AC-4, REQ-137 AC-3, D-B19/D-B20/D-B45): the 1 SD / 2 SD block from the engine's spot, ATM IV and a
FIXED 7-day horizon (days to expiry when fewer), via the one expected-move formula (spot x IV x sqrt(days / 365));
absent with a reason when the ATM IV or the spot is missing. The expected values here are the formula written out
independently in Decimal, never a Sensibull number."""
from __future__ import annotations

import dataclasses
from decimal import ROUND_HALF_UP, Decimal, localcontext

import pytest
from ofo.errors.explanations import render_explanation
from ofo.outcome import StrategyDefinition, service
from ofo.outcome.serialize import outcome_to_dict
from ofo.scenario.levels import move_from_spot
from outcome._both_curves_cases import CALENDAR, S54, as_json, definition, entries_outcome, market, outcome, snapshot
from outcome.test_same_engine import VALUATION

TENTH = Decimal("0.1")
ONE_19OCT = (("NSE_FO:47139", service.Action.BUY),)  # 22600 CE 19-Oct: 11 days out, so the 7-day cap applies


@pytest.fixture(scope="module")
def provider():
    return market()


def _body(provider, legs=S54, **kw):
    return as_json(outcome_to_dict(outcome(provider, legs, **kw)))


# ---- item 2: payoff table ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("step", [10, 25, 50, 100])
def test_payoff_table_rows_at_the_picked_interval_with_both_columns_from_the_engine(provider, step):
    body = _body(provider, payoff_step=Decimal(step))
    table = body["payoff_table"]
    levels = [Decimal(r["level"]) for r in table["rows"]]
    assert table["step"] == str(step) and table["available"] is True
    assert all(b - a == step for a, b in zip(levels, levels[1:], strict=False))  # noqa: RUF007 - pairs of neighbours
    assert all(lvl % step == 0 for lvl in levels)
    scen = body["scenario"]
    assert Decimal(scen["start"]) <= levels[0] < Decimal(scen["start"]) + step and levels[-1] <= Decimal(scen["end"])
    spot = outcome(provider, S54).level_set.current
    nearest = min(levels, key=lambda x: (abs(x - spot), x))
    assert [r["nearest_spot"] for r in table["rows"]] == [lvl == nearest for lvl in levels]
    # every At Expiry cell is the exact formula; every Estimated Now cell equals the engine at that level
    for r in table["rows"]:
        lvl = Decimal(r["level"])
        assert Decimal(r["at_expiry"]["pnl"]) == _s54_expiry_pnl(provider, lvl), lvl
        assert r["at_expiry"]["display"] == render_explanation("cell_rupees", amount=Decimal(r["at_expiry"]["pnl"]))
        assert r["estimated_now"] is not None
    # the per-leg scenario table keeps its admin step and levels (separate view, REQ-137 AC-2)
    assert scen == _body(provider)["scenario"]
    assert [c["view"] for c in table["columns"]] == ["estimated_now", "at_expiry"]


def test_estimated_cells_equal_the_curve_values_at_shared_levels(provider):
    body = _body(provider, payoff_step=Decimal(100), both_views=True)
    curve = {p["level"]: p["pnl"] for p in body["curves"]["estimated_now"]["points"]}
    shared = [r for r in body["payoff_table"]["rows"] if r["level"] in curve]
    assert shared
    for r in shared:
        assert r["estimated_now"]["pnl"] == curve[r["level"]]


def _row_gaps(table):
    levels = [Decimal(r["level"]) for r in table["rows"]]
    return {b - a for a, b in zip(levels, levels[1:], strict=False)}  # noqa: RUF007 - pairs of neighbours


def test_payoff_table_absent_step_is_the_strike_step_and_only_with_an_option(provider):
    """REQ-137 AC-1: "default the underlying's strike step: NIFTY 50, SENSEX 100" - NOT the scenario grid's Admin step
    (ADR-042: NIFTY 100), which the per-leg table keeps (a different view)."""
    assert "payoff_table" not in _body(provider)
    body = _body(provider, both_views=True)
    table = body["payoff_table"]
    assert table["step"] == "50" and _row_gaps(table) == {Decimal(50)}
    assert outcome(provider, S54, both_views=True).level_set.step == Decimal(100)  # the grid keeps the Admin step
    fe = as_json(outcome_to_dict(entries_outcome(provider, S54, both_views=True)))["payoff_table"]
    assert fe["step"] == "50" and _row_gaps(fe) == {Decimal(50)}


def test_payoff_table_default_step_sensex_is_100():
    """REQ-137 AC-1 for SENSEX (strike step 100; the Admin grid step is 300). The SENSEX case of test_from_entries
    (78000 / 78300 strikes, lot 20, real catalogue rows with only the name, strike and lot changed)."""
    from outcome.test_from_entries import LOW, _spread, _stored  # noqa: PLC0415 - late import as its neighbours
    stored = {iid: dataclasses.replace(
        c, contract=dataclasses.replace(c.contract, name="SENSEX", lot_size=20,
                                        strike=c.contract.strike + (Decimal(55000) if iid == LOW else Decimal(55100))))
              for iid, c in _stored().items()}
    out = service.from_entries(StrategyDefinition("SENSEX", _spread().legs), None, stored, VALUATION, both_views=True)
    assert out.level_set.step == Decimal(300)  # the grid's Admin step is unchanged
    table = as_json(outcome_to_dict(out))["payoff_table"]
    assert table["step"] == "100" and _row_gaps(table) == {Decimal(100)} and len(table["rows"]) > 2  # noqa: PLR2004 - literal is the pinned value


def test_default_step_refuses_an_index_without_a_strike_step():
    with pytest.raises(ValueError, match="strike step"):
        service.payoff_table_default_step("BANKNIFTY")


@pytest.mark.parametrize("bad", [Decimal(30), Decimal(0), Decimal(-50), Decimal("50.5"), Decimal(300)])
def test_engine_refuses_a_step_outside_the_four(provider, bad):
    with pytest.raises(ValueError):
        outcome(provider, S54, payoff_step=bad)


def test_payoff_table_calendar_and_from_entries(provider):
    cal = _body(provider, CALENDAR, payoff_step=Decimal(50))["payoff_table"]
    atx = next(c for c in cal["columns"] if c["view"] == "at_expiry")
    assert atx["available"] is False and atx["unavailable_reason"] == render_explanation("mixed_expiry_worst_case")
    assert all(r["at_expiry"] is None and r["estimated_now"] is not None for r in cal["rows"])
    fe = as_json(outcome_to_dict(entries_outcome(provider, S54, payoff_step=Decimal(25))))["payoff_table"]
    est = next(c for c in fe["columns"] if c["view"] == "estimated_now")
    assert est["available"] is False and est["unavailable_reason"] == render_explanation(
        "outcome_from_entries_no_estimate")
    assert all(r["estimated_now"] is None and r["at_expiry"] is not None for r in fe["rows"])
    assert not any(r["nearest_spot"] for r in fe["rows"])  # no live index price: no row is "nearest spot"


def _s54_expiry_pnl(provider, level):
    """REQ-033 AC-1 written out: BUY 22600 CE, SELL 22800 CE, 65 each, at the replay LTP entries."""
    d = definition(provider, S54)
    buy, sell = d.legs
    return ((max(level - 22600, Decimal(0)) - buy.planned_entry) - (max(level - 22800, Decimal(0)) - sell.planned_entry)) * 65  # noqa: E501 - long line kept whole


# ---- item 3: SD block ----------------------------------------------------------------------------------------------

def _independent_sd(spot, iv, days):
    one = spot * iv * (Decimal(days) / Decimal(365)).sqrt()
    rows = []
    for n in (1, 2):
        m = one * n
        rows.append({"sd": n, "move": str(m.quantize(TENTH, ROUND_HALF_UP)),
                     "percent": str((m / spot * 100).quantize(TENTH, ROUND_HALF_UP)),
                     "lower": str((spot - m).quantize(TENTH, ROUND_HALF_UP)),
                     "upper": str((spot + m).quantize(TENTH, ROUND_HALF_UP))})
    return rows


@pytest.mark.parametrize(("legs", "days"), [(S54, 5), (ONE_19OCT, 7)])
def test_sd_block_is_the_expected_move_formula_on_a_fixed_7_day_horizon(provider, legs, days):
    """13-Oct is 5 days from 8-Oct (fewer than 7: days to expiry); 19-Oct is 11 days (capped at 7, D-B20)."""
    sd = _body(provider, legs, sd_bands=True)["standard_deviation"]
    d = definition(provider, legs)
    snap = snapshot(provider, d)
    expiry = min(c.contract.contract.expiry for c in snap.legs.values())
    iv = service.atm_iv(snap, expiry)
    spot = outcome(provider, legs).spot_level
    assert sd["available"] is True and sd["reason"] is None
    assert sd["horizon_days"] == days and Decimal(sd["iv"]) == iv and Decimal(sd["spot"]) == spot
    want = _independent_sd(spot, iv, days)
    assert [{k: r[k] for k in ("sd", "move", "percent", "lower", "upper")} for r in sd["rows"]] == want
    one, two = sd["rows"]
    assert one["move_display"] == f"{one['move']} ({one['percent']}%)" and one["label"] == "1SD"
    assert one["lower_display"] == one["lower"] and two["upper_display"] == two["upper"]
    # the bands are the table's own levels (one function), -2 / -1 / +1 / +2
    assert [(b["sd"], b["level"]) for b in sd["bands"]] == [(-2, two["lower"]), (-1, one["lower"]),
                                                            (1, one["upper"]), (2, two["upper"])]
    assert [b["label"] for b in sd["bands"]] == ["-2SD", "-1SD", "1SD", "2SD"]


def test_sd_absent_with_reason_when_no_atm_iv(provider, monkeypatch):
    monkeypatch.setattr(service, "atm_iv", lambda *a, **k: None)
    sd = _body(provider, sd_bands=True)["standard_deviation"]
    assert sd == {"available": False, "reason": render_explanation("sd_no_iv"), "horizon_days": None, "iv": None,
                  "spot": None, "rows": [], "bands": []}


def test_sd_absent_with_reason_when_no_spot(provider):
    sd = as_json(outcome_to_dict(entries_outcome(provider, S54, sd_bands=True)))["standard_deviation"]
    assert sd["available"] is False and sd["reason"] == render_explanation("sd_no_spot") and sd["rows"] == []


def test_sd_does_not_change_the_default_range(provider):
    """The range keeps its own expected move (days to expiry, rounded up): the SD option changes no other block."""
    on, off = _body(provider, sd_bands=True), _body(provider)
    on.pop("standard_deviation")
    assert on == off


# ---- D-B26 (REQ-137 AC-2 "Show %"): each row's move from spot in percent, computed by the server --------------------

def test_move_pct_is_the_acs_own_example():
    pct, display = move_from_spot(Decimal("23450"), Decimal("22966"))
    with localcontext(prec=50):
        assert pct == (Decimal("23450") - Decimal("22966")) * 100 / Decimal("22966")
    assert display == "+2.1%"  # REQ-137 AC-2's own example: 23,450 = +2.1%
    assert move_from_spot(Decimal("22966"), Decimal("22966")) == (Decimal(0), "0.0%")  # a true zero has no sign
    assert move_from_spot(Decimal("22500"), Decimal("22966"))[1] == "-2.0%"
    assert move_from_spot(Decimal("22965"), Decimal("22966"))[1] == "0.0%"  # rounds to zero: never "-0.0%"
    assert move_from_spot(Decimal("22500"), None) == (None, None)


def test_payoff_rows_carry_move_pct_from_the_same_spot(provider):
    body = _body(provider, payoff_step=Decimal(50))
    rows = body["payoff_table"]["rows"]
    spot = Decimal(body["spot_level"])
    for r in rows:
        with localcontext(prec=50):
            exact = (Decimal(r["level"]) - spot) * 100 / spot
        assert Decimal(r["move_pct"]) == exact
        shown = exact.quantize(TENTH, ROUND_HALF_UP)
        assert r["move_pct_display"] == ("0.0%" if shown == 0 else f"{shown:+}%")
    near = next(r for r in rows if r["nearest_spot"])
    assert abs(Decimal(near["move_pct"])) == min(abs(Decimal(r["move_pct"])) for r in rows)


def test_payoff_rows_move_pct_null_without_a_spot(provider):
    fe = as_json(outcome_to_dict(entries_outcome(provider, S54, payoff_step=Decimal(25))))["payoff_table"]
    assert fe["rows"] and all(r["move_pct"] is None and r["move_pct_display"] is None for r in fe["rows"])
