"""REQ-155 AC-2..AC-8 at route level: POST /api/strategies/{id}/adjustment-approaches on the scenario library.

The tracked strategy and the market come from the scenario fixtures through the route's own seams (no database, no
Kite): every iron condor scenario's approaches equal ``expected.approach_after`` to the paisa (gross, booked P&L in).
"""
from __future__ import annotations

import datetime
import json
import sys
from decimal import Decimal as D
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from ofo.adjustment.approaches import APPROACH_IDS, ChainRow, Position, PositionLeg
from ofo.engine.black_scholes import year_fraction
from ofo.marketdata.spot_source import SourceReading, SourceState
from ofo.outcome.service import MARGIN_CHECKED, Margin, margin_unreadable

from ofo_app.main import create_app
from ofo_app.routes import adjustment as route
from ofo_app.routes import outcome

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
import adjust_scenarios_gen as gen  # noqa: E402

FIX = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "adjust_scenarios"
IC_IDS = sorted(s["id"] for s in gen.scenarios() if s["family"] == "ic")


def load(sid: str) -> dict:
    return json.loads((FIX / f"{sid}.json").read_text(encoding="utf-8"))


def _d(v):
    return None if v is None else D(str(v))


def tracked_of(sc: dict, booked="stated") -> route.Tracked:
    legs = tuple(PositionLeg(x["side"], x["type"], D(x["strike"]), datetime.date.fromisoformat(x["expiry"]), x["lots"],
                             D(x["entry"]), x["tradingsymbol"]) for x in sc["position"]["legs"])
    today = datetime.date.fromisoformat(sc["clock"]["ist"][:10])
    pos = Position(sc["underlying"], sc["lot"], sc["expiry_kind"], today, legs)
    return route.Tracked(pos, None if booked == "unknown" else D(sc["position"]["booked_pnl"]), D("0"))


def market_of(sc: dict) -> route.MarketInputs:
    unpriced = {q["tradingsymbol"] for q in sc["broker"]["quote"]["legs"] if q["state"] != "stated"}
    rows, ids = [], {}
    for c in sc["market"]["chains"]:
        if c["expiry"] != sc["expiry"]:
            continue
        for r in c["rows"]:
            gone = r["tradingsymbol"] in unpriced
            rows.append(ChainRow(D(r["strike"]), r["type"], datetime.date.fromisoformat(c["expiry"]),
                                 r["tradingsymbol"], None if gone else _d(r["ltp"]), None if gone else _d(r["bid"]),
                                 None if gone else _d(r["ask"]), _d(r["delta"]), r["listed"], r["tradable"],
                                 r["low_oi"]["state"], r["low_oi"]["blocked"]))
            ids[r["tradingsymbol"]] = f"NSE_FO:{r['tradingsymbol']}"
    now = datetime.datetime.fromisoformat(sc["clock"]["ist"])
    spot = D(sc["market"]["spot"])
    feed_ok = sc["data_state"].get("feed", "ok") != "missing"
    return route.MarketInputs(tuple(rows), ids, spot, year_fraction(now, datetime.date.fromisoformat(sc["expiry"])),
                              D(sc["market"]["atm_iv"]),
                              SourceReading(SourceState.STATED, spot, now) if feed_ok else SourceReading(
                                  SourceState.ABSENT),
                              SourceReading(SourceState.ABSENT), now)


class Calls:
    def __init__(self):
        self.margin = 0


def client_for(sc: dict, *, booked="stated", margin=None, environ=None, rates=None, calls: Calls | None = None):
    app = create_app()
    rest_ok = sc["data_state"].get("rest", "ok") == "ok" and sc["data_state"].get("spot_source") != "none"
    now = datetime.datetime.fromisoformat(sc["clock"]["ist"])

    async def tracked(sid, _rates):
        return tracked_of(sc, booked) if sid == 72 else None  # noqa: PLR2004 - the one strategy of this user

    async def market(_t, _ctx):
        return market_of(sc)

    async def rest(_u):
        return (SourceReading(SourceState.STATED, D(sc["market"]["spot"]), now) if rest_ok
                else SourceReading(SourceState.FAILED))

    async def default_margin(legs):
        if calls is not None:
            calls.margin += 1
        return Margin(MARGIN_CHECKED, margin_unreadable().reason, D("100000"), D("100000"), D("500000"), now)

    app.dependency_overrides |= {
        route.get_tracked_reader: lambda: tracked, route.get_market_reader: lambda: market,
        route.get_rest_spot_reader: lambda: rest, route.get_approach_margin: lambda: margin or default_margin,
        route.get_held_environ: lambda: environ, outcome.load_charge_rates: lambda: rates,
        outcome.get_market_context: lambda: None}
    return TestClient(app)


def post(c, sid=72, body=None):
    return c.post(f"/api/strategies/{sid}/adjustment-approaches", json=body or {})


@pytest.mark.parametrize("sid", IC_IDS)
def test_ac2_every_scenario_approach_gross_equals_the_hand_values(sid):
    sc = load(sid)
    hand = sc["expected"].get("approach_after") or {}
    r = post(client_for(sc))
    assert r.status_code == 200, r.text
    body = r.json()
    if sc["data_state"].get("spot_source") == "none":
        assert body["approaches"] == [] and body["spot"]["value"] is None
        return
    by_id = {a["id"]: a for a in body["approaches"]}
    assert list(by_id) == list(APPROACH_IDS)
    for a, h in hand.items():
        got = by_id[a]
        if got["refusal"] is not None or not h.get("exact", True):
            continue
        g = got["after"]["gross"]
        assert D(g["max_profit"]) == D(h["max_profit"]), (sid, a, g, h)
        assert D(g["max_loss"]) == D(h["max_loss"]), (sid, a, g, h)
        assert [D(b) for b in g["breakevens"]] == [D(b).quantize(D("0.01")) for b in h["breakevens"]], (sid, a)
        assert D(got["after"]["booked_pnl"]) == D(h["booked_pnl"]), (sid, a)


def test_ac2_adj13_booked_pnl_is_in_the_after():
    body = post(client_for(load("ADJ-13"))).json()
    a36 = next(a for a in body["approaches"] if a["id"] == "A-36")
    assert a36["after"]["booked_pnl"] == "962.00" and a36["after"]["gross"]["max_loss"] == "20858.50"


def test_ac4_adj23_pop_present_and_held_switch_off_gives_dash_with_reason():
    sc = load("ADJ-23")
    on = post(client_for(sc, environ={"APP_ENV": "test"})).json()  # held_switches: ON in development and test
    assert on["pop_switch_on"] is True
    pops = {a["id"]: a["pop"] for a in on["approaches"] if a["refusal"] is None}
    assert all(p["value"] is not None for p in pops.values()), pops
    off = post(client_for(sc, environ={"APP_ENV": "production"})).json()
    assert off["pop_switch_on"] is False
    for a in off["approaches"]:
        if a["refusal"] is None:
            assert a["pop"]["value"] is None and a["pop"]["reason"].startswith("POP not available")


def test_ac5_adj24a_spot_from_rest_quote_and_adj24b_no_after():
    a = post(client_for(load("ADJ-24a"))).json()
    assert a["spot"]["source"] == "rest_quote" and a["spot"]["source_text"] == "Spot from a REST quote"
    b = post(client_for(load("ADJ-24b"))).json()
    assert b["spot"]["value"] is None and b["spot"]["text"].startswith("Spot not available") and b["approaches"] == []


def test_ac6_margin_failed_is_not_available_with_reason_other_figures_shown():
    async def failed(legs):
        return margin_unreadable()
    body = post(client_for(load("ADJ-20a"), margin=failed)).json()
    a01 = next(a for a in body["approaches"] if a["id"] == "A-01")
    assert a01["margin"]["value"] is None and a01["margin"]["reason"].startswith("Margin not available")
    assert a01["after"]["gross"]["max_profit"] is not None


def test_ac6_margin_empty_is_never_zero():
    async def empty(legs):
        return Margin(MARGIN_CHECKED, margin_unreadable().reason)
    body = post(client_for(load("ADJ-20b"), margin=empty)).json()
    for a in body["approaches"]:
        if a["refusal"] is None and a["after_legs"]:
            assert a["margin"]["state"] == "empty" and a["margin"]["value"] is None


def test_attack4_one_approach_margin_raises_others_keep_theirs():
    async def flaky(legs):
        if any(x.lots == 1 for x in legs):
            raise RuntimeError("boom")
        return Margin(MARGIN_CHECKED, margin_unreadable().reason, D("1"), D("1"), D("9"),
                      datetime.datetime(2026, 10, 30, 13, tzinfo=datetime.UTC))
    body = post(client_for(load("ADJ-13"), margin=flaky)).json()
    states = {a["id"]: a["margin"]["state"] for a in body["approaches"] if a["refusal"] is None and a["after_legs"]}
    assert states["A-29"] == "failed" and states["A-36"] == "stated"


@pytest.mark.parametrize("sid", ["ADJ-20c", "ADJ-20d", "ADJ-20e"])
def test_ac8_refusal_or_warning_while_others_still_show(sid):
    sc = load(sid)
    body = post(client_for(sc)).json()
    hand = sc["expected"]["approach_legs"]
    shown = [a for a in body["approaches"] if a["refusal"] is None]
    assert len(shown) >= 2  # noqa: PLR2004 - the other approaches still show
    for a in body["approaches"]:
        h = hand[a["id"]]
        if "refused" in h:
            assert a["refusal"] is not None and a["after"] is None, (sid, a["id"])
        else:
            assert a["refusal"] is None and len(a["warnings"]) == len(h["warnings"]), (sid, a["id"])
    if sid != "ADJ-20e":
        assert any(a["refusal"] for a in body["approaches"])


def test_attack1_unknown_strategy_404_nothing_priced():
    calls = Calls()
    r = post(client_for(load("ADJ-02"), calls=calls), sid=999)
    assert r.status_code == 404 and calls.margin == 0  # noqa: PLR2004


def test_attack2_unknown_approach_refused_others_answer():
    body = post(client_for(load("ADJ-02")), body={"approaches": ["A-99", "A-36"]}).json()
    assert body["approaches"][0]["refusal"].startswith("A-99 is not") and body["approaches"][1]["after"] is not None


def test_attack3_booked_unreadable_gives_no_whole_trade_figure():
    body = post(client_for(load("ADJ-13"), booked="unknown")).json()
    for a in body["approaches"]:
        if a["refusal"] is None:
            assert a["after"] is None and a["after_reason"].startswith("The booked P&L")


def test_attack5_rates_unreadable_gross_shown_after_charges_withheld():
    body = post(client_for(load("ADJ-02"), rates=None)).json()
    a = next(x for x in body["approaches"] if x["id"] == "A-36")
    assert a["after"]["gross"]["max_profit"] and a["after"]["after_charges"] is None
    assert a["charges"]["not_available"].startswith("Charges not available")


def test_ac7_seven_approaches_engine_time_at_most_one_second_and_no_order_path(monkeypatch):
    from ofo_app import paper_store
    def no_order(*_a, **_k):
        raise AssertionError("an order path was called")
    monkeypatch.setattr(paper_store, "place", no_order)
    monkeypatch.setattr(route, "app_env", lambda: "production")
    assert "timing" not in post(client_for(load("ADJ-02"))).json() or post(
        client_for(load("ADJ-02"))).json()["timing"] is None  # dev/test only
    monkeypatch.setattr(route, "app_env", lambda: "test")
    body = post(client_for(load("ADJ-02"))).json()
    assert body["timing"]["approaches"] == len(APPROACH_IDS)
    assert D(body["timing"]["engine_seconds"]) <= 1
