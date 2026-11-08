"""W-093 AC-3 / AC-4: the Kite read door (orders, trades, positions) tested with the recorded 2026-10-16 replies.

No network, no database. A replay transport serves the recorded reply files byte for byte. The core test feeds the
door's output into ``ofo_app.kite_replies`` and expects the owner's real order: tag OFS1V1L0 filled 65, trade 4484194,
a 65-unit NIFTY26O1923650CE position.
"""
import dataclasses
import json
import logging
import re
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode

import pytest
from ofo.broker.kite_endpoints import ALLOWED_CALLS
from ofo.broker.kite_http import KiteCallRefused, check_call
from ofo.engine import Instrument
from ofo.execution.basket import TagParts, parse_tag
from ofo_app import broker_sync, kite_reads
from ofo_app.kite_margin import KiteMarginError
from ofo_app.kite_reads import Holding, HoldingChange, KiteReadError, KiteReads, holdings_unchanged
from ofo_app.kite_replies import ContractIndex, fills_from_reply, orders_from_reply, positions_from_reply

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "kite_replies"
SECRET = "tok-SECRET-123"
READS = frozenset({("GET", "/orders"), ("GET", "/trades"), ("GET", "/portfolio/positions")})
BASE = "https://api.kite.trade"
CONTRACT = ("NIFTY", Instrument.CE, Decimal("23650.00"), __import__("datetime").date(2026, 10, 19))


def recorded_text(name: str) -> str:
    return (FIXTURES / f"{name}.json").read_text(encoding="utf-8")


class Replay:
    """A transport that serves a text per path and records what it was asked."""

    def __init__(self, by_path: dict[str, str] | None = None, status: int = 200, text: str = "",
                 raises: Exception | None = None) -> None:
        self.by_path, self.status, self.text, self.raises, self.calls = by_path or {}, status, text, raises, []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        if self.raises:
            raise self.raises
        return self.status, self.by_path.get(url.removeprefix(BASE), self.text)


def client(transport) -> KiteReads:
    return KiteReads(api_key="key", access_token=SECRET, transport=transport)


def entry_replay(suffix: str = "122104") -> Replay:
    return Replay({"/orders": recorded_text(f"orders-{suffix}"), "/trades": recorded_text(f"trades-{suffix}"),
                   "/portfolio/positions": recorded_text(f"positions-{suffix}")})


def index() -> ContractIndex:
    rows = json.loads(recorded_text("instruments-2026-10-16-slice"), parse_float=Decimal)
    return ContractIndex.from_instrument_slice(rows)


def test_core_recorded_entry_replies_through_the_door() -> None:
    """AC-3 core: the three recorded entry replies, through the door, become tag OFS1V1L0 filled 65, trade 4484194,
    net {NIFTY26O1923650CE: 65}."""
    door = client(entry_replay())
    (order,) = orders_from_reply(door.fetch_orders())
    (fill,) = fills_from_reply(door.fetch_trades())
    read = positions_from_reply(door.fetch_positions(), index())
    assert (order.tag, order.filled_quantity) == ("OFS1V1L0", 65)
    assert fill.trade_id == "4484194"
    assert read.net == {CONTRACT: 65}
    assert parse_tag(order.tag) == TagParts(1, 1, 0)  # strategy 1, plan 1, leg 0


def test_exit_order_tag_decodes_to_plan_two() -> None:
    """AC-3: the recorded exit order (orders-151006) carries OFS1V2L0: strategy 1, plan 2, leg 0."""
    rows = orders_from_reply(client(entry_replay("151006")).fetch_orders())
    tags = {r.tag for r in rows}
    assert "OFS1V2L0" in tags
    assert parse_tag("OFS1V2L0") == TagParts(1, 2, 0)


def test_flat_position_after_exit_is_empty_net() -> None:
    """AC-3: the 151006 (after exit) positions reply is a flat row: net == {}."""
    read = positions_from_reply(client(entry_replay("151006")).fetch_positions(), index())
    assert read.net == {} and read.lines == ()


def test_money_as_json_numbers_is_exact_decimal() -> None:
    """AC-3: live REST sends money as JSON numbers; parse_float=Decimal keeps 5.1 as Decimal('5.1'), never a float."""
    text = '{"status": "success", "data": [{"order_id": "1", "price": 5.1, "average_price": 5.10, "quantity": 65}]}'
    (row,) = client(Replay(text=text)).fetch_orders()
    assert type(row["price"]) is Decimal and row["price"] == Decimal("5.1")
    assert type(row["average_price"]) is Decimal and str(row["average_price"]) == "5.10"
    assert row["quantity"] == 65 and type(row["quantity"]) is int


def test_requests_are_exactly_the_allow_listed_reads() -> None:
    """AC-4: each fetch makes one GET to its allow-listed path; the token is only in the Authorization header."""
    fake = entry_replay()
    door = client(fake)
    door.fetch_orders(), door.fetch_trades(), door.fetch_positions()
    assert [(m, u) for m, u, _, _ in fake.calls] == [
        ("GET", f"{BASE}/orders"), ("GET", f"{BASE}/trades"), ("GET", f"{BASE}/portfolio/positions")]
    assert {(m, u.removeprefix(BASE)) for m, u, _, _ in fake.calls} == READS
    assert all(b is None and h["Authorization"] == f"token key:{SECRET}" and h["X-Kite-Version"] == "3"
               for _, _, h, b in fake.calls)
    assert all(SECRET not in u for _, u, _, _ in fake.calls)


def test_allow_list_entry_is_exactly_the_three_reads() -> None:
    """AC-4: the module's ALLOWED_CALLS entry is the three reads and nothing else."""
    # W-099 added the quote read, W-106 the holdings read, W-131 the profile read
    assert ALLOWED_CALLS["ofo_app/kite_reads.py"] == READS | {("GET", "/quote"), ("GET", "/portfolio/holdings"),
                                                              ("GET", "/user/profile")}


@pytest.mark.parametrize("method,path", [("POST", "/orders"), ("POST", "/orders/regular"), ("DELETE", "/orders/1"),
                                         ("GET", "/orders/regular"), ("GET", "/orders/"), ("GET", "/orders/123"),
                                         ("PUT", "/trades"), ("POST", "/portfolio/holdings"),
                                         ("DELETE", "/portfolio/holdings"), ("GET", "/portfolio/holdings/x"),
                                         ("GET", "/portfolio/auctions")])
def test_door_refuses_anything_else_before_the_transport(method, path) -> None:
    """AC-4: a method or path outside the allow-list is refused and the transport is never called."""
    fake = entry_replay()
    with pytest.raises(KiteReadError) as raised:
        client(fake)._data(method, path)
    assert raised.value.code == "kite_read_refused" and fake.calls == []


def test_a_changed_path_constant_is_refused_before_the_transport(monkeypatch) -> None:
    """AC-4: if a read's path drifts to something not allow-listed, the fetch refuses without sending."""
    monkeypatch.setattr(kite_reads, "ORDERS_PATH", "/orders/regular")
    fake = entry_replay()
    with pytest.raises(KiteReadError) as raised:
        client(fake).fetch_orders()
    assert raised.value.code == "kite_read_refused" and fake.calls == []


@pytest.mark.parametrize("status,code", [(403, "kite_read_token"), (429, "kite_read_busy"), (400, "kite_read_refused"),
                                         (404, "kite_read_refused"), (500, "kite_read_unavailable"),
                                         (503, "kite_read_unavailable")])
def test_http_errors_map_to_codes(status, code) -> None:
    """AC-3: a non-200 status fails closed with its code."""
    with pytest.raises(KiteReadError) as raised:
        client(Replay(status=status, text="{}")).fetch_trades()
    assert raised.value.code == code


def test_token_exception_body_maps_to_token_code() -> None:
    """AC-3: error_type TokenException is a token error whatever the status."""
    text = '{"status": "error", "error_type": "TokenException", "message": "Incorrect api_key or access_token"}'
    with pytest.raises(KiteReadError) as raised:
        client(Replay(status=400, text=text)).fetch_orders()
    assert raised.value.code == "kite_read_token"


@pytest.mark.parametrize("exc", [OSError("boom"), TimeoutError(), RuntimeError("x"),
                                 KiteMarginError("kite_margin_unavailable")])
def test_transport_failure_is_unavailable(exc) -> None:
    """AC-3: whatever the transport raises is "not confirmed"."""
    with pytest.raises(KiteReadError) as raised:
        client(Replay(raises=exc)).fetch_orders()
    assert raised.value.code == "kite_read_unavailable"


def test_door_refusal_in_the_transport_is_refused() -> None:
    """AC-4: the urllib transport's own door refusal (KiteCallRefused / kite_margin_refused) is kite_read_refused."""
    for exc in (KiteCallRefused("x"), KiteMarginError("kite_margin_refused")):
        with pytest.raises(KiteReadError) as raised:
            client(Replay(raises=exc)).fetch_orders()
        assert raised.value.code == "kite_read_refused"


@pytest.mark.parametrize("text", ["", "not json", "<html>", pytest.param("[" * 100000, id="deeply-nested")])
def test_junk_body_is_unavailable(text) -> None:
    """AC-3: a body that is not JSON (or nests past the recursion limit) is kite_read_unavailable, never a crash."""
    with pytest.raises(KiteReadError) as raised:
        client(Replay(text=text)).fetch_orders()
    assert raised.value.code == "kite_read_unavailable"


@pytest.mark.parametrize("text", [
    '{"status": "error", "data": []}',                      # HTTP 200 but status error
    '{"data": []}',                                          # no status
    '{"status": "success"}',                                 # no data
    '{"status": "success", "data": {}}',                     # orders must be a list
    '{"status": "success", "data": null}',
    '{"status": "success", "data": "x"}',
    '{"status": "success", "data": [1, 2]}',                 # rows must be objects
    '[]',                                                    # reply is not an object
])
def test_bad_reply_for_a_list_endpoint(text) -> None:
    """AC-3: orders and trades need status success and a list of rows; anything else is kite_read_bad_reply."""
    for fetch in (client(Replay(text=text)).fetch_orders, client(Replay(text=text)).fetch_trades):
        with pytest.raises(KiteReadError) as raised:
            fetch()
        assert raised.value.code == "kite_read_bad_reply"


@pytest.mark.parametrize("data", [
    '{"day": []}',                                  # no net
    '{"net": []}',                                  # no day
    '{"net": {}, "day": []}',                       # net not a list
    '{"net": [], "day": "x"}',
    '[]',                                           # data is a list
    'null',
    '{"net": [1], "day": []}',                      # rows must be objects
])
def test_bad_reply_for_positions(data) -> None:
    """AC-3: positions data must be a mapping with net and day lists of rows."""
    with pytest.raises(KiteReadError) as raised:
        client(Replay(text='{"status": "success", "data": %s}' % data)).fetch_positions()  # noqa: UP031
    assert raised.value.code == "kite_read_bad_reply"


def test_positions_with_empty_lists_is_valid() -> None:
    """AC-3: a flat account (net and day empty) is a valid reply, not an error."""
    assert client(Replay(text='{"status": "success", "data": {"net": [], "day": []}}')).fetch_positions() == {
        "net": [], "day": []}


def test_the_token_appears_nowhere(caplog) -> None:
    """AC-3: not in repr(client), not in any exception text, not in a log line."""
    caplog.set_level(logging.DEBUG)
    door = client(Replay(status=500, text=SECRET))
    assert SECRET not in repr(door) and SECRET not in str(vars(door).get("_base", ""))
    for fake in (Replay(status=403, text=SECRET), Replay(status=500, text=SECRET), Replay(text=SECRET),
                 Replay(raises=RuntimeError(SECRET)), Replay(raises=KiteMarginError(SECRET)),
                 Replay(text='{"status": "error", "message": "%s"}' % SECRET)):
        with pytest.raises(KiteReadError) as raised:
            client(fake).fetch_orders()
        assert SECRET not in str(raised.value) and SECRET not in repr(raised.value.args)
        assert raised.value.__cause__ is None
        assert raised.value.__context__ is None or raised.value.__suppress_context__  # the transport's text is hidden
    assert SECRET not in caplog.text
    assert re.search(r"api_key|access_token", repr(door)) is None


def test_error_is_closed_shape() -> None:
    """AC-3: an error carries a code and nothing else."""
    err = KiteReadError("kite_read_bad_reply")
    assert err.code == "kite_read_bad_reply" and err.args == ("kite_read_bad_reply",)


# ---- W-106: GET /portfolio/holdings and the ADR-097 (4) before/after comparison -----------------------------------
QUANTITIES = ("quantity", "t1_quantity", "used_quantity", "authorised_quantity", "collateral_quantity")
HOLDINGS_FIELDS = ("tradingsymbol", "exchange", "isin", *QUANTITIES)
HOLDINGS_URL = "/portfolio/holdings"


def holdings_replay(reply: object | None = None) -> Replay:
    text = recorded_text("holdings-documented") if reply is None else json.dumps(reply)
    return Replay({HOLDINGS_URL: text})


def documented_rows() -> list[dict]:
    return json.loads(recorded_text("holdings-documented"))["data"]


def holding(symbol="INFY", exchange="NSE", isin="INE009A01021", quantity=10, t1=3) -> Holding:
    return Holding(symbol, exchange, isin, quantity, t1, 0, 0, 0)


def test_core_documented_holdings_reply_through_the_door() -> None:
    """AC-4 core: the documented reply, through the door, becomes exactly the eight fields per row; nothing more."""
    fake = holdings_replay()
    rows = client(fake).fetch_holdings()
    assert rows == (Holding("GOLDBEES", "BSE", "INF204KB17I5", 2, 0, 0, 0, 0),
                    Holding("INFY", "NSE", "INE009A01021", 10, 3, 0, 0, 0))
    assert [f.name for f in dataclasses.fields(Holding)] == list(HOLDINGS_FIELDS)  # no price / P&L field exists
    assert [(m, u, b) for m, u, _, b in fake.calls] == [("GET", BASE + HOLDINGS_URL, None)]


@pytest.mark.parametrize("field", HOLDINGS_FIELDS)
def test_a_row_missing_any_one_field_is_refused(field) -> None:
    """AC-4: every one of the eight fields removed in turn -> the whole read fails."""
    rows = documented_rows()
    del rows[1][field]
    with pytest.raises(KiteReadError) as raised:
        client(holdings_replay({"status": "success", "data": rows})).fetch_holdings()
    assert raised.value.code == "kite_read_bad_reply"


WRONG_TYPES = [None, -1, True, False, 10.5, 10.0, "10", "", "  ", [], {}, [10]]


@pytest.mark.parametrize("field", HOLDINGS_FIELDS)
@pytest.mark.parametrize("wrong", WRONG_TYPES, ids=repr)
def test_every_field_given_a_wrong_type_is_refused(field, wrong) -> None:
    """AC-4: allow-list of types (text for the three names, a JSON integer for the two quantities); everything else,
    including 10.5, 10.0, the string "10" and a bool, refuses."""
    if wrong == "10" and field not in QUANTITIES:
        return  # text is the right type for a name
    rows = documented_rows()
    rows[1][field] = wrong
    with pytest.raises(KiteReadError) as raised:
        client(holdings_replay({"status": "success", "data": rows})).fetch_holdings()
    assert raised.value.code == "kite_read_bad_reply"


@pytest.mark.parametrize("data", [None, {}, {"net": []}, "x", 5, [None], [[]], ["INFY"]], ids=repr)
def test_a_data_that_is_not_a_list_of_objects_is_refused(data) -> None:
    """AC-4: a non-list data (or non-object rows) raises; never an empty tuple."""
    with pytest.raises(KiteReadError) as raised:
        client(holdings_replay({"status": "success", "data": data})).fetch_holdings()
    assert raised.value.code == "kite_read_bad_reply"


def test_two_rows_with_one_key_are_refused() -> None:
    """AC-4: the same (exchange, tradingsymbol, isin) twice is ambiguous; the read fails."""
    row = documented_rows()[1]
    with pytest.raises(KiteReadError) as raised:
        client(holdings_replay({"status": "success", "data": [row, dict(row, quantity=11)]})).fetch_holdings()
    assert raised.value.code == "kite_read_bad_reply"


def test_an_empty_list_is_no_holdings_and_a_failed_read_is_an_error() -> None:
    """AC-4: [] is a valid answer (an empty tuple); a 500, a 403 or a non-success status raises instead."""
    assert client(holdings_replay({"status": "success", "data": []})).fetch_holdings() == ()
    for fake in (Replay(status=500, text="x"), Replay(status=403, text="x"),
                 holdings_replay({"status": "error", "data": []})):
        with pytest.raises(KiteReadError):
            client(fake).fetch_holdings()


@pytest.mark.parametrize("target", [HOLDINGS_URL + "?x=1", HOLDINGS_URL + "?", HOLDINGS_URL + "#f",
                                    "/portfolio/holdings%2Fx", "/portfolio%2Fholdings"])
def test_door_refuses_a_query_or_fragment_on_holdings(target) -> None:
    """AC-4: GET /portfolio/holdings?x=1 (and a fragment / escaped variant) is refused before the transport."""
    fake = holdings_replay()
    with pytest.raises(KiteReadError) as raised:
        client(fake)._data("GET", target)
    assert raised.value.code == "kite_read_refused" and fake.calls == []


def test_holdings_is_allow_listed_for_the_read_module_only() -> None:
    """AC-4: ("GET", "/portfolio/holdings") is in kite_reads' entry and in no other module's."""
    owners = [m for m, calls in ALLOWED_CALLS.items() if ("GET", HOLDINGS_URL) in calls]
    assert owners == ["ofo_app/kite_reads.py"]
    assert not any(method != "GET" and path.startswith("/portfolio")
                   for calls in ALLOWED_CALLS.values() for method, path in calls)


def test_a_changed_holdings_path_constant_is_refused_before_the_transport(monkeypatch) -> None:
    """AC-4: if HOLDINGS_PATH drifts off the allow-list, fetch_holdings refuses without sending."""
    monkeypatch.setattr(kite_reads, "HOLDINGS_PATH", "/portfolio/holdings/all")
    fake = holdings_replay()
    with pytest.raises(KiteReadError) as raised:
        client(fake).fetch_holdings()
    assert raised.value.code == "kite_read_refused" and fake.calls == []


def test_unchanged_holdings_compare_equal_whatever_the_order() -> None:
    """AC-4: the same rows in another order -> no differences."""
    a, b = holding(), holding("GOLDBEES", "BSE", "INF204KB17I5", 2, 0)
    assert holdings_unchanged((a, b), (b, a)) == ()
    assert holdings_unchanged((), ()) == ()


@pytest.mark.parametrize("field,value", [(f, 7) for f in QUANTITIES])
def test_a_changed_quantity_is_reported(field, value) -> None:
    """AC-4: a differing quantity or t1_quantity names the row, with both versions."""
    before = holding()
    after = dataclasses.replace(before, **{field: value})
    assert holdings_unchanged((before,), (after,)) == (HoldingChange(before.key, before, after),)


def test_an_added_and_a_removed_row_are_reported() -> None:
    """AC-4: a row only in `after` has before=None; a row only in `before` has after=None."""
    kept, gone, new = holding(), holding("TCS", "NSE", "INE467B01029"), holding("SBIN", "NSE", "INE062A01020")
    changes = holdings_unchanged((kept, gone), (kept, new))
    assert changes == (HoldingChange(new.key, None, new), HoldingChange(gone.key, gone, None))  # sorted by key


def test_holdings_unchanged_refuses_duplicate_keys() -> None:
    """AC-4: two rows with one key make the comparison ambiguous -> ValueError, not a silent last-one-wins."""
    with pytest.raises(ValueError):
        holdings_unchanged((holding(), holding(quantity=1)), ())
    with pytest.raises(ValueError):
        holdings_unchanged((), (holding(), holding(quantity=1)))


# ---- W-089: "Last successful sync" is noted only by a read whose reply parsed and passed its shape checks ----------

OK_LIST = '{"status": "success", "data": []}'
OK_POSITIONS = '{"status": "success", "data": {"net": [], "day": []}}'
FETCHES = {
    "orders": (lambda c: c.fetch_orders(), OK_LIST),
    "trades": (lambda c: c.fetch_trades(), OK_LIST),
    "positions": (lambda c: c.fetch_positions(), OK_POSITIONS),
    "holdings": (lambda c: c.fetch_holdings(), OK_LIST),
    "quote": (lambda c: c.fetch_circuit_bands(["NFO:X"]), '{"status": "success", "data": {}}'),
}


def _failure(kind: str) -> Replay:
    return {
        "bad_reply": Replay(status=200, text='{"status": "error", "data": []}'),
        "403": Replay(status=403, text="{}"),
        "500": Replay(status=500, text="{}"),
        "transport_error": Replay(raises=OSError("down")),
        "bad_json": Replay(status=200, text="not json"),
        "bad_shape": Replay(status=200, text='{"status": "success", "data": "x"}'),
    }[kind]


@pytest.fixture
def clean_sync():
    broker_sync.forget()
    yield broker_sync
    broker_sync.forget()


@pytest.mark.parametrize("name", sorted(FETCHES))
def test_a_successful_read_sets_the_last_read(clean_sync, name) -> None:
    """AC-4 (W-089): every one of the five reads notes the sync once it succeeded."""
    call, text = FETCHES[name]
    assert clean_sync.last_read() is None
    call(client(Replay(status=200, text=text)))
    assert clean_sync.last_read() is not None


@pytest.mark.parametrize("failure", ["bad_reply", "403", "500", "transport_error", "bad_json", "bad_shape"])
@pytest.mark.parametrize("name", sorted(FETCHES))
def test_a_failed_read_never_sets_the_last_read(clean_sync, name, failure) -> None:
    """AC-4 (W-089): bad reply, 403, 500, transport error, bad JSON and a rejected shape are not a sync."""
    call, _ = FETCHES[name]
    with pytest.raises(KiteReadError):
        call(client(_failure(failure)))
    assert clean_sync.last_read() is None


@pytest.mark.parametrize("failure", ["403", "500", "transport_error", "bad_json"])
def test_a_token_or_unavailable_failure_forgets_the_earlier_sync(clean_sync, failure) -> None:
    """AC-4 (W-089): the last sync does not age on screen once Zerodha stops answering or refuses the token."""
    client(Replay(status=200, text=OK_LIST)).fetch_orders()
    assert clean_sync.last_read() is not None
    with pytest.raises(KiteReadError):
        client(_failure(failure)).fetch_orders()
    assert clean_sync.last_read() is None


def test_a_bad_reply_keeps_the_earlier_sync(clean_sync) -> None:
    """A malformed answer (neither token nor unavailable) neither sets nor forgets: the earlier sync stands."""
    client(Replay(status=200, text=OK_LIST)).fetch_orders()
    with pytest.raises(KiteReadError):
        client(_failure("bad_shape")).fetch_orders()
    assert clean_sync.last_read() is not None


# REQ-155 AC-5 / F-76: the REST index quote for the spot resolver; the URL it builds passes the door's own check
@pytest.mark.parametrize(("name", "raw"), [("NSE:NIFTY 50", "/quote?i=NSE:NIFTY%2050"),
                                           ("BSE:SENSEX", "/quote?i=BSE:SENSEX")])
def test_index_quote_url_is_written_with_percent_20_and_passes_the_door(name, raw) -> None:
    assert kite_reads.index_quote_path(name) == raw
    check_call("GET", BASE + raw)  # the door itself; raises KiteCallRefused if refused
    body = json.dumps({"status": "success", "data": {name: {"last_price": 23101.5,
                                                             "timestamp": "2026-10-30 11:00:00"}}})
    replay = Replay({raw: body})
    quote = client(replay).fetch_index_quote(name)
    assert quote is not None and quote["last_price"] == Decimal("23101.5")
    assert [c[1] for c in replay.calls] == [BASE + raw]


def test_index_quote_reply_without_the_name_is_not_found_none() -> None:
    replay = Replay({"/quote?i=BSE:SENSEX": '{"status": "success", "data": {}}'})
    assert client(replay).fetch_index_quote("BSE:SENSEX") is None


@pytest.mark.parametrize("name", ["NSE:NIFTY BANK", "NSE:NIFTY+50", "NSE:NIFTY%2050", "NFO:X", ""])
def test_index_quote_of_any_other_name_is_refused_before_the_transport(name) -> None:
    replay = Replay()
    with pytest.raises(KiteReadError) as caught:
        client(replay).fetch_index_quote(name)
    assert caught.value.code == "kite_read_refused" and replay.calls == []


def test_urlencode_form_of_an_index_is_refused_by_the_door() -> None:
    with pytest.raises(KiteCallRefused):
        check_call("GET", BASE + "/quote?" + urlencode({"i": "NSE:NIFTY 50"}))
