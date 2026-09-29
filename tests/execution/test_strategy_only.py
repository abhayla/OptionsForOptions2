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
from ofo.execution import partial
from ofo.execution.send_guard import SendCapability, SendRefused, allowed_or_refuse, mint_capability
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
                       real.guard, real.plan, _mint=getattr(partial, "_MINT"))
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


def test_the_broker_is_reachable_only_with_a_capability_from_submit_confirmed() -> None:
    """AC-2/AC-3 runtime line: a submitter refuses a call without the one-shot capability submit_confirmed mints;
    a capability cannot be built directly or spent twice."""
    order = Order(STRATEGY_ID, "leg-4", CONTRACTS[3], Action.BUY, LOT, D("44.00"), version_id="v1")
    submitter = FakeSubmitter()
    for fake in (None, object(), "token"):
        with pytest.raises(SendRefused):
            submitter.submit(order, fake)
    with pytest.raises(SendRefused):
        SendCapability(order)
    cap = mint_capability(order)
    assert submitter.submit(order, cap) == "NEW-1"
    with pytest.raises(SendRefused):
        submitter.submit(order, cap)
    assert len(submitter.sent) == 1


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
    assert {n for n, t in modules.items() if _calls(t, "submit")} == {"execution/partial.py"}
    (fn,) = [n for n in modules["execution/partial.py"].body
             if isinstance(n, ast.FunctionDef) and n.name == "submit_confirmed"]
    assert len(_calls(fn, "submit")) == 1
    assert {n for n, t in modules.items() if _calls(t, "_issue")} == {"strategy/modification.py"}
    assert {n for n, t in modules.items() if _calls(t, "_decision")} == {"execution/partial.py", "strategy/guard.py"}
    assert {n for n, t in modules.items() if _calls(t, "mint_capability")} == {"execution/partial.py"}
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
