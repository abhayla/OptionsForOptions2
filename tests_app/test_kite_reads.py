"""W-093 AC-3 / AC-4: the Kite read door (orders, trades, positions) tested with the recorded 2026-10-16 replies.

No network, no database. A replay transport serves the recorded reply files byte for byte. The core test feeds the
door's output into ``ofo_app.kite_replies`` and expects the owner's real order: tag OFS1V1L0 filled 65, trade 4484194,
a 65-unit NIFTY26O1923650CE position.
"""
import json
import logging
import re
from decimal import Decimal
from pathlib import Path

import pytest
from ofo.broker.kite_endpoints import ALLOWED_CALLS
from ofo.broker.kite_http import KiteCallRefused
from ofo.engine import Instrument
from ofo.execution.basket import TagParts, parse_tag
from ofo_app import kite_reads
from ofo_app.kite_margin import KiteMarginError
from ofo_app.kite_reads import KiteReadError, KiteReads
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
    assert ALLOWED_CALLS["ofo_app/kite_reads.py"] == READS | {("GET", "/quote")}  # W-099 added the quote read


@pytest.mark.parametrize("method,path", [("POST", "/orders"), ("POST", "/orders/regular"), ("DELETE", "/orders/1"),
                                         ("GET", "/orders/regular"), ("GET", "/orders/"), ("GET", "/orders/123"),
                                         ("PUT", "/trades"), ("GET", "/portfolio/holdings")])
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
