"""W-080 AC-1 (REQ-073): the real iron condor becomes one read-only Kite basket of LIMIT orders in plan order.

Expected exchange / symbol / side / quantity come from the request legs of margins_basket.json (a request Kite
accepted on 2026-10-15), never from literals typed here."""
from __future__ import annotations

import copy
import dataclasses
import datetime
import inspect
import json
import pickle
from decimal import Decimal as D

import pytest
from basket_inputs import FakeFreeze, OkMargin, real_catalogue, real_plan, request_legs
from ofo.errors import display_text
from ofo.execution import basket as basket_module
from ofo.execution import margin_gate
from ofo.execution.basket import KITE_BASKET_URL, BasketRefused, KiteBasket, build_basket
from ofo.execution.margin_gate import MarginVerdict, check_margin
from ofo.execution.planned import ExecutionPlan, PlannedLeg
from ofo.instruments.models import ZERODHA, MissingBrokerRef


def _build(plan=None, cat=None, freeze=None, margin=None):
    cat = cat or real_catalogue()
    plan = plan or real_plan(cat)
    return build_basket(plan, cat, 3, freeze_check=freeze or FakeFreeze(), margin_source=margin or OkMargin())


def test_core_real_condor_makes_four_read_only_limit_orders() -> None:
    basket = _build()
    req = request_legs()
    assert len(basket.orders) == 4 == len(req)  # noqa: PLR2004
    for order, r in zip(basket.orders, req, strict=False):  # plan order, not sorted
        assert (order.exchange, order.tradingsymbol, order.transaction_type, order.quantity) == (
            r["exchange"], r["tradingsymbol"], r["transaction_type"], r["quantity"])
        assert order.quantity == 65  # noqa: PLR2004
        assert order.order_type == "LIMIT" and order.readonly is True
        assert order.variety == "regular" and order.product == "NRML"
        assert order.price == D(str(r["price"]))
    assert len({o.tag for o in basket.orders}) == 4  # noqa: PLR2004
    assert all(len(o.tag) <= 20 and o.tag.isascii() and o.tag.isalnum() for o in basket.orders)  # noqa: PLR2004


def test_every_order_carries_the_instrument_id_of_its_catalogue_row() -> None:
    cat = real_catalogue()
    basket = _build(cat=cat)
    for order in basket.orders:
        entry = cat.get(order.instrument_id)
        assert entry is not None and entry.ref(ZERODHA).broker_symbol == order.tradingsymbol


def test_json_matches_kite_form_and_has_no_float_artefacts() -> None:
    basket = _build()
    text = basket.orders_json()
    parsed = json.loads(text)
    assert [o["price"] for o in parsed] == [53.3, 17.3, 65.15, 34]
    assert '"price": 53.3,' in text and '"price": 65.15,' in text and '"price": 34,' in text
    assert all(o["readonly"] is True and o["order_type"] == "LIMIT" and o["tag"] for o in parsed)
    assert set(parsed[0]) == {"variety", "tradingsymbol", "exchange", "transaction_type", "order_type", "product",
                              "price", "quantity", "readonly", "tag"}
    assert KITE_BASKET_URL == "https://kite.zerodha.com/connect/basket"
    assert basket.form_fields("KEY") == {"api_key": "KEY", "data": text}


def test_price_3_95_serialises_as_3_95() -> None:
    cat = real_catalogue()
    plan = real_plan(cat)
    first = plan.legs[0]
    leg = dataclasses.replace(first.leg, entry_price=D("3.95"))
    plan = ExecutionPlan(plan.strategy_id, (PlannedLeg(first.leg_ref, first.contract, leg), *plan.legs[1:]))
    assert '"price": 3.95,' in _build(plan, cat).orders_json()


def test_plan_order_is_kept_when_legs_are_reversed() -> None:
    cat = real_catalogue()
    plan = real_plan(cat)
    rev = ExecutionPlan(plan.strategy_id, tuple(reversed(plan.legs)))
    assert [o.tradingsymbol for o in _build(rev, cat).orders] == [r["tradingsymbol"] for r in reversed(request_legs())]


def test_symbol_comes_from_the_catalogue_row_not_a_derived_form() -> None:
    """A catalogue row whose symbol differs from anything derivable from strike/expiry: the order uses the row."""
    cat = real_catalogue()
    plan = real_plan(cat)
    (entry,) = cat.entries_for_broker_symbol(ZERODHA, plan.legs[0].contract)
    entry.broker_refs[ZERODHA] = dataclasses.replace(entry.ref(ZERODHA), broker_symbol="ODDROW-1")
    one = ExecutionPlan("S-9", (PlannedLeg("L1", "ODDROW-1", plan.legs[0].leg),))
    order = _build(one, cat).orders[0]
    assert order.tradingsymbol == "ODDROW-1" and order.instrument_id == entry.id


def test_missing_broker_row_for_one_leg_refuses_the_whole_basket() -> None:
    cat = real_catalogue()
    plan = real_plan(cat)
    (entry,) = cat.entries_for_broker_symbol(ZERODHA, plan.legs[2].contract)
    del entry.broker_refs[ZERODHA]  # leg 3 can no longer even be found by its Zerodha symbol
    with pytest.raises(MissingBrokerRef):
        _build(plan, cat)


def test_unknown_contract_refuses_and_nothing_is_guessed() -> None:
    cat = real_catalogue()
    plan = real_plan(cat)
    bad = ExecutionPlan("S-9", (*plan.legs[:1], PlannedLeg("L9", "NOSUCHSYMBOL", plan.legs[1].leg)))
    with pytest.raises(MissingBrokerRef):
        _build(bad, cat)


def _twin_entry(cat, symbol):
    """A second catalogue entry (other exchange token) carrying the same Zerodha symbol, as F-03 allows."""
    from ofo.instruments.catalogue import CatalogueEntry  # noqa: PLC0415

    (e,) = cat.entries_for_broker_symbol(ZERODHA, symbol)
    contract = dataclasses.replace(e.contract, exchange_token=e.contract.exchange_token + 7_000_000)
    twin = CatalogueEntry(contract, True, dict(e.broker_refs))
    cat._entries[twin.id] = twin


def test_symbol_carried_by_two_entries_refuses_the_whole_basket() -> None:
    """Leg 0's symbol twice, every other leg intact: no way to pick, so no basket (kills `len != 1` -> `not entries`)."""  # noqa: E501
    cat = real_catalogue()
    plan = real_plan(cat)
    _twin_entry(cat, plan.legs[0].contract)
    assert len(cat.entries_for_broker_symbol(ZERODHA, plan.legs[0].contract)) == 2  # noqa: PLR2004
    assert all(len(cat.entries_for_broker_symbol(ZERODHA, p.contract)) >= 1 for p in plan.legs)
    with pytest.raises(MissingBrokerRef):
        _build(plan, cat)


@pytest.mark.parametrize("field", ["strike", "expiry", "type"])
def test_row_that_disagrees_with_the_plan_leg_refuses(field) -> None:
    cat = real_catalogue()
    plan = real_plan(cat)
    (e,) = cat.entries_for_broker_symbol(ZERODHA, plan.legs[1].contract)
    c = e.contract
    changed = {"strike": {"strike": c.strike + 50}, "expiry": {"expiry": c.expiry + datetime.timedelta(days=7)},
               "type": {"instrument_type": "PE" if c.instrument_type == "CE" else "CE"}}[field]
    e.contract = dataclasses.replace(c, **changed)
    with pytest.raises(BasketRefused):
        _build(plan, cat)


def test_margin_is_asked_about_exactly_the_orders_that_are_sent() -> None:
    margin = OkMargin()
    basket = _build(margin=margin)
    assert len(margin.calls) == 1 and margin.calls[0] == basket.orders


@pytest.mark.parametrize("sid", ["S-9x", "xS-9", "S-09", "S-", "s-9", "S--9"])
def test_strategy_id_must_be_exactly_the_tag_shape(sid) -> None:
    """kills fullmatch -> search / match: a malformed id never reaches a tag."""
    cat = real_catalogue()
    with pytest.raises(BasketRefused):
        _build(real_plan(cat, strategy_id=sid), cat)


def test_tag_strategy_comes_from_the_plan_not_the_caller() -> None:
    from ofo.execution.basket import parse_tag  # noqa: PLC0415

    assert {parse_tag(o.tag).strategy_id for o in _build().orders} == {9}  # the plan is "S-9"
    cat = real_catalogue()
    plan = real_plan(cat, strategy_id="not-a-number")
    with pytest.raises(BasketRefused):
        _build(plan, cat)


def test_delisted_contract_refuses() -> None:
    cat = real_catalogue()
    plan = real_plan(cat)
    (e,) = cat.entries_for_broker_symbol(ZERODHA, plan.legs[0].contract)
    e.currently_listed = False
    with pytest.raises(BasketRefused):
        _build(plan, cat)


def test_blocked_freeze_refuses_the_whole_basket() -> None:
    from ofo.errors import render  # noqa: PLC0415
    from ofo.execution.freeze import FreezeFinding  # noqa: PLC0415

    block = FreezeFinding("L1", "X", render("freeze_limit_unknown", contract="X"))
    freeze = FakeFreeze((block,))
    with pytest.raises(BasketRefused):
        _build(freeze=freeze)
    assert len(freeze.calls) == 1  # the basket called the gate itself


def test_blocked_margin_refuses_the_whole_basket() -> None:
    margin = OkMargin(allowed=False)
    with pytest.raises(BasketRefused):
        _build(margin=margin)
    assert len(margin.calls) == 1 and margin.funds_calls == 1  # the basket read both figures itself


def test_funds_equal_to_required_build_and_one_paisa_short_refuses() -> None:
    """The basket's own check_margin call decides on the source's two figures (kills dropping or inverting it)."""
    assert len(_build(margin=OkMargin(available=D("68498.85"), required=D("68498.85"))).orders) == 4  # noqa: PLR2004
    with pytest.raises(BasketRefused) as caught:
        _build(margin=OkMargin(available=D("68498.84"), required=D("68498.85")))
    shown = display_text(caught.value.user_message)
    assert "68,498.85" in shown and "68,498.84" in shown and shown in str(caught.value)


def test_a_closing_basket_needing_zero_builds_on_zero_funds() -> None:
    assert len(_build(margin=OkMargin(available=D("0"), required=D("0"))).orders) == 4  # noqa: PLR2004


class _Figures(OkMargin):
    """A source returning exactly the given figures (OkMargin swaps None for a default)."""

    def __init__(self, available: object, required: object) -> None:
        super().__init__()
        self.available, self.required = available, required


@pytest.mark.parametrize(("available", "required"), [
    (1e9, D("0")), (D("1e9"), 0.0), ("99999999", D("0")), (D("1e9"), "0"), (True, D("0")), (D("1e9"), None),
    (None, D("0")), (D("NaN"), D("0")), (D("Infinity"), D("0")), (D("1e9"), D("-1")), (D("1e9"), 0),
])
def test_an_unusable_figure_from_the_source_fails_closed(available, required) -> None:
    """A figure that is not an exact finite Decimal, a missing one, or a negative requirement is "not confirmed":
    refused with a user message, never a pass (kills passing on an exception or skipping the type check)."""
    with pytest.raises(BasketRefused) as caught:
        _build(margin=_Figures(available, required))
    assert caught.value.user_message is not None


class _Raising(OkMargin):
    def __init__(self, which: str) -> None:
        super().__init__()
        self.which = which

    def available_funds(self):
        if self.which == "available_funds":
            raise ConnectionError("Zerodha unreachable")
        return super().available_funds()

    def zerodha_required(self, orders, *, closes_held=False):
        if self.which == "zerodha_required":
            raise ConnectionError("Zerodha unreachable")
        return super().zerodha_required(orders, closes_held=closes_held)


@pytest.mark.parametrize("which", ["available_funds", "zerodha_required"])
def test_a_source_that_raises_fails_closed(which: str) -> None:
    with pytest.raises(BasketRefused) as caught:
        _build(margin=_Raising(which))
    assert caught.value.user_message is not None


@pytest.mark.parametrize("bad", [object(), lambda orders: True, "ok"])
def test_a_source_without_the_two_reads_fails_closed(bad) -> None:
    with pytest.raises(BasketRefused):
        _build(margin=bad)


def test_build_basket_takes_no_verdict() -> None:
    """Finding caller-supplied-verdict-trusted: no verdict crosses the boundary - the old ``margin_check`` callable that
    returned a verdict is not a parameter, and the only margin input is the source. #338: ``held`` is the held net
    (data); whether the orders only close it is computed inside, never passed in."""
    params = inspect.signature(build_basket).parameters
    assert "margin_check" not in params and list(params)[-2:] == ["margin_source", "held"]
    cat = real_catalogue()
    with pytest.raises(TypeError):
        build_basket(real_plan(cat), cat, 3, freeze_check=FakeFreeze(),  # type: ignore[call-arg]
                     margin_check=lambda orders: check_margin(D("1"), D("0")))


# -- forge shapes (round-2 attacks 1c/1d/1g/1h/1i): the verdict and the basket are sealed ------------------------


def test_a_basket_cannot_be_constructed_outside_build_basket() -> None:
    orders = _build().orders
    with pytest.raises(TypeError):
        KiteBasket(orders)
    with pytest.raises(TypeError):
        KiteBasket(orders=orders)
    assert not hasattr(basket_module, "_MINT") and not hasattr(margin_gate, "_MINT")  # no token to borrow
    with pytest.raises(TypeError):
        type("Sub", (KiteBasket,), {})


_FORGES = {
    "copy": copy.copy,
    "deepcopy": copy.deepcopy,
    "pickle": lambda obj: pickle.loads(pickle.dumps(obj)),  # noqa: S301 - the forge under test
    "replace": dataclasses.replace,
}


@pytest.mark.parametrize("forge", list(_FORGES))
def test_a_basket_cannot_be_copied_or_replaced(forge: str) -> None:
    basket = _build()
    with pytest.raises(TypeError):
        _FORGES[forge](basket)


def test_a_built_basket_cannot_be_edited() -> None:
    basket = _build()
    other = basket.orders[:1]
    for attempt in (lambda: setattr(basket, "orders", other), lambda: object.__setattr__(basket, "orders", other),
                    lambda: delattr(basket, "orders"), lambda: setattr(basket, "extra", 1)):
        with pytest.raises(AttributeError):
            attempt()
    assert len(basket.orders) == 4  # noqa: PLR2004


@pytest.mark.parametrize("forge", list(_FORGES))
def test_a_verdict_cannot_be_copied_or_replaced(forge: str) -> None:
    blocked = check_margin(D("671.50"), D("68498.85"))
    with pytest.raises(TypeError):
        _FORGES[forge](blocked)


def test_a_verdict_cannot_be_edited_or_self_minted() -> None:
    blocked = check_margin(D("671.50"), D("68498.85"))
    for attempt in (lambda: setattr(blocked, "allowed", True), lambda: object.__setattr__(blocked, "allowed", True),
                    lambda: object.__setattr__(blocked, "available", D("1e9")), lambda: delattr(blocked, "message")):
        with pytest.raises(AttributeError):
            attempt()
    assert blocked.allowed is False and blocked.message is not None
    with pytest.raises(TypeError):
        MarginVerdict(D("1"), D("0"))
    with pytest.raises(TypeError):
        MarginVerdict(D("1"), D("0"), _mint=object())
    with pytest.raises(TypeError):
        type("Sub", (MarginVerdict,), {})


def test_freeze_that_raises_fails_closed() -> None:
    def boom(plan):
        raise ConnectionError("freeze service down")

    with pytest.raises(BasketRefused):
        _build(freeze=boom)


def test_gates_are_required_parameters() -> None:
    cat = real_catalogue()
    with pytest.raises(TypeError):
        build_basket(real_plan(cat), cat, 3)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        build_basket(real_plan(cat), cat, 3, freeze_check=FakeFreeze())  # type: ignore[call-arg]


def test_freeze_result_of_wrong_type_fails_closed() -> None:
    with pytest.raises(BasketRefused):
        _build(freeze=lambda plan: None)


def test_non_plan_input_is_rejected() -> None:
    with pytest.raises(ValueError):
        build_basket("plan", real_catalogue(), 3, freeze_check=FakeFreeze(), margin_source=OkMargin())  # type: ignore[arg-type]
