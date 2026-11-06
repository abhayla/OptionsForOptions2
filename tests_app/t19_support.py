"""Scenario -> the approaches route's inputs (Tracked, MarketInputs) for the T-19 cost tests (ADR-221).

Shared by tests_app/test_t19_cheapest_cost.py and the core proof. The charge rates are the scenario library's
stated rates (``adjust_scenarios_gen.CHARGE_RATES``: Zerodha's published F&O rates, ADR-082)."""
from __future__ import annotations

import datetime
import json
import sys
from decimal import Decimal as D
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))  # the generator lives in tests/
import adjust_scenarios_gen as gen
from ofo.adjustment.approaches import APPROACH_IDS, ChainRow, Position, PositionLeg
from ofo.adjustment.compare import Cheapest, Column, Context, MarginRead, compare
from ofo.adjustment.playbook_eval import body_from_fixture
from ofo.adjustment.preferences import from_values
from ofo.charges import ChargeRates
from ofo.rules.inputs import DataHealth
from ofo.settings import defaults as registry_defaults
from ofo_app import adjustment_check as check
from ofo_app.routes.adjustment import MarketInputs, Tracked, priced_approach

PREFS = from_values(registry_defaults())  # the registry defaults, passed explicitly (REQ-168 AC-1)
#: ADR-243: the roll basis of a user who changed nothing on a strategy with no plan (the admin default, target delta)
BASIS = check.basis_in_force(None, None, None)

FIX = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "adjust_scenarios"
PLAYBOOKS = json.loads((FIX / "_playbooks.json").read_text(encoding="utf-8"))
RATES = ChargeRates(**{**gen.CHARGE_RATES, "read_on": datetime.date.fromisoformat(gen.CHARGE_RATES["read_on"])})


def seed_rates(monkeypatch) -> None:
    """The screen's charge rates source (``routes.outcome.load_charge_rates``) answers ``RATES`` for this test, the way
    the screen tests seed it (the conftest default is a cached "no rate set", so T-19 is rightly not checked). The
    worker's lister and the screen routes read the SAME cache, so both price with the same set (ADR-254)."""
    import math  # noqa: PLC0415

    from ofo_app.routes import outcome  # noqa: PLC0415 - app module, loaded after the env placeholders
    monkeypatch.setattr(outcome, "_rates_cache", {"until": math.inf, "value": RATES})


def load(sid: str) -> dict:
    return json.loads((FIX / f"{sid}.json").read_text(encoding="utf-8"))


def _d(v: object) -> D | None:
    return None if v is None else D(str(v))


def inputs(sc: dict) -> tuple[Tracked, MarketInputs, D]:
    """The scenario's position (nearest expiry chain, as the approach builder reads it), booked P&L, no charges paid."""
    expiry = sc["expiry"]
    unpriced = {q["tradingsymbol"] for q in sc["broker"]["quote"]["legs"] if q["state"] != "stated"}
    rows = tuple(ChainRow(D(r["strike"]), r["type"], datetime.date.fromisoformat(c["expiry"]), r["tradingsymbol"],
                          *((None, None, None) if r["tradingsymbol"] in unpriced else
                            (_d(r["ltp"]), _d(r["bid"]), _d(r["ask"]))),
                          _d(r["delta"]), r["listed"], r["tradable"], r["low_oi"]["state"], r["low_oi"]["blocked"],
                          None,
                          None if r["tradingsymbol"] in unpriced else DataHealth.AVAILABLE)  # live book, ADR-172
                 for c in sc["market"]["chains"] if c["expiry"] == expiry for r in c["rows"])
    legs = tuple(PositionLeg(x["side"], x["type"], D(x["strike"]), datetime.date.fromisoformat(x["expiry"]), x["lots"],
                             D(x["entry"]), x["tradingsymbol"]) for x in sc["position"]["legs"] if x["type"] != "FUT")
    clock = datetime.datetime.fromisoformat(sc["clock"]["ist"])
    position = Position(sc["underlying"], sc["lot"], sc["expiry_kind"], clock.date(), legs)
    tracked = Tracked(position, D(sc["position"]["booked_pnl"]), D(0), sc["position"]["adjustments_used"])
    market = MarketInputs(rows, {}, None, None, None, None, None, clock)
    return tracked, market, D(sc["market"]["spot"])


def body_of(sc: dict) -> dict:
    body = body_from_fixture(PLAYBOOKS, sc["family"])
    on = sc["playbook_ref"]["plan_overrides"].get("approaches_on", [])
    body["approaches"]["applicable"] += [a for a in on if a not in body["approaches"]["applicable"]]
    return body


def compare_costs(tracked: Tracked, market: MarketInputs, spot: D) -> dict[str, object]:
    """The Compare's "This adjustment" cell of every built approach: the route's build path, then ``compare``."""
    cols = []
    for a in APPROACH_IDS:
        built, priced = priced_approach(a, tracked, market, spot, RATES, PREFS.approach, roll_basis=BASIS)
        if built is not None and priced is not None:
            cols.append(Column(built, priced.after, priced.reason, priced.charges_known, MarginRead(None)))
    ctx = Context(tracked.position, spot, market.chain, RATES, False, MarginRead(None), {}, tracked.adjustments_used,
                  PREFS.compare)
    cost = next(c for c in compare(cols, ctx).criteria if c.id == "cost")
    return dict(cost.values)


def cheapest(sc: dict) -> Cheapest:
    """The checker's T-19 cost of a scenario: ``adjustment_check.cheapest_offered`` on the scenario's own inputs."""
    tracked, market, spot = inputs(sc)
    return check.cheapest_offered(body_of(sc), tracked, market, spot, RATES, PREFS.approach, roll_basis=BASIS)
