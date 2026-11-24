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


async def test_core_switch_on_adds_booked_to_every_curve_point(provider):  # noqa: F811
    booked = _book_63_booked()
    off = await _post(provider, booked, paper_strategy_id=63, include_booked=False)
    on = await _post(provider, booked, paper_strategy_id=63)
    for key in ("at_expiry", "estimated_now"):
        a, b = off["curves"][key], on["curves"][key]
        if not a["available"]:
            continue
        assert [y - x for x, y in zip(_pts(a["points"]), _pts(b["points"]), strict=True)] == [booked] * len(a["points"])
    assert [y - x for x, y in zip(_pts(off["payoff"]["points"]), _pts(on["payoff"]["points"]), strict=True)] \
        == [booked] * len(off["payoff"]["points"])
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
        assert rows.keys() == on[name].keys(), name
        assert {lv: on[name][lv] - v for lv, v in rows.items()} == {lv: booked for lv in rows}, name
