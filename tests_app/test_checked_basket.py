"""W-081 wired into the W-080 basket (REQ-055 AC-1/AC-3/AC-4, #273): the one production path to a basket decides on
Zerodha's figures only, replayed here from REAL recorded replies through a fake transport (no network, no database).

- funds: tests/fixtures/kite_margins/funds-2026-10-16-122104.json, the real ``GET /user/margins`` of 2026-10-16
  12:21:04 IST (``equity.net`` 671.5).
- basket: docs/research/kite-proof-2026-10-07/rest-2026-10-15/margins_basket.json, the real four-leg NIFTY condor
  reply (``final.total`` 68498.85; its two BUY legs need no ADR-094 top-up, so required = 68,498.85).
"""
from __future__ import annotations

import csv
import dataclasses
import datetime
import json
import pathlib
from decimal import Decimal as D

import pytest
from ofo.engine import Action, Instrument, Leg
from ofo.errors import display_text
from ofo.execution.basket import BasketRefused
from ofo.execution.freeze import FreezeCheck
from ofo.execution.planned import ExecutionPlan, PlannedLeg
from ofo.instruments.catalogue import Catalogue
from ofo.instruments.models import ZERODHA
from ofo.instruments.parser import parse_instruments_rows
from ofo.orders import Order
from ofo_app.checked_basket import checked_basket, zerodha_required_margin
from ofo_app.execution_plan_store import PlanOrder, StoredPlan
from ofo_app.kite_margin import KiteMargin

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONDOR = json.loads((ROOT / "docs/research/kite-proof-2026-10-07/rest-2026-10-15/margins_basket.json")
                    .read_text(encoding="utf-8"))
FUNDS = json.loads((ROOT / "tests/fixtures/kite_margins/funds-2026-10-16-122104.json").read_text(encoding="utf-8"))
LIST_CSV = ROOT / "tests/fixtures/kite_ws/instruments-2026-10-08-subscribed.csv"
CONDOR_REPLY = json.dumps(CONDOR["reply"])
REAL_FUNDS_REPLY = json.dumps(FUNDS["reply"])


def funds_reply(net: str) -> str:
    return '{"status": "success", "data": {"equity": {"enabled": true, "net": %s}}}' % net  # noqa: UP031


class Replay:
    """Fake transport: the funds reply for GET /user/margins, the basket reply for POST /margins/basket."""

    def __init__(self, funds: str, basket: str = CONDOR_REPLY, fail: str | None = None) -> None:
        self.funds, self.basket, self.fail, self.calls = funds, basket, fail, []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, body))
        if self.fail and self.fail in url:
            raise ConnectionError("Zerodha unreachable")
        return 200, self.funds if url.endswith("/user/margins") else self.basket


def client(transport: Replay) -> KiteMargin:
    return KiteMargin(api_key="key", access_token="tok", transport=transport)  # noqa: S106


def catalogue() -> Catalogue:
    wanted = {r["tradingsymbol"] for r in CONDOR["request"]}
    with LIST_CSV.open(newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["tradingsymbol"] in wanted]
    cat = Catalogue()
    cat.load(parse_instruments_rows(rows))
    return cat


def plan(cat: Catalogue) -> ExecutionPlan:
    legs = []
    for i, req in enumerate(CONDOR["request"], start=1):
        (entry,) = cat.entries_for_broker_symbol(ZERODHA, req["tradingsymbol"])
        c = entry.contract
        legs.append(PlannedLeg(f"L{i}", req["tradingsymbol"], Leg(Action(req["transaction_type"]),
                    Instrument(c.instrument_type), c.strike, c.expiry, req["quantity"], D(str(req["price"])))))
    return ExecutionPlan("S-9", tuple(legs))


def no_freeze(_plan: ExecutionPlan) -> FreezeCheck:
    return FreezeCheck((), ())


def build(transport: Replay):
    cat = catalogue()
    return checked_basket(plan(cat), cat, 3, margin_client=client(transport), freeze_check=no_freeze)


def test_real_funds_671_50_cannot_carry_the_real_condor_and_the_refusal_shows_both() -> None:
    """AC-1/AC-4 on real data: Zerodha's 671.50 against Zerodha's 68,498.85 -> no basket; the user sees both."""
    with pytest.raises(BasketRefused) as caught:
        build(Replay(REAL_FUNDS_REPLY))
    shown = display_text(caught.value.user_message)
    assert "671.50" in shown and "68,498.85" in shown


def test_funds_exactly_zerodhas_required_build_the_basket_from_the_same_orders() -> None:
    """AC-1: funds 68,498.85 == required -> built; the margin call was asked about exactly the basket's orders."""
    transport = Replay(funds_reply("68498.85"))
    basket = build(transport)
    assert [o.tradingsymbol for o in basket.orders] == [r["tradingsymbol"] for r in CONDOR["request"]]
    (post,) = [c for c in transport.calls if c[0] == "POST"]
    sent = json.loads(post[2], parse_float=D)
    assert [(s["tradingsymbol"], s["transaction_type"], s["quantity"], s["price"]) for s in sent] == [
        (o.tradingsymbol, o.transaction_type, o.quantity, o.price) for o in basket.orders]


def test_one_paisa_short_refuses_with_available_and_required() -> None:
    """AC-4: 68,498.84 against 68,498.85 -> no basket; the message names both amounts to the paisa."""
    with pytest.raises(BasketRefused) as caught:
        build(Replay(funds_reply("68498.84")))
    shown = display_text(caught.value.user_message)
    assert "68,498.84" in shown and "68,498.85" in shown


@pytest.mark.parametrize("fail", ["/user/margins", "/margins/basket"])
def test_zerodha_unreadable_builds_no_basket(fail: str) -> None:
    """Fail closed: either Zerodha read failing (huge funds notwithstanding) refuses the basket."""
    with pytest.raises(BasketRefused):
        build(Replay(funds_reply("99999999.00"), fail=fail))


def test_a_margin_client_that_is_not_zerodhas_is_refused() -> None:
    """The margin check is built from a real KiteMargin client only; a look-alike with generous answers is refused."""
    class Generous:
        def fetch_available_funds(self) -> D:
            return D("99999999")

        def fetch_basket_margin(self, orders):
            raise AssertionError("never asked")

    cat = catalogue()
    with pytest.raises(TypeError):
        checked_basket(plan(cat), cat, 3, margin_client=Generous(), freeze_check=no_freeze)  # type: ignore[arg-type]


def test_partial_recheck_figure_is_zerodhas_required_for_the_orders() -> None:
    """#273, app side of ``BrokerReader.fetch_required_margin``: the orders go to Zerodha's basket margin and its
    required figure (68,498.85, to the paisa) comes back; an unreadable reply raises (the domain then blocks)."""
    cat = catalogue()
    orders = [Order("S-9", f"L{i}", r["tradingsymbol"], Action(r["transaction_type"]), r["quantity"],
                    D(str(r["price"])), version_id="V-1") for i, r in enumerate(CONDOR["request"], start=1)]
    assert zerodha_required_margin(client(Replay(funds_reply("0"))), cat, orders) == D("68498.85")
    with pytest.raises(Exception):  # noqa: B017 - any failure is "not confirmed"
        zerodha_required_margin(client(Replay(funds_reply("0"), fail="/margins/basket")), cat, orders)


class _Lying(KiteMargin):
    def fetch_available_funds(self) -> D:
        return D("99999999")


def _lying() -> _Lying:
    return _Lying(api_key="key", access_token="tok", transport=Replay(REAL_FUNDS_REPLY))  # noqa: S106


def test_the_partial_recheck_needs_exactly_a_kitemargin_client() -> None:
    """MINOR-1 (round 2): kills dropping the ``type(client) is KiteMargin`` check in zerodha_required_margin - a duck
    or a subclass is refused before anything is asked."""
    class Duck:
        def fetch_basket_margin(self, orders):
            raise AssertionError("never asked")

    cat = catalogue()
    first = CONDOR["request"][0]
    order = Order("S-9", "L1", first["tradingsymbol"], Action(first["transaction_type"]), first["quantity"],
                  D(str(first["price"])), version_id="V-1")
    for bad in (Duck(), _lying()):
        with pytest.raises(TypeError):
            zerodha_required_margin(bad, cat, [order])  # type: ignore[arg-type]


def test_a_lying_subclass_or_an_instance_patched_client_cannot_answer() -> None:
    """Attack 2a/2c: a KiteMargin subclass is refused, and a method patched onto the real client's instance is never
    called - the source calls KiteMargin's own methods, so Zerodha's real 671.50 still refuses the condor."""
    cat = catalogue()
    with pytest.raises(TypeError):
        checked_basket(plan(cat), cat, 3, margin_client=_lying(), freeze_check=no_freeze)
    patched = client(Replay(REAL_FUNDS_REPLY))
    patched.fetch_available_funds = lambda: D("99999999")  # type: ignore[method-assign]
    with pytest.raises(BasketRefused) as caught:
        checked_basket(plan(cat), cat, 3, margin_client=patched, freeze_check=no_freeze)
    assert "671.50" in display_text(caught.value.user_message)


def test_a_closing_basket_needs_zero_and_builds_on_zero_funds() -> None:
    """ADR-094/#321: a closing basket's negative final.total (real exit -214.5) needs 0, so funds 0 build it."""
    reply = json.loads(CONDOR_REPLY)
    reply["data"]["final"]["total"] = -214.5
    assert len(build(Replay(funds_reply("0"), basket=json.dumps(reply))).orders) == 4  # noqa: PLR2004


@pytest.mark.parametrize("fail", ["/user/margins", "/margins/basket"])
def test_zerodha_unreadable_shows_could_not_confirm(fail: str) -> None:
    with pytest.raises(BasketRefused) as caught:
        build(Replay(funds_reply("99999999.00"), fail=fail))
    assert caught.value.user_message is not None



# -- #338: a closing basket is never blocked by a negative balance ---------------------------------------------------
# Real input: tests/fixtures/kite_replies/margins-basket-exit-150717.json, Zerodha's real POST /margins/basket reply
# for SELL 65 NIFTY26O1923650CE @ 3.30 against +65 held (final.total -214.5 -> required 0). The funds replies are
# derived from the real GET /user/margins shape (``equity.net``), with the balance set to each case's value.
EXIT_REPLY = (ROOT / "tests/fixtures/kite_replies/margins-basket-exit-150717.json").read_text(encoding="utf-8")
ENTRY_REPLY = (ROOT / "tests/fixtures/kite_replies/margins-basket-entry-derived.json").read_text(encoding="utf-8")
EXIT_SYMBOL = "NIFTY26O1923650CE"
OPEN_SYMBOL = CONDOR["request"][0]["tradingsymbol"]  # a contract the strategy does not hold


def _contract_cat(*symbols: str) -> Catalogue:
    with LIST_CSV.open(newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["tradingsymbol"] in symbols]
    cat = Catalogue()
    cat.load(parse_instruments_rows(rows))
    return cat


def _leg(cat: Catalogue, ref: str, symbol: str, side: Action, units: int,  # noqa: PLR0913 - one leg's fields
         price: str) -> PlannedLeg:
    (entry,) = cat.entries_for_broker_symbol(ZERODHA, symbol)
    c = entry.contract
    return PlannedLeg(ref, symbol, Leg(side, Instrument(c.instrument_type), c.strike, c.expiry, units, D(price)))


def _iid(cat: Catalogue, symbol: str):
    (entry,) = cat.entries_for_broker_symbol(ZERODHA, symbol)
    return entry.id


def _history(cat: Catalogue, symbol: str, units: int) -> tuple[StoredPlan, ...]:
    """The store's own row shape: one closed ENTRY plan whose order filled ``units`` (BUY +, SELL -) of ``symbol``;
    checked_basket derives what is held from it with ``execute_plan.held_units`` (#338 round 3)."""
    iid = _iid(cat, symbol)
    side = "BUY" if units > 0 else "SELL"
    order = PlanOrder(leg_index=0, tag="S9P1L0", instrument_id=f"{iid.exchange_segment}:{iid.exchange_token}",
                      tradingsymbol=symbol, transaction_type=side, quantity=abs(units), price=D("1.00"),
                      filled_quantity=abs(units))
    return (StoredPlan(strategy_id=9, plan_number=1, action="ENTRY", status="closed", orders=(order,),
                       created_at=datetime.datetime(2026, 10, 19, 10, 0, tzinfo=datetime.UTC), closed_at=None,
                       close_reason=None),)


def _two_order_reply(total: str) -> str:
    reply = json.loads(EXIT_REPLY)
    row = reply["data"]["orders"][0]
    reply["data"]["orders"] = [row, {**row, "tradingsymbol": OPEN_SYMBOL}]
    reply["data"]["final"]["total"] = json.loads(total)
    return json.dumps(reply)


def _exit_build(funds: str, *, held_units: int | None = 65, reply: str = EXIT_REPLY):
    cat = _contract_cat(EXIT_SYMBOL)
    held = () if not held_units else _history(cat, EXIT_SYMBOL, held_units)
    return checked_basket(ExecutionPlan("S-9", (_leg(cat, "L1", EXIT_SYMBOL, Action.SELL, 65, "3.30"),)), cat, 2,
                          margin_client=client(Replay(funds_reply(funds), basket=reply)), freeze_check=no_freeze,
                          history=held)


def test_core_real_exit_reply_with_negative_funds_builds_the_closing_basket() -> None:
    """REQ-055 AC-1 (#338 core): Zerodha's real exit reply (final.total -214.5 -> needs 0) with funds -120.50 and +65
    held -> the SELL 65 closing basket is built, its one order exactly the exit."""
    basket = _exit_build("-120.50")
    assert [(o.tradingsymbol, o.transaction_type, o.quantity, o.price) for o in basket.orders] == [
        (EXIT_SYMBOL, "SELL", 65, D("3.30"))]


@pytest.mark.parametrize("funds", ["-120.50", "0", "671.50"])
def test_closing_basket_builds_on_negative_zero_and_positive_funds(funds: str) -> None:
    """REQ-055 AC-1 (#338, B4 d): funds negative / zero / positive with the real exit reply -> built every time."""
    assert len(_exit_build(funds).orders) == 1


def test_an_entry_basket_with_the_same_negative_funds_is_blocked() -> None:
    """REQ-055 AC-1/AC-4 (#338 proof): the same SELL with nothing held (an entry) and funds -120.50 against the real
    exit reply's required 0 -> refused, both amounts shown (Zerodha's 0 is not enough when nothing is closed)."""
    with pytest.raises(BasketRefused) as caught:
        _exit_build("-120.50", held_units=None)
    shown = display_text(caught.value.user_message)
    assert "needs ₹0.00 of margin; -₹120.50 is available" in shown


@pytest.mark.parametrize("held_units", [-65, 64, 0])
def test_a_sell_that_does_not_reduce_what_is_held_is_checked_as_today(held_units: int) -> None:
    """REQ-055 AC-1 (#338): held SHORT 65 (the SELL adds), held 64 (the SELL of 65 exceeds it), held 0 -> negative
    funds refuse the basket."""
    with pytest.raises(BasketRefused):
        _exit_build("-120.50", held_units=held_units)


def test_zerodha_states_a_positive_required_for_a_closing_basket_checked_as_today() -> None:
    """REQ-055 AC-1 (#338 attack 2, B4 d 'stated positive'): Zerodha states a positive required (the derived entry
    reply, 354.25) for a basket that closes +65 held -> checked as today: -120.50 < 354.25 refuses."""
    with pytest.raises(BasketRefused) as caught:
        _exit_build("-120.50", reply=ENTRY_REPLY)
    assert "354.25" in display_text(caught.value.user_message)


def test_zerodha_states_a_positive_required_and_funds_cover_it_builds() -> None:
    """REQ-055 AC-1 (#338): a closing basket Zerodha says needs 354.25, funds 1003 -> built as today."""
    assert len(_exit_build("1003", reply=ENTRY_REPLY).orders) == 1


@pytest.mark.parametrize("total", ["-214.5", "0"])
def test_a_mixed_basket_close_one_open_another_with_negative_funds_is_blocked(total: str) -> None:
    """REQ-055 AC-1 (#338 attack 1): close +65 held AND open an unheld contract; Zerodha says the basket needs 0
    (negative or zero final.total) -> negative funds still refuse it: one leg opens a position."""
    cat = _contract_cat(EXIT_SYMBOL, OPEN_SYMBOL)
    legs = (_leg(cat, "L1", EXIT_SYMBOL, Action.SELL, 65, "3.30"),
            _leg(cat, "L2", OPEN_SYMBOL, Action.SELL, 75, "3.30"))
    with pytest.raises(BasketRefused):
        checked_basket(ExecutionPlan("S-9", legs), cat, 2,
                       margin_client=client(Replay(funds_reply("-120.50"), basket=_two_order_reply(total))),
                       freeze_check=no_freeze, history=_history(cat, EXIT_SYMBOL, 65))


@pytest.mark.parametrize("total", ['"x"', "null"])
def test_closing_basket_with_an_unparseable_or_missing_total_is_blocked(total: str) -> None:
    """REQ-055 AC-1 (#338, B4 d 'missing / unparseable'): no usable final.total -> could not confirm, never built."""
    reply = json.loads(EXIT_REPLY)
    reply["data"]["final"]["total"] = json.loads(total)
    with pytest.raises(BasketRefused):
        _exit_build("-120.50", reply=json.dumps(reply))


# -- ADR-113 (#338 round 2): a buy-back of a short is decided on Zerodha's final.total, no ADR-094 top-up ----------

def _buyback_reply(total: str) -> str:
    """The real exit reply's shape with the review's buy-back figures: final.total ``total``, option_premium 650."""
    reply = json.loads(EXIT_REPLY)
    reply["data"]["final"]["total"] = json.loads(total)
    reply["data"]["orders"][0]["option_premium"] = 650
    return json.dumps(reply)


def _buyback_build(funds: str, total: str, *, held_units: int | None = -65):
    cat = _contract_cat(EXIT_SYMBOL)
    held = () if not held_units else _history(cat, EXIT_SYMBOL, held_units)
    return checked_basket(ExecutionPlan("S-9", (_leg(cat, "L1", EXIT_SYMBOL, Action.BUY, 65, "10.50"),)), cat, 2,
                          margin_client=client(Replay(funds_reply(funds), basket=_buyback_reply(total))),
                          freeze_check=no_freeze, history=held)


@pytest.mark.parametrize("funds", ["-0.01", "0", "30"])
@pytest.mark.parametrize("total", ["-500", "0"])
def test_adr113_buyback_of_a_short_builds_at_any_funds(total: str, funds: str) -> None:
    """ADR-113 (#338 review finding 1): BUY 65 @ 10.50 buying back -65 held, Zerodha final.total -500 / 0 -> built at
    funds -0.01 / 0 / 30 (before: required 32.50, blocked)."""
    basket = _buyback_build(funds, total)
    assert [(o.tradingsymbol, o.transaction_type, o.quantity, o.price) for o in basket.orders] == [
        (EXIT_SYMBOL, "BUY", 65, D("10.50"))]


@pytest.mark.parametrize("funds", ["-0.01", "0", "30"])
def test_adr113_buyback_with_a_positive_final_total_is_compared_with_funds(funds: str) -> None:
    """ADR-113: Zerodha says +200 -> required 200.00 exactly (no top-up), refused at -0.01 / 0 / 30."""
    with pytest.raises(BasketRefused) as caught:
        _buyback_build(funds, "200")
    assert "needs ₹200.00 of margin" in display_text(caught.value.user_message)


def test_adr113_the_same_buy_as_an_entry_keeps_the_top_up() -> None:
    """ADR-094 kept: the same BUY with nothing held (an entry) needs 0 + 32.50 -> funds 30 refused, 32.50 shown."""
    with pytest.raises(BasketRefused) as caught:
        _buyback_build("30", "-500", held_units=None)
    assert "needs ₹32.50 of margin" in display_text(caught.value.user_message)


def test_adr113_a_mixed_basket_keeps_the_top_up_and_is_blocked_at_negative_funds() -> None:
    """ADR-113 applies only when EVERY order closes: buy back -65 held AND buy an unheld contract -> not reduce-only,
    the top-up stays, negative funds refuse."""
    cat = _contract_cat(EXIT_SYMBOL, OPEN_SYMBOL)
    legs = (_leg(cat, "L1", EXIT_SYMBOL, Action.BUY, 65, "10.50"),
            _leg(cat, "L2", OPEN_SYMBOL, Action.BUY, 75, "10.50"))
    reply = json.loads(_buyback_reply("-500"))
    row = reply["data"]["orders"][0]
    reply["data"]["orders"] = [row, {**row, "tradingsymbol": OPEN_SYMBOL}]
    with pytest.raises(BasketRefused):
        checked_basket(ExecutionPlan("S-9", legs), cat, 2,
                       margin_client=client(Replay(funds_reply("-0.01"), basket=json.dumps(reply))),
                       freeze_check=no_freeze, history=_history(cat, EXIT_SYMBOL, -65))


def test_a_caller_computed_held_mapping_is_not_accepted() -> None:
    """#338 round 3 (finding caller-supplied-verdict-trusted): checked_basket takes the store's rows, never a held
    mapping: the old keyword is gone, and a row that is not the store's StoredPlan is refused before Zerodha is read."""
    cat = _contract_cat(EXIT_SYMBOL)
    plan = ExecutionPlan("S-9", (_leg(cat, "L1", EXIT_SYMBOL, Action.SELL, 65, "3.30"),))
    margin = client(Replay(funds_reply("-0.01"), basket=EXIT_REPLY))
    with pytest.raises(TypeError):
        checked_basket(plan, cat, 2, margin_client=margin, freeze_check=no_freeze,  # type: ignore[call-arg]
                       held={_iid(cat, EXIT_SYMBOL): 65})
    with pytest.raises(TypeError, match="StoredPlan"):
        checked_basket(plan, cat, 2, margin_client=margin, freeze_check=no_freeze,
                       history=({"orders": ()},))  # type: ignore[arg-type]


def test_held_is_the_net_over_all_stored_plans() -> None:
    """ADR-105 via held_units: an ENTRY that filled +65 and an EXIT that filled -65 net to nothing held, so the SELL is
    an opening order and negative funds refuse it; the ENTRY alone holds +65 and the closing SELL is built."""
    cat = _contract_cat(EXIT_SYMBOL)
    (entry,) = _history(cat, EXIT_SYMBOL, 65)
    (sold,) = _history(cat, EXIT_SYMBOL, -65)
    exited = dataclasses.replace(sold, plan_number=2, action="EXIT",
                                 orders=(dataclasses.replace(sold.orders[0], tag="S9P2L0"),))
    plan = ExecutionPlan("S-9", (_leg(cat, "L1", EXIT_SYMBOL, Action.SELL, 65, "3.30"),))
    with pytest.raises(BasketRefused):
        checked_basket(plan, cat, 3, margin_client=client(Replay(funds_reply("-0.01"), basket=EXIT_REPLY)),
                       freeze_check=no_freeze, history=(entry, exited))
    built = checked_basket(plan, cat, 3, margin_client=client(Replay(funds_reply("-0.01"), basket=EXIT_REPLY)),
                           freeze_check=no_freeze, history=(entry,))
    assert len(built.orders) == 1
