"""W-091 core proof (REQ-054 AC-1, REQ-057, REQ-060; ADR-102, ADR-103): the owner's REAL 1-lot order replies go
through the product adapter (ofo_app/kite_replies.py) into the fill ledger and reconcile, with no scaffolding adapter.

Fixtures: tests/fixtures/kite_replies/ (recorded 2026-10-16, client id redacted; README there). Snapshot 122104 is
after the entry (BUY 65 NIFTY26O1923650CE at 5.1), 151006 after the exit (SELL 65 at 3.1). Expected values are read
from the fixture files or worked by hand: P&L = (3.1 - 5.1) x 65 = -130.00, which is Kite's flat-row `unrealised`
(-130); that row's `realised` is 0. Three money shapes: the recorder's strings, JSON numbers read with
`parse_float=Decimal`, and the kiteconnect SDK's Python floats.

The strategy record and the platform's own orders are test setup (they are the platform's state, not a Kite reply);
the record's exit is driven by hand (`observe_broker_position` + `mark_exited`): deriving it from the ledger reaching 0
is NOT built in W-091 (moved to GC-2c).
"""
from __future__ import annotations

import copy
import datetime
import json
from decimal import Decimal
from pathlib import Path

import pytest

from ofo.engine import Action, Instrument
from ofo.orders.model import Order, OrderBook, OrderState, OutOfOrderFillError, realised_pnl
from ofo.reconciliation.compare import compare
from ofo.reconciliation.positions import is_flat_row
from ofo.strategy.definition import DefinitionLeg, StrategyDefinition
from ofo.strategy.versions import ExecutionResult, Position, ResultStatus, StrategyRecord
from ofo.timeutil import IST
from ofo_app.kite_replies import (
    ContractIndex,
    KiteReplyError,
    _IndexRow,
    fill_from_trade_row,
    fills_from_reply,
    kite_money,
    orders_from_reply,
    positions_from_reply,
)

pytestmark = pytest.mark.repo_scan

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "kite_replies"
SYMBOL = "NIFTY26O1923650CE"
CONTRACT = ("NIFTY", Instrument.CE, Decimal("23650.00"), datetime.date(2026, 10, 19))
ENTRY_TRADE, EXIT_TRADE = "4484194", "5966618"
MONEY = {"price", "average_price", "last_price", "trigger_price", "close_price", "value", "pnl", "m2m", "unrealised",
         "realised", "buy_price", "buy_value", "buy_m2m", "sell_price", "sell_value", "sell_m2m", "day_buy_price",
         "day_buy_value", "day_sell_price", "day_sell_value", "overnight_value"}


def ist(text: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(text).replace(tzinfo=IST)


_now = [ist("2026-10-16 12:21:05")]  # the platform clock, moved by each test step; never the wall clock


def clock() -> datetime.datetime:
    return _now[0]


@pytest.fixture(autouse=True)
def _reset_clock():
    _now[0] = ist("2026-10-16 12:21:05")


def _recorded(name: str) -> object:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"), parse_float=Decimal)["data"]


def _map_money(node: object, convert) -> object:
    if isinstance(node, list):
        return [_map_money(n, convert) for n in node]
    if isinstance(node, dict):
        return {k: (convert(v) if k in MONEY and isinstance(v, (str, int, Decimal)) and not isinstance(v, bool)
                    else _map_money(v, convert)) for k, v in node.items()}
    return node


def _json_numbers(name: str) -> object:
    """The same reply as live Kite REST sends it: money as JSON numbers, read with parse_float=Decimal."""
    as_numbers = _map_money(copy.deepcopy(_recorded(name)), float)  # float-ok: only to WRITE the JSON
    text = json.dumps({"status": "success", "data": as_numbers})
    assert '"5.1"' not in text  # no money string is left: every figure is a JSON number
    return json.loads(text, parse_float=Decimal)["data"]


def _sdk_floats(name: str) -> object:
    """The same reply as the kiteconnect SDK hands it over: money as Python floats."""
    return _map_money(copy.deepcopy(_recorded(name)), float)  # float-ok: simulating the SDK's floats


SHAPES = {"recorded-strings": _recorded, "json-numbers": _json_numbers, "sdk-floats": _sdk_floats}


def _index() -> ContractIndex:
    slice_rows = json.loads((FIXTURES / "instruments-2026-10-16-slice.json").read_text(encoding="utf-8"),
                            parse_float=Decimal)
    return ContractIndex.from_instrument_slice(slice_rows)


def _record() -> StrategyRecord:
    definition = StrategyDefinition("NIFTY", (DefinitionLeg(Action.BUY, CONTRACT[1], CONTRACT[2], CONTRACT[3], 65),))
    record = StrategyRecord(definition, at=ist("2026-10-16 12:20:00"), clock=clock)
    v1 = record.propose_execution(at=ist("2026-10-16 12:20:10"))
    record.confirm(v1.number, at=ist("2026-10-16 12:20:20"))
    record.apply_result(ExecutionResult(1, ResultStatus.COMPLETE, Position.of({CONTRACT: 65}),
                                        ist("2026-10-16 12:20:50"), "OFS1V1L0"))
    return record


def _book(record: StrategyRecord, load) -> OrderBook:
    book = OrderBook(clock=clock)
    book.bind_strategy("S1", record)
    for row in orders_from_reply(load("orders-151006")):  # the platform registered both orders (entry, then exit)
        book.add(Order("S1", "L0", row.tradingsymbol, row.side, row.quantity, row.price, broker_order_id=row.order_id,
                       version_id="v1", client_tag=row.tag))
        book.mirror_broker_state(row.tag, OrderState.PENDING)
    return book


@pytest.mark.parametrize("shape", SHAPES)
def test_core_proof_real_order_entry_and_exit(shape):
    load = SHAPES[shape]
    index, record = _index(), _record()
    book = _book(record, load)

    # after entry (122104): ledger 65 long, broker 65 long, 0 mismatches, cumulative fills agree
    for fill in fills_from_reply(load("trades-122104")):
        book.apply_fill(fill)
    entry = positions_from_reply(load("positions-122104"), index)
    assert entry.net == {CONTRACT: 65}
    (line,) = entry.lines
    assert type(line.average_price) is Decimal and str(line.average_price) == "5.10"
    assert book.position("S1", SYMBOL) == 65
    assert compare(entry.net, {"S1": record}, at=ist("2026-10-16 12:21:04"), clock=clock).mismatches == ()
    for row in orders_from_reply(load("orders-122104")):
        assert book.reconcile_cumulative(row.order_id, row.filled_quantity, read_at=ist("2026-10-16 12:21:04")) == "ok"

    _now[0] = ist("2026-10-16 15:10:10")
    # after exit (151006): the whole trades reply again (entry replayed = no-op), ledger flat, broker flat row dropped
    for fill in fills_from_reply(load("trades-151006")) + fills_from_reply(load("trades-122104")):
        book.apply_fill(fill)
    assert book.position("S1", SYMBOL) == 0
    assert sorted(f.trade_id for f in book.raw_fills()) == [ENTRY_TRADE, EXIT_TRADE]
    exit_read = positions_from_reply(load("positions-151006"), index)
    assert exit_read.net == {} and exit_read.lines == ()
    for row in orders_from_reply(load("orders-151006")):
        assert book.reconcile_cumulative(row.order_id, row.filled_quantity, read_at=ist("2026-10-16 15:10:06")) == "ok"
    record.observe_broker_position(Position.of(exit_read.net), at=ist("2026-10-16 15:10:06"), reference="obs-151006")
    record.mark_exited(at=ist("2026-10-16 15:10:07"), actor="test", resolution="exit order OFS1V2L0 filled")
    assert compare(exit_read.net, {"S1": record}, at=ist("2026-10-16 15:10:08"), clock=clock).mismatches == ()

    # P&L from the fills (ADR-102) equals Kite's own flat-row figure; that figure is `unrealised`, `realised` is 0
    (flat_row,) = load("positions-151006")["net"]
    pnl = realised_pnl(book.raw_fills())
    assert type(pnl) is Decimal and str(pnl) == "-130.00"
    assert pnl == kite_money(flat_row["unrealised"], "unrealised") == Decimal("-130")
    assert kite_money(flat_row["realised"], "realised") == 0


@pytest.mark.parametrize("shape", SHAPES)
def test_trade_rows_become_exact_ist_fills(shape):
    buy, sell = fills_from_reply(SHAPES[shape]("trades-151006"))
    assert (buy.trade_id, buy.broker_order_id, buy.side, buy.quantity) == (ENTRY_TRADE, "261016170576173", Action.BUY,
                                                                           65)
    assert type(buy.price) is Decimal and str(buy.price) == "5.10" and str(sell.price) == "3.10"
    assert buy.timestamp == datetime.datetime(2026, 10, 16, 12, 20, 50, tzinfo=IST)
    assert sell.timestamp == datetime.datetime(2026, 10, 16, 15, 9, 52, tzinfo=IST)
    assert buy.timestamp.utcoffset() == datetime.timedelta(hours=5, minutes=30)


def test_time_only_order_timestamp_is_never_used_and_a_time_only_fill_timestamp_is_refused():
    row = dict(_recorded("trades-122104")[0])
    assert row["order_timestamp"] == "12:20:50"  # the real reply: time-only
    assert fill_from_trade_row({**row, "order_timestamp": "junk"}) == fill_from_trade_row(row)
    for partial in ("12:20:50", "2026-10-16", "2026-10-16T12:20:50+00:00", "2026-10-16 12:20"):
        with pytest.raises(KiteReplyError, match="fill_timestamp"):  # never midnight, never another zone's text
            fill_from_trade_row({**row, "fill_timestamp": partial})
    with pytest.raises(KiteReplyError, match="fill_timestamp"):
        fill_from_trade_row({k: v for k, v in row.items() if k != "fill_timestamp"})
    naive_sdk = fill_from_trade_row({**row, "fill_timestamp": datetime.datetime(2026, 10, 16, 12, 20, 50)})  # noqa: DTZ001 SDK shape
    assert naive_sdk.timestamp == datetime.datetime(2026, 10, 16, 12, 20, 50, tzinfo=IST)


def test_flat_row_is_no_position_not_an_error():
    (flat_row,) = _recorded("positions-151006")["net"]
    assert flat_row["quantity"] == 0 and flat_row["average_price"] == 0  # the real flat row
    assert is_flat_row(flat_row)
    assert not is_flat_row({**flat_row, "quantity": False})
    read = positions_from_reply({"net": [flat_row]}, _index())
    assert read.net == {} and read.lines == ()


def test_symbol_not_in_slice_is_refused():
    (row,) = _recorded("positions-122104")["net"]
    with pytest.raises(KiteReplyError, match="matches 0"):
        positions_from_reply({"net": [{**row, "tradingsymbol": "NIFTY26O1923700CE"}]}, _index())
    with pytest.raises(KiteReplyError, match="matches 0"):
        positions_from_reply({"net": [{**row, "instrument_token": 12080387}]}, _index())


def test_symbol_matching_two_rows_is_refused():
    (row,) = _recorded("positions-122104")["net"]
    two = ContractIndex([_IndexRow("12080386", SYMBOL, CONTRACT), _IndexRow("12080386", SYMBOL, CONTRACT)])
    with pytest.raises(KiteReplyError, match="matches 2"):
        two.resolve(row)
    by_symbol = ContractIndex([_IndexRow("1", SYMBOL, CONTRACT), _IndexRow("2", SYMBOL, CONTRACT)])
    with pytest.raises(KiteReplyError, match="matches 2"):
        by_symbol.resolve({k: v for k, v in row.items() if k != "instrument_token"})
    assert by_symbol.resolve(row | {"instrument_token": 2}) == CONTRACT  # the token picks one: not a guess


def test_out_of_order_exit_fill_is_refused_and_blocks_never_a_short():
    record = _record()
    book = _book(record, _recorded)
    _now[0] = ist("2026-10-16 15:10:10")
    buy, sell = fills_from_reply(_recorded("trades-151006"))
    with pytest.raises(OutOfOrderFillError) as refused:
        book.apply_fill(sell)
    assert refused.value.args == ("out_of_order_fill", "5966618", "SELL", 65, 0, -65)
    assert book.position("S1", SYMBOL) == 0  # never -65
    assert book.raw_fills() == ()
    assert book.is_submit_blocked("S1")
    assert book.reconciliation_events("S1")[-1].reason == "out_of_order_fill"
    sell_order = sell.broker_order_id
    assert book.reconcile_cumulative(sell_order, 65, read_at=ist("2026-10-16 15:10:06")) == "missing_trades"
    book.apply_fill(buy)  # the missing fill arrives; the exit fill is then accepted
    book.apply_fill(sell)
    book.apply_fill(sell)  # replay: no-op
    assert book.position("S1", SYMBOL) == 0 and len(book.raw_fills()) == 2


def test_float_money_shapes():
    assert kite_money(float("5.1"), "p") == Decimal("5.10") and str(kite_money(float("5.1"), "p")) == "5.10"
    assert str(kite_money(Decimal("68498.85000000001"), "p")) == "68498.85"
    assert str(kite_money("331.5", "p")) == "331.50" and kite_money(0, "p") == 0
    for bad in (float("nan"), float("inf"), float("-inf"), Decimal("NaN"), "5.1e0", " 5.1", "", True, None, "abc"):
        with pytest.raises(KiteReplyError):
            kite_money(bad, "p")


def test_missing_or_unknown_fields_fail_closed():
    trade = dict(_recorded("trades-122104")[0])
    for field in ("trade_id", "order_id", "tradingsymbol", "transaction_type", "quantity", "average_price"):
        with pytest.raises(KiteReplyError):
            fill_from_trade_row({k: v for k, v in trade.items() if k != field})
    with pytest.raises(KiteReplyError, match="BUY or SELL"):
        fill_from_trade_row({**trade, "transaction_type": "SHORT"})
    (pos,) = _recorded("positions-122104")["net"]
    with pytest.raises(KiteReplyError):
        positions_from_reply({"net": [{k: v for k, v in pos.items() if k != "average_price"}]}, _index())
    with pytest.raises(KiteReplyError):
        positions_from_reply({"day": []}, _index())


@pytest.mark.parametrize("row", ["x", None, 5, ["OFS1V1L0"]])
def test_an_orders_row_that_is_not_a_mapping_is_refused_not_a_crash(row):
    """W-111 round 2 (review MINOR 2): only a mapping is an orders row; anything else raises KiteReplyError (the
    route's 409), never AttributeError (a 500)."""
    with pytest.raises(KiteReplyError, match="must be a mapping"):
        orders_from_reply([row])
    with pytest.raises(KiteReplyError, match="must be a mapping"):
        orders_from_reply([*_recorded("orders-122104"), row])


def test_fixtures_hold_no_client_id():
    client_id = "DA" + "1707"
    files = sorted(FIXTURES.iterdir())
    assert len(files) >= 8  # the W-091 recordings at least: a moved or empty folder must not pass vacuously
    for path in files:
        assert client_id not in path.read_text(encoding="utf-8"), path.name


def test_an_average_price_finer_than_a_paisa_is_kept_exact():
    """ADR-102: a broker average (5.125 after two fills) is kept as Zerodha sent it - not rounded, not refused."""
    from ofo_app.kite_replies import kite_money  # noqa: PLC0415

    assert kite_money("5.125", "average_price", exact=True) == Decimal("5.125")
    assert str(kite_money(5.125, "average_price", exact=True)) == "5.125"
    assert kite_money("5.125", "price") == Decimal("5.13")  # a money figure still rounds (ADR-101)
    with pytest.raises(ValueError):
        kite_money(float("nan"), "average_price", exact=True)


def test_integer_money_and_overflow_in_exact_mode_fail_cleanly():
    """Tier A review MAJOR: live Kite sends "average_price": 0 (a JSON int) on every open/cancelled order."""
    from ofo_app.kite_replies import KiteReplyError, kite_money  # noqa: PLC0415

    assert kite_money(0, "average_price", exact=True) == Decimal("0.00")
    assert kite_money(5, "average_price", exact=True) == Decimal("5.00")
    with pytest.raises(KiteReplyError):
        kite_money(Decimal("1E+30"), "average_price", exact=True)


def test_an_unfilled_order_row_with_integer_zero_average_parses():
    """The real order rows as live Kite sends them: an OPEN order has the JSON integer 0 as its average price."""
    from ofo_app.kite_replies import order_from_row  # noqa: PLC0415

    row = json.loads((FIXTURES / "orders-122104.json").read_text(encoding="utf-8"), parse_float=Decimal)
    rows = row["data"] if isinstance(row, dict) and "data" in row else row
    first = dict(rows[0])
    first["average_price"] = 0
    first["status"] = "OPEN"
    assert order_from_row(first).average_price == Decimal("0.00")


# ---- rows the platform can never own (GC-3L 2026-10-19: equity CNC rows refused the whole reply) --------------------

OCT_CE = ("NIFTY", Instrument.CE, Decimal("24000"), datetime.date(2026, 10, 27))


def _oct_index() -> ContractIndex:
    return ContractIndex([_IndexRow("13156354", "NIFTY26OCT24000CE", OCT_CE)])


def _with_stocks() -> dict:
    """The 2026-10-19 reply: two equity CNC rows (shaped from the live read) + the real saved NIFTY row (flat)."""
    return _recorded("positions-20261019-with-stocks")


def test_equity_rows_are_ignored_not_refused():
    data = _with_stocks()
    assert [(r["tradingsymbol"], r["product"], r["quantity"]) for r in data["net"]] == [
        ("FRANKLININD", "CNC", -201900), ("LIQUIDBEES", "CNC", -2), ("NIFTY26OCT24000CE", "NRML", 0)]
    read = positions_from_reply(data, _oct_index())
    assert read.net == {} and read.lines == ()
    assert read.ignored == ("NSE:FRANKLININD", "NSE:LIQUIDBEES")
    for exchange in ("BSE", "MCX", "CDS", "BCD", "NCO"):  # any exchange outside the F&O allowlist
        stock = {**data["net"][0], "exchange": exchange}
        assert positions_from_reply({"net": [stock]}, _oct_index()).ignored == (f"{exchange}:FRANKLININD",)


def test_the_platforms_own_row_is_still_seen_next_to_stocks():
    data = _with_stocks()
    data["net"][2] = {**data["net"][2], "quantity": 65, "average_price": 7}
    read = positions_from_reply(data, _oct_index())
    assert read.net == {OCT_CE: 65}
    assert [line.net_quantity for line in read.lines] == [65]
    assert read.ignored == ("NSE:FRANKLININD", "NSE:LIQUIDBEES")


def test_a_supported_underlying_row_missing_from_the_catalogue_still_refuses():
    nifty = {**_with_stocks()["net"][2], "quantity": 65, "average_price": 7}
    with pytest.raises(KiteReplyError, match="matches 0"):  # could be ours (a catalogue gap): never skipped
        positions_from_reply({"net": [nifty]}, _index())
    with pytest.raises(KiteReplyError, match="matches 0"):
        positions_from_reply({"net": [{**nifty, "tradingsymbol": "NIFTY26O2724000CE", "instrument_token": 1}]},
                             _oct_index())
    sensex = {**nifty, "exchange": "BFO", "tradingsymbol": "SENSEX26OCT80000PE", "instrument_token": 2}
    with pytest.raises(KiteReplyError, match="matches 0"):
        positions_from_reply({"net": [sensex]}, _oct_index())


def test_a_row_with_no_or_an_unshaped_exchange_or_fo_symbol_refuses():
    stock = _with_stocks()["net"][0]
    for bad in ({k: v for k, v in stock.items() if k != "exchange"}, {**stock, "exchange": ""},
                {**stock, "exchange": None}, {**stock, "exchange": " NSE"}):
        with pytest.raises(KiteReplyError, match="exchange"):  # never read as "not ours"
            positions_from_reply({"net": [bad]}, _oct_index())
    nifty = {**_with_stocks()["net"][2], "quantity": 65, "average_price": 7}
    with pytest.raises(KiteReplyError, match="F&O symbol"):  # an NFO row whose underlying cannot be read
        positions_from_reply({"net": [{**nifty, "tradingsymbol": "NIFTY-OCT-CE"}]}, _oct_index())


def test_other_underlying_fo_rows_are_ignored():
    nifty = {**_with_stocks()["net"][2], "quantity": 30, "average_price": 7}
    others = [("NFO", "BANKNIFTY26OCT56000CE"), ("NFO", "BANKNIFTY26O2856000PE"), ("NFO", "RELIANCE26OCTFUT"),
              ("NFO", "NIFTYNXT5026OCT70000CE"), ("NFO", "FINNIFTY26OCT27000PE"), ("BFO", "SENSEX5026OCT28000CE"),
              ("BFO", "BANKEX26OCT60000CE"), ("BFO", "NIFTY26OCT24000CE")]  # NIFTY is an NFO contract, never BFO
    rows = [{**nifty, "exchange": ex, "tradingsymbol": sym, "instrument_token": 7} for ex, sym in others]
    read = positions_from_reply({"net": [*rows, {**nifty, "quantity": 65}]}, _oct_index())
    assert read.ignored == tuple(f"{ex}:{sym}" for ex, sym in others)
    assert read.net == {OCT_CE: 65}
    weekly_nifty = {**nifty, "tradingsymbol": "NIFTY26O1923650CE", "instrument_token": 12080386}
    assert positions_from_reply({"net": [weekly_nifty]}, _index()).ignored == ()  # weekly symbol: ours, resolved
    fut = {**nifty, "tradingsymbol": "NIFTY26OCTFUT", "instrument_token": 3}
    with pytest.raises(KiteReplyError, match="matches 0"):  # a NIFTY future is ours: resolved, not skipped
        positions_from_reply({"net": [fut]}, _oct_index())


def test_an_unknown_exchange_refuses_never_ignored():
    """Tier A review MAJOR: only the listed never-ours exchanges are skipped; a code that is neither those nor an F&O
    exchange (a case slip, a new code) could be ours and refuses the read."""
    nifty = {**_with_stocks()["net"][2], "quantity": 65, "average_price": 7}
    for exchange in ("nfo", "NSEFO", "XYZ", "bfo"):
        with pytest.raises(KiteReplyError, match="unknown exchange"):
            positions_from_reply({"net": [{**nifty, "exchange": exchange}]}, _oct_index())
    stock = _with_stocks()["net"][0]
    for exchange in ("NSE", "BSE"):
        assert positions_from_reply({"net": [{**stock, "exchange": exchange}]}, _oct_index()).ignored == (
            f"{exchange}:FRANKLININD",)


def test_an_ignored_row_without_a_symbol_refuses():
    stock = {k: v for k, v in _with_stocks()["net"][0].items() if k != "tradingsymbol"}
    with pytest.raises(KiteReplyError, match="tradingsymbol"):  # never a KeyError, never an unnamed skip
        positions_from_reply({"net": [stock]}, _oct_index())


def test_ignored_rows_are_logged_once_per_read_without_money(caplog):
    from ofo_app.kite_replies import log_ignored  # noqa: PLC0415

    read = positions_from_reply(_with_stocks(), _oct_index())
    with caplog.at_level("INFO", logger="ofo_app.kite_replies"):
        log_ignored(read, "execute strategy 15")
        log_ignored(positions_from_reply({"net": []}, _oct_index()), "execute strategy 15")  # nothing ignored: silent
    assert [r.getMessage() for r in caplog.records] == [
        "execute strategy 15: positions read ignored 2 non-platform rows: NSE:FRANKLININD, NSE:LIQUIDBEES"]
