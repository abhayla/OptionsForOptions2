"""Modular doors Phase 6 (PLAN 5.6, B2): the whole Kite exit basket of one condor exit, byte for byte.
``_wanted`` -> ``price_legs`` -> ``checked_basket`` on the fixed catalogue of ``test_checked_basket`` (the real
recorded condor contracts), deterministic depth and zero funds (a closing basket needs 0). The repr below was
captured on the code BEFORE ``exit_legs`` used ``open_legs_to_close``; it must not change.

Spec basis: ADR-105, ADR-094 (a closing basket needs 0), ADR-016 to ADR-019; no broker order endpoint is called
(only the margin replay)."""
from __future__ import annotations

import asyncio
import datetime
import json
from decimal import Decimal as D
from types import SimpleNamespace

from ofo.engine.executable_price import depth_from_levels
from ofo_app import execute_plan as ep
from ofo_app.checked_basket import checked_basket
from ofo_app.routes.execute import EXIT, _wanted
from test_checked_basket import CONDOR_REPLY, Replay, catalogue, client, funds_reply, no_freeze

AT = datetime.datetime(2026, 10, 16, 15, 7, 20, tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
# held by the condor: the two shorts and the two longs (exchange_token as the catalogue knows them)
HELD = {"NSE_FO:47169": -65, "NSE_FO:47177": 65, "NSE_FO:47152": -65, "NSE_FO:47138": 65}
LAST = {47169: D("53.30"), 47177: D("17.30"), 47152: D("65.15"), 47138: D("34.00")}
GOLDEN = (
    "KiteBasket(orders=(KiteOrder(instrument_id=InstrumentId(exchange_segment='NSE_FO', exchange_toke"
    "n=47138), exchange='NFO', tradingsymbol='NIFTY26O1922550PE', transaction_type='SELL', quantity=6"
    "5, price=Decimal('33.95'), tag='Q0009030', order_type='LIMIT', product='NRML', variety='regular'"
    ", readonly=True), KiteOrder(instrument_id=InstrumentId(exchange_segment='NSE_FO', exchange_token"
    "=47152), exchange='NFO', tradingsymbol='NIFTY26O1922750PE', transaction_type='BUY', quantity=65,"
    " price=Decimal('65.20'), tag='Q0009031', order_type='LIMIT', product='NRML', variety='regular', "
    "readonly=True), KiteOrder(instrument_id=InstrumentId(exchange_segment='NSE_FO', exchange_token=4"
    "7169), exchange='NFO', tradingsymbol='NIFTY26O1923150CE', transaction_type='BUY', quantity=65, p"
    "rice=Decimal('53.35'), tag='Q0009032', order_type='LIMIT', product='NRML', variety='regular', re"
    "adonly=True), KiteOrder(instrument_id=InstrumentId(exchange_segment='NSE_FO', exchange_token=471"
    "77), exchange='NFO', tradingsymbol='NIFTY26O1923350CE', transaction_type='SELL', quantity=65, pr"
    "ice=Decimal('17.25'), tag='Q0009033', order_type='LIMIT', product='NRML', variety='regular', rea"
    'donly=True)))'
)


def _quote_of(instrument_id, _token):
    last = LAST[instrument_id.exchange_token]
    tick = D("0.05")
    bids = [(last - tick * i, 1000) for i in range(1, 6)]
    asks = [(last + tick * i, 1000) for i in range(1, 6)]
    depth = depth_from_levels(bids, asks)
    return ep.LegQuote(depth, AT, last, (D("0.05"), D("500")))


def _exit_basket():
    cat = catalogue()
    legs = asyncio.run(_wanted(SimpleNamespace(action=EXIT), None, HELD))
    priced = ep.price_legs("S-9", "NIFTY", legs, cat, _quote_of)
    reply = json.loads(CONDOR_REPLY)
    reply["data"]["final"]["total"] = -214.5
    order = [leg.contract for leg in priced.plan.legs]  # Zerodha lists the orders in the order they were sent
    reply["data"]["orders"].sort(key=lambda row: order.index(row["tradingsymbol"]))
    transport = Replay(funds_reply("99999999.00"), basket=json.dumps(reply))
    basket = checked_basket(priced.plan, cat, 3, margin_client=client(transport), freeze_check=no_freeze)
    return basket, transport


def test_the_condor_exit_basket_is_byte_identical_to_the_recorded_golden() -> None:
    basket, _ = _exit_basket()
    assert repr(basket) == GOLDEN


def test_the_exit_basket_closes_each_side_and_only_asks_margin_never_orders() -> None:
    basket, transport = _exit_basket()
    assert [(o.tradingsymbol, o.transaction_type, o.quantity) for o in basket.orders] == [
        ("NIFTY26O1922550PE", "SELL", 65), ("NIFTY26O1922750PE", "BUY", 65),
        ("NIFTY26O1923150CE", "BUY", 65), ("NIFTY26O1923350CE", "SELL", 65)]
    assert {m for m, _, _ in transport.calls} <= {"GET", "POST"}
    assert all("/margins" in url for _, url, _ in transport.calls)
    assert not any("/orders" in url for _, url, _ in transport.calls)
