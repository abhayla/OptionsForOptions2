"""REQ-036 AC-1..AC-3 (W-026): strategy-only execution, backend part.

Spec: REQ-036 AC-1 "Every order record references a strategy and strategy version; an order without one cannot be
created." AC-2 "No screen, UX level or API offers a standalone buy/sell of a single contract." (backend/API only)
AC-3 "Option Chain and Builder can prepare legs but submission happens only through the strategy's execution flow."
ADR-002 (every trade belongs to a strategy; no standalone orders at any level).

The public paths that create or send an order (listed by the AST tests below, which fail if a new one appears):
``Order(...)`` is constructed only in ``ofo/execution/partial.py`` (Complete / Retry / Close, each grounded on the
strategy's record); the broker ``submit`` is called only in ``submit_confirmed``; the Strategy Guard ``issue`` only by
the two owning flows (execution in ``partial.py``, modification in ``modification.py``); ``ofo.orders`` is imported
only by ``partial.py``.
"""
from __future__ import annotations

import ast
import dataclasses
import datetime
from decimal import Decimal as D
from pathlib import Path

import pytest
from partial_inputs import (
    FILL_AT,
    CONTRACTS,
    LOT,
    STRATEGY_ID,
    FakeBroker,
    FakePlanner,
    FakeSubmitter,
    book_with_three_filled,
    condor_record,
    entry_context,
    plan,
    statuses,
    three_positions,
)

from ofo.engine import Action, Strategy
from ofo.execution import partial, send_guard
from ofo.execution.send_guard import SendRefused, allowed_or_refuse
from ofo.execution.partial import (
    ExecutionPlan,
    PlannedLeg,
    PartialChoice,
    Preparation,
    complete_strategy,
    discard_preparation,
    submit_confirmed,
)
from ofo.orders import Order, OrderBook, OrderState
from ofo.strategy.definition import StrategyDefinition
from ofo.strategy.versions import ExecutionResult, Position, ResultStatus
from ofo.strategy.guard import GuardRefused, StrategyGuard

BACKEND = Path(__file__).resolve().parents[2] / "backend" / "ofo"


def _modules() -> dict[str, ast.Module]:
    return {p.relative_to(BACKEND).as_posix(): ast.parse(p.read_text(encoding="utf-8"))
            for p in sorted(BACKEND.rglob("*.py"))}


def _calls(tree: ast.AST, name: str) -> list[ast.Call]:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if (isinstance(f, ast.Name) and f.id == name) or (isinstance(f, ast.Attribute) and f.attr == name):
                out.append(node)
    return out


def _complete(book: OrderBook, catalogue, eligibility, **ctx) -> Preparation:  # noqa: ANN001
    return complete_strategy(plan(), FakeBroker(three_positions(), statuses()), book, FakePlanner(),
                             entry_context(**ctx), catalogue, eligibility)


# -- AC-1 -----------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("version_id", [None, "", " v1", 7])
def test_ac1_an_order_without_a_strategy_version_cannot_be_created(version_id: object) -> None:
    """AC-1: no version (None, empty, padded, not a string) -> the Order constructor refuses."""
    with pytest.raises(ValueError):
        Order(STRATEGY_ID, "leg-1", CONTRACTS[0], Action.BUY, LOT, D("42.50"), version_id=version_id)


@pytest.mark.parametrize("strategy_id", ["", "  ", None])
def test_ac1_an_order_without_a_strategy_cannot_be_created(strategy_id: object) -> None:
    """AC-1: no strategy id -> refused, even with a version."""
    with pytest.raises(ValueError):
        Order(strategy_id, "leg-1", CONTRACTS[0], Action.BUY, LOT, D("42.50"), version_id="v1")


def test_ac1_every_prepared_and_sent_order_names_the_strategy_and_its_record_version(catalogue, eligibility) -> None:
    """AC-1: the order the flow prepares and sends carries S-1 and v1, a version that exists in S-1's record."""
    book = book_with_three_filled()
    prep = _complete(book, catalogue, eligibility)
    submitter = FakeSubmitter()
    submit_confirmed(prep, choice=PartialChoice.COMPLETE_STRATEGY, confirmed_by="user:U-1", submitter=submitter)
    assert [(o.strategy_id, o.version_id) for o in submitter.sent] == [(STRATEGY_ID, "v1")]
    assert book.record_for(STRATEGY_ID).version(1).definition.legs  # v1 really exists in the bound record


def test_ac1_no_order_for_a_strategy_without_a_record_or_an_unknown_version(catalogue, eligibility) -> None:
    """AC-1: an unbound strategy, a version the record does not have, or a malformed version id prepares nothing."""
    with pytest.raises(ValueError, match="no strategy record"):
        _complete(book_with_three_filled(record=False), catalogue, eligibility)
    for bad in ("v2", "V-3", "v0"):
        with pytest.raises(ValueError):
            _complete(book_with_three_filled(), catalogue, eligibility, version_id=bad)


def test_ac1_a_plan_that_is_not_the_records_version_is_refused(catalogue, eligibility) -> None:
    """AC-1/AC-3: the plan must equal the named version's legs; a record whose v1 is a 2-lot condor refuses the
    1-lot plan."""
    book = book_with_three_filled(record=condor_record(2 * LOT))
    with pytest.raises(ValueError, match="not version 'v1'"):
        _complete(book, catalogue, eligibility)


def test_ac1_order_book_refuses_an_unknown_version_or_an_unbound_strategy() -> None:
    """AC-1 (verifier attack): ``OrderBook.add`` refused v99 of a bound strategy and any order of an unbound
    strategy, so nothing can be moved to Submitted for them either."""
    book = book_with_three_filled()
    for sid, version in (("S-1", "v99"), ("S-UNBOUND", "v1"), ("S-1", "v0"), ("S-1", "1")):
        with pytest.raises(ValueError):
            book.add(Order(sid, "x", CONTRACTS[2], Action.SELL, 5 * LOT, D("91.50"), version_id=version,
                           client_tag="OFO-X"))
        with pytest.raises(ValueError):
            book.transition_key("OFO-X", OrderState.SUBMITTED)
    assert [v.key for v in book.views_for("S-1")] == ["BRK-1", "BRK-2", "BRK-3", "BRK-4"]


def test_a_preparation_cannot_be_built_directly(catalogue, eligibility) -> None:
    """AC-2/AC-3: only the flow mints a Preparation; a direct construction is refused, and a flow-made one cannot
    be changed afterwards."""
    real = _complete(book_with_three_filled(), catalogue, eligibility)
    with pytest.raises(ValueError, match="made only by the strategy's execution flow"):
        Preparation(real.choice, real.assessment, real.orders, real.gate, "x", real.book, STRATEGY_ID)
    with pytest.raises(AttributeError):
        real.orders = ()  # type: ignore[misc]


def _reach_around(real: Preparation, orders: tuple[Order, ...], forge_gate: bool) -> Preparation:
    """In-process bypass of the mint (the verifier's getattr route): used only to prove the LATER lines hold."""
    discard_preparation(real)
    prep = Preparation(real.choice, real.assessment, orders, real.gate, "x", real.book, STRATEGY_ID, (),
                       real.guard, real.plan, real.catalogue, _mint=getattr(partial, "_MINT"))
    if forge_gate:  # also forge the gate-to-orders binding
        getattr(partial, "_GATE_ORDERS")[id(real.gate)] = (real.gate, getattr(partial, "_orders_digest")(orders))
    return prep


@pytest.mark.parametrize("order", [
    Order(STRATEGY_ID, "leg-3", CONTRACTS[2], Action.SELL, 5 * LOT, D("91.50"), version_id="v1"),  # naked short
    Order(STRATEGY_ID, "leg-4", "BANKNIFTY26OCT50000CE", Action.BUY, 30, D("100.00"), version_id="v1"),
    Order(STRATEGY_ID, "leg-4", CONTRACTS[3], Action.BUY, 2 * LOT, D("44.00"), version_id="v1"),  # too many
    Order(STRATEGY_ID, "leg-4", CONTRACTS[3], Action.SELL, LOT, D("44.00"), version_id="v1"),  # wrong side
    Order(STRATEGY_ID, "leg-4", CONTRACTS[3], Action.BUY, LOT, D("44.00"), version_id="v9"),  # unknown version
], ids=["naked-sell-5-lots", "banknifty-not-in-strategy", "over-quantity", "wrong-side", "version-v9"])
def test_ac2_verifier_attacks_send_nothing_even_through_the_private_mint(order, catalogue, eligibility) -> None:
    """AC-2 (verifier's two attacks and their class): reaching the private mint AND forging the gate binding still
    sends nothing, because ``submit_confirmed`` re-derives the allowed orders from the bound record and the ledger."""
    book = book_with_three_filled()
    prep = _reach_around(_complete(book, catalogue, eligibility), (order,), forge_gate=True)
    submitter = FakeSubmitter()
    expected = ValueError if order.version_id == "v9" else SendRefused  # the leg/side/quantity re-derivation itself
    with pytest.raises(expected):
        submit_confirmed(prep, choice=prep.choice, confirmed_by="user:U-1", submitter=submitter,
                         acknowledgement=prep.guard.acknowledgement if prep.guard else None)
    assert submitter.sent == [] and len(book.views_for("S-1")) == 4


def test_a_gate_result_from_other_orders_is_refused(catalogue, eligibility) -> None:
    """AC-3: a real passing gate result is bound to the orders it was run for; reused for other orders it refuses."""
    book = book_with_three_filled()
    real = _complete(book, catalogue, eligibility)
    other = (dataclasses.replace(real.orders[0], price=D("39.00")),)
    prep = _reach_around(real, other, forge_gate=False)
    submitter = FakeSubmitter()
    with pytest.raises(ValueError, match="does not belong to these orders"):
        submit_confirmed(prep, choice=prep.choice, confirmed_by="user:U-1", submitter=submitter)
    assert submitter.sent == []


def test_ac1_a_strategy_id_cannot_be_rebound_to_another_record() -> None:
    """AC-1: the record behind a strategy id cannot be swapped, and one record cannot serve two ids."""
    book = OrderBook()
    record = condor_record()
    book.bind_strategy(STRATEGY_ID, record)
    book.bind_strategy(STRATEGY_ID, record)  # idempotent for the same record
    with pytest.raises(ValueError):
        book.bind_strategy(STRATEGY_ID, condor_record())
    with pytest.raises(ValueError):
        book.bind_strategy("S-2", record)
    with pytest.raises(ValueError):
        book.bind_strategy("S-3", object())  # type: ignore[arg-type]


def test_ac1_only_the_strategy_execution_flow_constructs_an_order() -> None:
    """AC-1 (structural): ``Order(...)`` is called only in execution/partial.py; any new module that builds an order
    makes this fail."""
    where = {name for name, tree in _modules().items() if _calls(tree, "Order")}
    assert where == {"execution/partial.py"}
    assert len(_calls(_modules()["execution/partial.py"], "Order")) == 2  # _prepare_missing and close


# -- AC-2 -----------------------------------------------------------------------------------------------------------

_ORDER_WORDS = {"side", "action"}
_CONTRACT_WORDS = {"contract", "instrument", "tradingsymbol", "instrument_token"}
_STRATEGY_WORDS = {"strategy_id", "strategy", "plan", "record", "preparation", "definition"}
# Leg-shaped values that are not orders, each with the reason it cannot be sent on its own.
_ALLOWED_LEG_SHAPES = {
    "engine/legs.py:Leg": "a calculation input; nothing converts it to an order outside the execution flow",
    "strategy/definition.py:DefinitionLeg": "exists only inside a StrategyDefinition",
    "strategy/modification.py:LegChange": "resolved only against a record's active version (apply_changes)",
    "orders/model.py:FillEvent": "an inbound broker fact, keyed to a broker order that belongs to a strategy",
    "engine/inputs.py:LegInput": "a calculation input",
    "execution/review.py:ReviewLine": "a display row of the pre-execution review; it has no route to the broker",
    "outcome/service.py:OutcomeLeg": "a display row of the outcome view (W-063); it has no route to the broker",
}


def _names(node: ast.AST) -> set[str]:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        a = node.args
        return {x.arg for x in a.posonlyargs + a.args + a.kwonlyargs}
    return {t.target.id for t in node.body if isinstance(t, ast.AnnAssign) and isinstance(t.target, ast.Name)}


def test_ac2_no_public_api_takes_a_contract_side_and_quantity_without_a_strategy() -> None:
    """AC-2 (structural): no public function or record type accepts contract + side + quantity unless it also
    names the strategy (or is one of the listed non-order leg shapes). A new ``def buy(contract, side, quantity)``
    fails this test."""
    found = set()
    for name, tree in _modules().items():
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if node.name.startswith("_"):
                continue
            names = _names(node)
            if "quantity" in names and names & _ORDER_WORDS and names & _CONTRACT_WORDS and not names & _STRATEGY_WORDS:
                found.add(f"{name}:{node.name}")
    assert found <= set(_ALLOWED_LEG_SHAPES), sorted(found - set(_ALLOWED_LEG_SHAPES))


# -- AC-3 -----------------------------------------------------------------------------------------------------------

def test_ac3_only_submit_confirmed_sends_and_only_the_owning_flows_issue_a_guard_decision() -> None:
    """AC-3 (structural): the broker ``submit`` is called once, inside ``submit_confirmed``; ``ofo.orders`` and
    ``ofo.execution.partial`` are imported by no Builder / Option Chain / engine module; guard decisions are issued
    only by the execution flow and the modification flow."""
    modules = _modules()
    assert {n for n, t in modules.items() if _calls(t, "submit")} == {"execution/partial.py",
                                                                       "execution/send_guard.py"}
    (fn,) = [n for n in modules["execution/partial.py"].body
             if isinstance(n, ast.FunctionDef) and n.name == "submit_confirmed"]
    assert len(_calls(fn, "submit")) == 1
    assert {n for n, t in modules.items() if _calls(t, "_issue")} == {"strategy/modification.py"}
    assert {n for n, t in modules.items() if _calls(t, "_decision")} == {"execution/partial.py", "strategy/guard.py"}
    assert {n for n, t in modules.items() if _calls(t, "_BrokerSink")} == {"execution/partial.py"}
    public = {m for m in vars(StrategyGuard) if not m.startswith("_")}
    assert public == {"check", "redeem", "withdraw"}  # no public method accepts metrics or a verdict
    importers = set()
    for name, tree in modules.items():
        for node in ast.walk(tree):
            mod = node.module if isinstance(node, ast.ImportFrom) else None
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [mod or ""]
            if any(m == "ofo.orders" or m.startswith("ofo.orders.") or m == "ofo.execution.partial" for m in mods):
                importers.add(name)
    assert importers - {"orders/__init__.py"} == {"execution/partial.py", "execution/send_guard.py"}


def test_ac3_builder_output_is_legs_only_and_cannot_be_submitted(catalogue, eligibility) -> None:
    """AC-3: what the Builder produces (a StrategyDefinition of legs) is refused by the submitter; the only way to a
    submission is a preparation made by the strategy's execution flow."""
    definition = StrategyDefinition.from_engine("NIFTY", Strategy(tuple(p.leg for p in plan().legs)))
    with pytest.raises(ValueError, match="needs a Preparation"):
        submit_confirmed(definition, choice=PartialChoice.COMPLETE_STRATEGY, confirmed_by="user:U-1",  # type: ignore[arg-type]
                         submitter=FakeSubmitter())
    prep = _complete(book_with_three_filled(), catalogue, eligibility)
    assert prep.ready and prep.gate is not None and not prep.gate.blocked  # the gate ran inside the flow
    assert submit_confirmed(prep, choice=PartialChoice.COMPLETE_STRATEGY, confirmed_by="user:U-1",
                            submitter=FakeSubmitter()).submitted


def test_send_rule_refuses_an_order_of_another_strategy_or_version() -> None:
    """AC-1, ``allowed_or_refuse`` on its own: an order naming another strategy or version is never a permitted
    leg, whatever the plan says."""
    book = book_with_three_filled()
    record = book.record_for(STRATEGY_ID)
    planned = {c: (f"leg-{i + 1}", p.leg.action, p.leg.quantity) for i, (c, p) in enumerate(zip(CONTRACTS, plan().legs))}
    for sid, version in (("S-2", "v1"), (STRATEGY_ID, "v2")):
        order = Order(sid, "leg-4", CONTRACTS[3], Action.BUY, LOT, D("44.00"), version_id=version)
        with pytest.raises(SendRefused, match="does not belong"):
            allowed_or_refuse(choice="complete", orders=(order,), version=record.version(1), planned=planned,
                              book=book, strategy_id=STRATEGY_ID)


def test_only_the_active_or_pending_version_executes(catalogue, eligibility) -> None:
    """AC-1: a version that is neither active nor pending (v1 rejected, nothing active) prepares nothing."""
    record = condor_record()
    record.confirm(1, at=FILL_AT - datetime.timedelta(minutes=8))
    record.apply_result(ExecutionResult(1, ResultStatus.REJECTED, Position(), FILL_AT - datetime.timedelta(minutes=7),
                                        "rejected-1"))
    assert record.active_version is None and record.proposed_version is None
    with pytest.raises(SendRefused, match="neither the active nor the pending"):
        _complete(book_with_three_filled(record=record), catalogue, eligibility)


def test_a_plan_symbol_must_be_its_legs_catalogue_instrument(catalogue) -> None:
    """AC-3: the plan's contract symbol for the 23,600 CE leg swapped for the same strike on ANOTHER expiry (a real
    catalogue row) is refused when the flow grounds the plan."""
    good = plan()
    legs = list(good.legs)
    legs[3] = PlannedLeg(legs[3].leg_ref, "NIFTY26SEP23600CE", legs[3].leg)
    with pytest.raises(ValueError, match="not the catalogue instrument"):
        getattr(partial, "_grounded_plan")(book_with_three_filled(), ExecutionPlan(STRATEGY_ID, tuple(legs)), "v1",
                                           catalogue)
    assert getattr(partial, "_grounded_plan")(book_with_three_filled(), good, "v1", catalogue) is not None



# -- W-026 round 3: the broker sink ----------------------------------------------------------------------------------
# Core: the sink re-derives every broker field (symbol, side, quantity, strategy, version) from the bound record and
# the catalogue, and no public name reaches it except submit_confirmed. Private names below (_BrokerSink, _MINT) are
# used ONLY to prove the sink's own checks hold behind the flow (R3: reach-arounds are out of scope, documented).

class CountingTransport:
    """The broker transport: counts every call; returns the broker id."""

    def __init__(self) -> None:
        self.calls: list[object] = []

    def submit(self, request: object) -> str:
        self.calls.append(request)
        return f"NEW-{len(self.calls)}"


def _sink(book: OrderBook, catalogue, choice: str = "complete", leg_slots=None, transport=None):  # noqa: ANN001, ANN202
    slots = leg_slots or {p.leg_ref: (p.leg.instrument.value, p.leg.strike, p.leg.expiry) for p in plan().legs}
    return send_guard._BrokerSink(transport or CountingTransport(), book=book, strategy_id=STRATEGY_ID,
                                  catalogue=catalogue, choice=choice, leg_slots=slots)


def _tagged(order: Order) -> Order:
    return dataclasses.replace(order, client_tag="OFO999999999")


def test_core_sink_refuses_a_forged_plan_symbol_and_the_transport_is_never_called(catalogue, eligibility) -> None:
    """Core (round 3): a reach-around preparation whose forged plan puts the 23,600 CE symbol on the strike-23,400
    leg (leg-3) is refused AT THE SINK; the transport's call count stays 0."""
    book = book_with_three_filled()
    real = _complete(book, catalogue, eligibility)
    forged_legs = list(plan().legs)
    forged_legs[2] = PlannedLeg("leg-3", CONTRACTS[3], forged_legs[2].leg)  # 23600CE symbol on the 23400 leg
    forged_legs[3] = PlannedLeg("leg-4", CONTRACTS[2], forged_legs[3].leg)
    forged_plan = ExecutionPlan(STRATEGY_ID, tuple(forged_legs))
    transport = CountingTransport()
    order = Order(STRATEGY_ID, "leg-3", CONTRACTS[3], Action.BUY, LOT, D("44.00"), version_id="v1")
    with pytest.raises(SendRefused, match="not the catalogue symbol"):
        _sink(book, catalogue, transport=transport,
              leg_slots={p.leg_ref: (p.leg.instrument.value, p.leg.strike, p.leg.expiry) for p in forged_plan.legs}
              ).resolve_all((_tagged(order),))
    assert transport.calls == []
    discard_preparation(real)


def test_sink_refuses_a_banknifty_symbol_on_a_nifty_record(catalogue) -> None:
    """Round 3: a BANKNIFTY contract on the NIFTY record is refused at the sink; transport untouched."""
    transport = CountingTransport()
    order = Order(STRATEGY_ID, "leg-4", "BANKNIFTY26OCT50000CE", Action.BUY, 30, D("100.00"), version_id="v1")
    with pytest.raises(SendRefused, match="not the catalogue symbol"):
        _sink(book_with_three_filled(), catalogue, transport=transport).resolve_all((_tagged(order),))
    assert transport.calls == []


def test_sink_refuses_an_unknown_strategy_and_never_calls_the_transport(catalogue) -> None:
    """Round 3: Order('S-NOSUCH', ...) is refused at the sink; a sink for an unbound strategy cannot even open."""
    transport = CountingTransport()
    order = Order("S-NOSUCH", "leg-4", CONTRACTS[3], Action.BUY, LOT, D("44.00"), version_id="v1")
    with pytest.raises(SendRefused, match="belong to this strategy; nothing"):  # the sink's own check
        _sink(book_with_three_filled(), catalogue, transport=transport).resolve_all((_tagged(order),))
    with pytest.raises(ValueError, match="no strategy record"):
        send_guard._BrokerSink(transport, book=book_with_three_filled(), strategy_id="S-NOSUCH", catalogue=catalogue,
                               choice="complete", leg_slots={})
    assert transport.calls == []


def test_sink_derives_side_from_the_leg_never_from_the_order(catalogue) -> None:
    """Round 3: leg-4 is a BUY; an order claiming SELL for it is refused at the sink (the side is derived)."""
    transport = CountingTransport()
    order = Order(STRATEGY_ID, "leg-4", CONTRACTS[3], Action.SELL, LOT, D("44.00"), version_id="v1")
    with pytest.raises(SendRefused, match="is not the side of leg"):
        _sink(book_with_three_filled(), catalogue, transport=transport).resolve_all((_tagged(order),))
    assert transport.calls == []


def test_sink_needs_the_catalogue(catalogue) -> None:
    """Round 3: without the catalogue the sink cannot derive a symbol, so it refuses to open."""
    with pytest.raises(SendRefused, match="needs the catalogue"):
        _sink(book_with_three_filled(), None)


def test_sink_room_counts_units_still_open_on_the_book(catalogue) -> None:
    """Verifier's surviving M3: the 23,600 CE order still open at the broker (Submitted, 0 filled) leaves no room;
    a second BUY of it is refused at the send rule and at the sink."""
    book = book_with_three_filled(fourth=OrderState.SUBMITTED)
    order = Order(STRATEGY_ID, "leg-4", CONTRACTS[3], Action.BUY, LOT, D("44.00"), version_id="v1")
    planned = {CONTRACTS[3]: ("leg-4", Action.BUY, LOT)}
    with pytest.raises(SendRefused, match="exceed what the strategy allows"):
        allowed_or_refuse(choice="complete", orders=(order,), version=book.record_for(STRATEGY_ID).version(1),
                          planned=planned, book=book, strategy_id=STRATEGY_ID)
    transport = CountingTransport()
    with pytest.raises(SendRefused, match="exceed"):
        _sink(book, catalogue, transport=transport).resolve_all((_tagged(order),))
    assert transport.calls == []


def test_sink_sends_only_what_it_resolved_and_only_once(catalogue) -> None:
    """Round 3: the happy path resolves the one missing leg to the record's own values; a request is sent once."""
    transport = CountingTransport()
    sink = _sink(book_with_three_filled(), catalogue, transport=transport)
    order = _tagged(Order(STRATEGY_ID, "leg-4", CONTRACTS[3], Action.BUY, LOT, D("44.00"), version_id="v1"))
    (request,) = sink.resolve_all((order,))
    assert (request.strategy_id, request.version_id, request.contract, request.side, request.quantity) == (
        STRATEGY_ID, "v1", "NIFTY26O0623600CE", Action.BUY, LOT)
    assert sink.submit(request) == "NEW-1"
    with pytest.raises(SendRefused):
        sink.submit(request)
    with pytest.raises(SendRefused):  # a request cannot be built outside the sink
        send_guard._BrokerRequest(STRATEGY_ID, "v1", "leg-4", CONTRACTS[3], Action.BUY, LOT, D("44"), "T")
    assert len(transport.calls) == 1


def test_happy_path_sends_exactly_the_missing_leg_through_submit_confirmed(catalogue, eligibility) -> None:
    """Round 3: Complete on three filled legs sends exactly BUY 65 x NIFTY26O0623600CE for S-1 v1."""
    transport = CountingTransport()
    prep = _complete(book_with_three_filled(), catalogue, eligibility)
    submit_confirmed(prep, choice=PartialChoice.COMPLETE_STRATEGY, confirmed_by="user:U-1", submitter=transport)
    assert [(r.strategy_id, r.version_id, r.contract, r.side, r.quantity) for r in transport.calls] == [
        (STRATEGY_ID, "v1", "NIFTY26O0623600CE", Action.BUY, LOT)]


def test_a_transport_handed_an_order_directly_has_no_public_route(catalogue) -> None:
    """Round 3: the only public route to a transport is submit_confirmed, which refuses anything but a
    flow-made preparation; the transport is never called."""
    transport = CountingTransport()
    order = Order(STRATEGY_ID, "leg-4", CONTRACTS[3], Action.BUY, LOT, D("44.00"), version_id="v1")
    with pytest.raises(ValueError, match="needs a Preparation"):
        submit_confirmed(order, choice=PartialChoice.COMPLETE_STRATEGY, confirmed_by="user:U-1",  # type: ignore[arg-type]
                         submitter=transport)
    assert transport.calls == []


def test_an_aliased_submit_confirmed_works_only_through_the_real_flow(catalogue, eligibility) -> None:
    """Round 3: importing submit_confirmed under another name changes nothing: a hand-made preparation is refused,
    a flow-made one is sent."""
    from ofo.execution.partial import submit_confirmed as send_it
    transport = CountingTransport()
    real = _complete(book_with_three_filled(), catalogue, eligibility)
    with pytest.raises(ValueError, match="made only by the strategy's execution flow"):
        Preparation(real.choice, real.assessment, real.orders, real.gate, "x", real.book, STRATEGY_ID)
    send_it(real, choice=PartialChoice.COMPLETE_STRATEGY, confirmed_by="user:U-1", submitter=transport)
    assert len(transport.calls) == 1


_SINK_NAMES = ("_BrokerRequest", "_Transport", "_BrokerSink")
# Public names allowed to mention them: the one public route, and send-rule helpers that only raise.
_SINK_OWNERS = {"ofo.execution.partial.submit_confirmed", "ofo.execution.send_guard.SendRefused",
                "ofo.execution.send_guard.allowed_or_refuse", "ofo.execution.send_guard.executable_version"}


def test_no_public_name_reaches_a_broker_request_transport_or_sink() -> None:
    """R1 (runtime walk): import every ofo module; no public name is (or aliases) the request, transport or sink
    type, no public name is a capability minter, and no public callable except submit_confirmed accepts or returns
    a broker request, transport or sink."""
    import importlib
    import inspect
    import pkgutil

    import ofo
    private_objects = {id(getattr(send_guard, n)) for n in _SINK_NAMES}
    offenders = []
    for info in pkgutil.walk_packages(ofo.__path__, "ofo."):
        module = importlib.import_module(info.name)
        for name, value in vars(module).items():
            if name.startswith("_"):
                continue
            where = f"{info.name}.{name}"
            if id(value) in private_objects or "capabilit" in name.lower() or name.lower().startswith("mint"):
                offenders.append(where)
                continue
            if not callable(value) or getattr(value, "__module__", "") != info.name:
                continue
            try:  # a public function that builds or wraps a sink, request or transport, even unannotated
                body = inspect.getsource(value)
            except (OSError, TypeError):
                body = ""
            if any(t in body for t in _SINK_NAMES) and where not in _SINK_OWNERS:
                offenders.append(f"{where} (source names {[t for t in _SINK_NAMES if t in body]})")
                continue
            targets = [value] + ([m for _, m in inspect.getmembers(value, inspect.isfunction)]
                                 if inspect.isclass(value) else [])
            for fn in targets:
                try:
                    sig = inspect.signature(fn)
                except (TypeError, ValueError):
                    continue
                text = " ".join(str(p.annotation) for p in sig.parameters.values()) + " " + str(sig.return_annotation)
                if any(t in text for t in _SINK_NAMES) and where != "ofo.execution.partial.submit_confirmed":
                    offenders.append(f"{where}:{getattr(fn, '__name__', '')}")
    assert offenders == []


def test_send_time_grounding_uses_the_catalogue(catalogue, eligibility) -> None:
    """Round 3: at the send, the preparation's plan is grounded against the catalogue again; a reach-around plan that
    swaps the 23,400 CE and 23,600 CE symbols is refused there with the catalogue reason, and nothing is sent."""
    book = book_with_three_filled()
    real = _complete(book, catalogue, eligibility)
    legs = list(real.plan.legs)
    legs[2], legs[3] = (PlannedLeg("leg-3", CONTRACTS[3], legs[2].leg), PlannedLeg("leg-4", CONTRACTS[2], legs[3].leg))
    order = Order(STRATEGY_ID, "leg-4", CONTRACTS[2], Action.BUY, LOT, D("44.00"), version_id="v1")
    discard_preparation(real)
    prep = Preparation(real.choice, real.assessment, (order,), real.gate, "x", book, STRATEGY_ID, (), real.guard,
                       ExecutionPlan(STRATEGY_ID, tuple(legs)), real.catalogue, _mint=getattr(partial, "_MINT"))
    getattr(partial, "_GATE_ORDERS")[id(real.gate)] = (real.gate, getattr(partial, "_orders_digest")((order,)))
    transport = CountingTransport()
    with pytest.raises(ValueError, match="not the catalogue instrument"):
        submit_confirmed(prep, choice=prep.choice, confirmed_by="user:U-1", submitter=transport)
    assert transport.calls == []
