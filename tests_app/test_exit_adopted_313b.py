"""GC-6 #313b fix round 2 (Tier A review round 1 MAJOR): adopted lots are held legs on Execute and on the return route.

ADR-096: adding a held position "records the held legs (Zerodha's quantity, average price as the entry per ADR-084)".
ADR-126 (1): "An adopted leg's entry price ... is stored exactly as Zerodha reports the average ... never rounded or
refused"; (3) "Screens show the price to 2 decimals (7.03, half up for display only)".

Before the fix: ``_exit_fields`` priced held legs only from filled plan orders (``prices[B]`` KeyError once ``held.units``
held an adopted contract B), an adopted-only strategy had ``plan_number`` None (no active legs: no exit), and the
return route reconciled plan-order contracts only (an adopted-only contract was never compared with Zerodha).

No database: the route's own functions run on the real catalogue rows, the real recorded depth quote and the real
domain gate (``ofo.execution.safety``); the DB-backed route tests run in CI.
"""

from __future__ import annotations

import datetime
import types
from decimal import Decimal as D

import pytest
from ofo.engine import Action, Instrument
from ofo.engine.strategy import Strategy
from ofo.errors import render
from ofo.execution import safety
from ofo.execution.context import active_legs_hash, product_key
from ofo.instruments import Catalogue
from ofo.instruments.parser import zerodha_listed
from ofo_app import execute_plan as ep
from ofo_app import execution_plan_store as plans
from ofo_app import order_book_store as books
from ofo_app.execute_replay import CORE_ID, live_quote
from ofo_app.execute_replay import listed_contract as _listed
from ofo_app.routes import execute as route
from ofo_app.routes import execution_return as ret
from ofo_app.routes.strategies import StrategyRefused

A = f"{CORE_ID.exchange_segment}:{CORE_ID.exchange_token}"  # NIFTY26O1923650CE, the real listed contract
B_TOKEN = 12080642  # a second listed NIFTY call (same expiry, strike 23700) for the two-contract cases
B = f"{CORE_ID.exchange_segment}:{B_TOKEN >> 8}"
EXPIRY = datetime.date(2026, 10, 19)
AT = datetime.datetime(2026, 10, 16, 15, 7, tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30)))


def _catalogue() -> Catalogue:
    b = zerodha_listed(instrument_token=B_TOKEN, exchange_token=B_TOKEN >> 8, tradingsymbol="NIFTY26O1923700CE",
                       name="NIFTY", expiry=EXPIRY, strike=D("23700"), tick_size=D("0.05"), lot_size=65,
                       instrument_type="CE", segment="NFO-OPT", exchange="NFO")
    cat = Catalogue()
    cat.load([_listed(), b])
    return cat


def _plan_one_filled(contract: str = A) -> plans.StoredPlan:
    order = plans.PlanOrder(0, "Q0001010", contract, "NIFTY26O1923650CE", "BUY", 65, D("3.35"), filled_quantity=65)
    return plans.StoredPlan(1, 1, "ENTRY", "closed", (order,), AT, AT, "filled")


def _adopted(contract: str = B, price: D = D("7.025"), quantity: int = 65) -> books.AdoptedHolding:
    return books.AdoptedHolding(contract, "BUY", quantity, "NRML", price, "zerodha-position", version_number=2)


def _held(history: tuple, adopted: tuple) -> route._Held:  # noqa: SLF001 - the route's own held position
    units = ep.held_units(history, adopted)
    return route._Held(units, ep.version_state("EXIT", units), ep.latest_filled_plan(history), history, adopted)  # noqa: SLF001


def _exit(held: route._Held, catalogue: Catalogue) -> tuple[ep.PricedPlan, dict]:  # noqa: SLF001
    """The EXIT path of ``_execute`` up to the gate: exit legs from held units, priced from the real recorded depth,
    then the gate's active legs."""
    wanted = ep.exit_legs(held.units, route._iid)  # noqa: SLF001
    quote = ep.quote_from_kite(live_quote())
    priced = ep.price_legs("1", "NIFTY", wanted, catalogue, lambda iid, token: quote)
    return priced, route._exit_fields("1", held, priced, None, catalogue)  # noqa: SLF001


def _gate_exit(priced_legs: tuple, fields: dict) -> object:
    """The domain gate's reduce-only + product check on the fields the route built (products from the exit basket,
    held products = the same product, as Zerodha would report an NRML position)."""
    held_products = {product_key(leg): route.BASKET_PRODUCT for leg in fields["active_legs"] or ()}
    ctx = types.SimpleNamespace(active_legs=fields["active_legs"], underlying="NIFTY",
                                active_products=held_products, exit_products=fields["exit_products"])
    return safety._exit_failure(Strategy(priced_legs), ctx)  # noqa: SLF001


def test_plan_fill_on_a_and_adopted_b_exit_builds_for_both_with_no_keyerror():
    """Test (1). ADR-096 "average price as the entry": B's active leg is priced from its adopted average."""
    catalogue = _catalogue()
    held = _held((_plan_one_filled(),), (_adopted(),))
    assert held.units == {A: 65, B: 65}
    priced, fields = _exit(held, catalogue)
    assert [(p.contract, p.leg.action, p.leg.quantity) for p in priced.plan.legs] == [
        ("NIFTY26O1923650CE", Action.SELL, 65), ("NIFTY26O1923700CE", Action.SELL, 65)]
    legs = fields["active_legs"]
    assert [(leg.strike, leg.action, leg.quantity, leg.entry_price) for leg in legs] == [
        (D("23650"), Action.BUY, 65, D("3.35")), (D("23700"), Action.BUY, 65, D("7.03"))]
    assert all(isinstance(leg.entry_price, D) for leg in legs)
    assert fields["active_version_id"] == "plan-1"
    assert fields["active_legs_hash"] == active_legs_hash("1", "plan-1", legs)
    assert _gate_exit(priced.strategy.legs, fields) is None  # reduce-only and products pass: the basket is built


def test_adopted_only_strategy_shows_its_legs_and_its_exit_builds():
    """Test (2): no filled plan (plan_number None), one adopted lot -> active legs and a passing exit gate."""
    catalogue = _catalogue()
    held = _held((), (_adopted(price=D("7.00")),))
    assert held.plan_number is None and held.units == {B: 65}
    priced, fields = _exit(held, catalogue)
    (leg,) = fields["active_legs"]
    assert (leg.strike, leg.action, leg.quantity, leg.entry_price) == (D("23700"), Action.BUY, 65, D("7.00"))
    assert fields["active_version_id"] == "adopted-2"
    assert fields["active_legs_hash"] == active_legs_hash("1", "adopted-2", (leg,))
    assert _gate_exit(priced.strategy.legs, fields) is None


def test_no_exit_exceeds_held_units_with_adoptions():
    """An exit of 66 against 65 held (adopted) is refused by the reduce-only gate."""
    catalogue = _catalogue()
    held = _held((), (_adopted(),))
    priced, fields = _exit(held, catalogue)
    (sell,) = priced.strategy.legs
    too_many = (sell.__class__(sell.action, sell.instrument, sell.strike, sell.expiry, 66, sell.entry_price),)
    failure = _gate_exit(too_many, fields)
    assert failure is not None and failure.code is safety.CheckCode.EXIT_NOT_REDUCE_ONLY


def test_a_contract_both_filled_and_adopted_is_one_leg_with_the_net_units():
    """Counted once: plan fill 65 on A plus 65 adopted on A -> one A leg of 130 (the plan's price), exit SELL 130."""
    catalogue = _catalogue()
    held = _held((_plan_one_filled(),), (_adopted(contract=A),))
    assert held.units == {A: 130}
    priced, fields = _exit(held, catalogue)
    assert [(p.contract, p.leg.quantity) for p in priced.plan.legs] == [("NIFTY26O1923650CE", 130)]
    (leg,) = fields["active_legs"]
    assert (leg.quantity, leg.entry_price) == (130, D("3.35"))
    assert _gate_exit(priced.strategy.legs, fields) is None


def test_a_held_contract_with_no_price_fails_closed_with_the_catalogue_refusal():
    """No price for a held contract -> no active legs -> the gate's own catalogue refusal, never a guessed price."""
    held = route._Held({B: 65}, ep.version_state("EXIT", {B: 65}), None, (), ())  # noqa: SLF001
    priced, fields = _exit(held, _catalogue())
    assert fields["active_legs"] is None
    failure = _gate_exit(priced.strategy.legs, fields)
    assert failure is not None and failure.code is safety.CheckCode.EXIT_NOT_REDUCE_ONLY
    expected = render("gate_exit_unverified")
    assert (failure.message.code, failure.message.what_happened) == (expected.code, expected.what_happened)


def test_an_adopted_contract_the_catalogue_lost_is_the_catalogue_refusal_not_a_500():
    held = _held((), (_adopted(contract=f"{CORE_ID.exchange_segment}:99"),))
    with pytest.raises(KeyError):  # _execute maps KeyError to strategy_contract_not_in_catalogue
        route._exit_fields("1", held, types.SimpleNamespace(strategy=types.SimpleNamespace(legs=())), None, _catalogue())  # noqa: SLF001


def _world(net: dict, adopted: tuple, catalogue: Catalogue | None = None) -> ret._World:  # noqa: SLF001
    zerodha = types.SimpleNamespace(net=net)
    return ret._World(catalogue or _catalogue(), "NIFTY", zerodha, {}, frozenset(), adopted)  # noqa: SLF001


B_KEY = ("NIFTY", Instrument.CE, D("23700"), EXPIRY)


def test_return_route_reconciles_an_adopted_only_contract_and_flags_a_zerodha_difference():
    """Test (3): the reconcile list = plan-order contracts UNION adopted contracts; Zerodha holding 0 of the adopted
    65 is a mismatch that blocks; Zerodha holding the 65 is clean."""
    adopted = (_adopted(),)
    (check,) = ret._checks((), _world({}, adopted))  # noqa: SLF001
    assert (check.key, check.platform_units, check.zerodha_units) == (B_KEY, 65, 0)
    assert check.blocks
    (clean,) = ret._checks((), _world({B_KEY: 65}, adopted))  # noqa: SLF001
    assert not clean.blocks
    assert ret._symbols((), _world({}, adopted)) == {B_KEY: "NIFTY26O1923700CE"}  # noqa: SLF001


def test_return_route_counts_a_contract_in_a_plan_and_adopted_once():
    adopted = (_adopted(contract=A),)
    checks = ret._checks((_plan_one_filled(),), _world({}, adopted))  # noqa: SLF001
    assert [(c.platform_units, c.zerodha_units) for c in checks] == [(130, 0)]


def test_return_route_refuses_an_adopted_contract_the_catalogue_lost():
    adopted = (_adopted(contract=f"{CORE_ID.exchange_segment}:99"),)
    with pytest.raises(StrategyRefused):
        ret._checks((), _world({}, adopted))  # noqa: SLF001
