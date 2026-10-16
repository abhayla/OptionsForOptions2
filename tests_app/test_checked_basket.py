"""W-081 wired into the W-080 basket (REQ-055 AC-1/AC-3/AC-4, #273): the one production path to a basket decides on
Zerodha's figures only, replayed here from REAL recorded replies through a fake transport (no network, no database).

- funds: tests/fixtures/kite_margins/funds-2026-10-16-122104.json, the real ``GET /user/margins`` of 2026-10-16
  12:21:04 IST (``equity.net`` 671.5).
- basket: docs/research/kite-proof-2026-10-07/rest-2026-10-15/margins_basket.json, the real four-leg NIFTY condor
  reply (``final.total`` 68498.85; its two BUY legs need no ADR-094 top-up, so required = 68,498.85).
"""
from __future__ import annotations

import csv
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
