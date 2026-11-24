"""D-11 (ADR-209 "Same basis as Max Profit / Max Loss", GC-ICLIVE-B): the Add Booked P&L switch ON puts the booked P&L
into the at-expiry and estimated-now curves too (not only the target block): every point of the drawn curve = open
legs + booked, with the line "includes +Rs 962.00 booked"; OFF is open legs only, no line. Real book: strategy 63
(booked +962.00 from the engine)."""
from __future__ import annotations

import pathlib
import sys
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from test_outcome_target_booked import LINE, _book_63_booked, _post, provider  # noqa: F401

D = Decimal


def _pts(points: list[dict]) -> list[Decimal]:
    return [D(p["pnl"]) for p in points]


def _common_shift(off: list[dict], on: list[dict]) -> set[Decimal]:
    """ON minus OFF at every level both curves have. R3: with the switch ON the 0-P&L levels are the booked-in
    breakevens, so the ON curve has those levels and not the open legs' own; every shared level moves by booked."""
    a, b = {p["level"]: D(p["pnl"]) for p in off}, {p["level"]: D(p["pnl"]) for p in on}
    shared = a.keys() & b.keys()
    assert len(shared) >= len(a) - 2 and shared, (len(shared), len(a))  # only the breakeven columns differ
    return {b[lv] - a[lv] for lv in shared}


async def test_core_switch_on_adds_booked_to_every_curve_point(provider):  # noqa: F811
    booked = _book_63_booked()
    off = await _post(provider, booked, paper_strategy_id=63, include_booked=False)
    on = await _post(provider, booked, paper_strategy_id=63)
    for key in ("at_expiry", "estimated_now"):
        a, b = off["curves"][key], on["curves"][key]
        if not a["available"]:
            continue
        assert _common_shift(a["points"], b["points"]) == {booked}
    assert _common_shift(off["payoff"]["points"], on["payoff"]["points"]) == {booked}
    assert on["curve_includes_booked_text"] == LINE
    assert off.get("curve_includes_booked_text") is None


async def test_unreadable_book_or_plan_leaves_the_curve_as_it_was(provider):  # noqa: F811
    plan = await _post(provider, None)
    again = await _post(provider, None, paper_strategy_id=63)
    assert plan["payoff"]["points"] == again["payoff"]["points"]
    assert again.get("curve_includes_booked_text") is None


def _level_values(body: dict) -> dict[str, dict[str, Decimal]]:
    """Every table the reply serves, as {table: {level: value}}: the TOTAL row of the scenario table, the scenario
    totals and the other view's, and the payoff table's two views."""
    levels = [x["level"] for x in body["scenario"]["levels"]]
    total = next(r for r in body["table"]["rows"] if r["row_id"] == "TOTAL")["cells"]
    got = {"table": {lv: D(total[lv]["value"]) for lv in levels if total[lv]["value"] is not None},
           "scenario": dict(zip(levels, (D(x) for x in body["scenario"]["totals"]), strict=True))}
    if body["scenario"]["other"]["totals"] is not None:
        got["other"] = dict(zip(levels, (D(x) for x in body["scenario"]["other"]["totals"]), strict=True))
    for key in ("at_expiry", "estimated_now"):
        got[f"payoff_table.{key}"] = {r["level"]: D(r[key]["pnl"]) for r in body["payoff_table"]["rows"] if r[key]}
    return got


async def test_d11_switch_on_every_table_row_is_open_legs_plus_booked(provider):  # noqa: F811
    booked = _book_63_booked()
    off = _level_values(await _post(provider, booked, paper_strategy_id=63, include_booked=False))
    on = _level_values(await _post(provider, booked, paper_strategy_id=63))
    assert off.keys() == on.keys() and off["table"] and off["payoff_table.at_expiry"]
    for name, rows in off.items():
        shared = rows.keys() & on[name].keys()
        assert len(shared) >= len(rows) - 2 and shared, name  # R3: only the 0-P&L (breakeven) columns move
        assert {lv: on[name][lv] - rows[lv] for lv in shared} == dict.fromkeys(shared, booked), name


async def test_d11_switch_on_zero_pnl_columns_and_total_be_cells_are_on_the_booked_in_basis(provider):  # noqa: F811
    """R3 fix 2 (D-11 / D-16): with the switch ON the TOTAL cells are open legs + booked, so the column headed 0-P&L and
    the TOTAL Lower / Upper BE cells must be the levels where THAT total is 0 (the chart's breakevens), not the open
    legs' breakevens: TOTAL at a 0-P&L column reads 0.00 and the BE cells are 0-P&L levels. OFF is unchanged."""
    booked = _book_63_booked()
    on = await _post(provider, booked, paper_strategy_id=63)
    off = await _post(provider, booked, paper_strategy_id=63, include_booked=False)
    for body, shifted in ((on, True), (off, False)):
        total = next(r for r in body["table"]["rows"] if r["row_id"] == "TOTAL")["cells"]
        zero = [x["level"] for x in body["scenario"]["levels"] if x["zero_pnl"]]
        assert zero, shifted
        for lv in zero:  # the cell at a 0-P&L column is 0.00 (the table's own rounding)
            assert abs(D(total[lv]["value"])) <= D("0.01"), (shifted, lv, total[lv]["value"])
        marked = {c["id"] for c in body["table"]["columns"] if "ZERO_PNL" in c["markers"]}
        assert marked == set(zero), (marked, zero)
        be = [D(total[k]["value"]) for k in ("lower_be", "upper_be") if total.get(k) and total[k]["value"] is not None]
        assert be and all(b in {D(z) for z in zero} for b in be), (shifted, be, zero)
    off_zero = [x["level"] for x in off["scenario"]["levels"] if x["zero_pnl"]]
    on_zero = [x["level"] for x in on["scenario"]["levels"] if x["zero_pnl"]]
    assert off_zero != on_zero  # booked +962 moves them
