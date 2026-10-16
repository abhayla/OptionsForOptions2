"""W-081 AC-1: the Kite margin client, tested with the recorded 2026-10-15 basket reply through a fake transport.

No network, no database. The funds reply is built from the recorded SHAPE (shape_user_margins.json holds field types
only; real values are withheld), so `equity.net` is unproven on real data until the live run of 2026-10-16.
"""
import http.client
import json
import logging
import pathlib
from decimal import Decimal

import pytest
from ofo.broker import kite_http as kite_door  # round 7: the urllib door sends through its own opener
from ofo.execution.margin_gate import MarginVerdict
from ofo_app.kite_margin import BasketOrder, KiteMargin, KiteMarginError, margin_verdict, urllib_transport

REPLY_FILE = (pathlib.Path(__file__).resolve().parent.parent
              / "docs/research/kite-proof-2026-10-07/rest-2026-10-15/margins_basket.json")
STRANGLE_FILE = (pathlib.Path(__file__).resolve().parent.parent
                 / "tests/fixtures/kite_margins/basket-2026-10-16-long-strangle-bump5.json")
SENSEX_STRANGLE_FILE = (pathlib.Path(__file__).resolve().parent.parent
                        / "tests/fixtures/kite_margins/basket-2026-10-16-sensex-long-strangle-bump5.json")
RECORDED = json.loads(REPLY_FILE.read_text(encoding="utf-8"), parse_float=Decimal)
REPLY_TEXT = json.dumps(json.loads(REPLY_FILE.read_text(encoding="utf-8"))["reply"])
SECRET = "tok-SECRET-123"  # noqa: S105


def condor() -> list[BasketOrder]:
    return [BasketOrder(r["exchange"], r["tradingsymbol"], r["transaction_type"], r["product"], r["order_type"],
                        r["quantity"], Decimal(str(r["price"])), r["variety"]) for r in RECORDED["request"]]


def funds_text(net: str) -> str:
    return '{"status": "success", "data": {"equity": {"enabled": true, "net": %s}}}' % net  # noqa: UP031


class Fake:
    def __init__(self, status: int = 200, text: str = "", raises: Exception | None = None) -> None:
        self.status, self.text, self.raises, self.calls = status, text, raises, []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        if self.raises:
            raise self.raises
        return self.status, self.text


def client(fake) -> KiteMargin:
    return KiteMargin(api_key="key", access_token=SECRET, transport=fake)


def test_ac1_basket_margin_from_the_recorded_reply_and_the_right_request() -> None:
    """AC-1: final.total 68498.85, initial.total 296332.8 and four per-order rows come back as Decimal; the request
    is a POST of the recorded request shape to /margins/basket?consider_positions=true."""
    fake = Fake(text=REPLY_TEXT)
    result = client(fake).fetch_basket_margin(condor())
    assert (result.zerodha_total, result.required_total, result.initial_total) == (
        Decimal("68498.85"), Decimal("68498.85"), Decimal("296332.8"))
    assert [(o.tradingsymbol, o.total) for o in result.orders] == [
        ("NIFTY26O1923150CE", Decimal("132219.75")), ("NIFTY26O1923350CE", Decimal("1124.5")),
        ("NIFTY26O1922750PE", Decimal("160778.55")), ("NIFTY26O1922550PE", Decimal("2210"))]
    (method, url, headers, body), = fake.calls
    assert (method, url) == ("POST", "https://api.kite.trade/margins/basket?consider_positions=true")
    assert headers["Authorization"] == f"token key:{SECRET}" and headers["X-Kite-Version"] == "3"
    assert headers["Content-Type"] == "application/json"
    assert json.loads(body, parse_float=Decimal) == RECORDED["request"]  # exact recorded shape, prices as numbers
    assert '"price": 53.3}' in body and '"price": "53.3"' not in body


def test_ac1_available_funds_is_equity_net_as_decimal() -> None:
    """AC-1: GET /user/margins -> equity.net as an exact Decimal (a float in the JSON never becomes a float)."""
    fake = Fake(text=funds_text("68498.85"))
    assert client(fake).fetch_available_funds() == Decimal("68498.85")
    assert fake.calls[0][:2] == ("GET", "https://api.kite.trade/user/margins") and fake.calls[0][3] is None
    assert client(Fake(text=funds_text("0"))).fetch_available_funds() == Decimal("0")


@pytest.mark.parametrize("status,code", [(403, "kite_margin_token"), (429, "kite_margin_busy"),
                                         (400, "kite_margin_refused"), (500, "kite_margin_unavailable"),
                                         (503, "kite_margin_unavailable")])
def test_ac1_a_non_success_status_is_a_typed_error(status: int, code: str) -> None:
    """AC-1: HTTP 403/429/400/500/503 -> a typed error with its code (fail closed)."""
    with pytest.raises(KiteMarginError) as raised:
        client(Fake(status, REPLY_TEXT)).fetch_basket_margin(condor())
    assert raised.value.code == code
    with pytest.raises(KiteMarginError) as raised:
        client(Fake(status, funds_text("1"))).fetch_available_funds()
    assert raised.value.code == code


def test_ac1_token_exception_body_is_a_token_error_whatever_the_status() -> None:
    """AC-1: error_type TokenException -> kite_margin_token."""
    with pytest.raises(KiteMarginError) as raised:
        client(Fake(401, '{"status": "error", "error_type": "TokenException"}')).fetch_available_funds()
    assert raised.value.code == "kite_margin_token"


def _without(path: list[str]) -> str:
    reply = json.loads(REPLY_TEXT)
    node = reply
    for key in path[:-1]:
        node = node[key]
    del node[path[-1]]
    return json.dumps(reply)


@pytest.mark.parametrize("text", [
    _without(["data", "final"]), _without(["data", "final", "total"]), _without(["data", "initial"]),
    _without(["data", "orders"]), REPLY_TEXT.replace('"success"', '"error"'),
    REPLY_TEXT.replace("68498.85", '"68498.85"'), REPLY_TEXT.replace("68498.85", "null"),
    REPLY_TEXT.replace("68498.85", "true"), REPLY_TEXT.replace("68498.85", "NaN"), "not json", "[]", "",
])
def test_ac1_a_reply_without_a_numeric_final_total_is_a_typed_error(text: str) -> None:
    """AC-1: missing final/total/initial/orders, a failed status, a string/null/bool/NaN total or junk -> typed error."""  # noqa: E501
    with pytest.raises(KiteMarginError):
        client(Fake(text=text)).fetch_basket_margin(condor())


@pytest.mark.parametrize("text", ['{"status": "success", "data": {}}', funds_text('"1"'), funds_text("null"),
                                  funds_text("NaN"), funds_text("true"), "oops"])
def test_ac1_funds_without_a_numeric_net_is_a_typed_error(text: str) -> None:
    """AC-1: no equity, no net, or a string/null/NaN/bool net -> typed error."""
    with pytest.raises(KiteMarginError):
        client(Fake(text=text)).fetch_available_funds()


def test_ac1_a_transport_failure_is_a_typed_error_and_the_token_never_leaks(caplog) -> None:
    """AC-1: a transport exception from the injected transport is not swallowed into success; no secret in logs or text."""  # noqa: E501
    caplog.set_level(logging.DEBUG)
    with pytest.raises(KiteMarginError) as raised:
        client(Fake(status=500, text=SECRET)).fetch_available_funds()
    with pytest.raises(KiteMarginError) as dropped:
        client(Fake(raises=TimeoutError(SECRET))).fetch_available_funds()
    assert dropped.value.code == "kite_margin_unavailable" and SECRET not in str(dropped.value)
    assert SECRET not in str(raised.value) and SECRET not in caplog.text and SECRET not in repr(client(Fake()))


def test_ac1_equal_funds_build_and_one_paisa_short_blocks_through_the_client() -> None:
    """AC-1/AC-4 (core, app layer): funds 68498.85 vs the recorded basket allow; 68498.84 block with both amounts."""
    basket = Fake(text=REPLY_TEXT)

    def transport(method, url, headers, body):
        return basket(method, url, headers, body) if "basket" in url else (200, FUNDS[0])

    FUNDS = [funds_text("68498.85")]
    allowed = margin_verdict(client(transport), condor())
    assert isinstance(allowed, MarginVerdict) and allowed.allowed is True
    FUNDS[0] = funds_text("68498.84")
    blocked = margin_verdict(client(transport), condor())
    assert blocked.allowed is False and blocked.message is not None
    assert "₹68,498.85" in blocked.message.what_happened and "₹68,498.84" in blocked.message.what_happened


def test_ac1_negative_funds_block_and_show_zerodhas_signed_figure() -> None:
    """AC-1 (round 2 item 3): a negative equity.net (account in debit) blocks and is shown as Zerodha gives it."""
    def transport(method, url, headers, body):
        return (200, REPLY_TEXT) if "basket" in url else (200, funds_text("-120.5"))

    assert client(Fake(text=funds_text("-120.5"))).fetch_available_funds() == Decimal("-120.5")
    verdict = margin_verdict(client(transport), condor())
    assert verdict.allowed is False and verdict.available == Decimal("-120.5")
    assert "-₹120.50 is available" in verdict.message.what_happened


def _recorded_basket(path: pathlib.Path) -> tuple[list[BasketOrder], Fake]:
    """The recorded request as BasketOrders and a fake transport replying with the recorded reply."""
    recorded = json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)
    orders = [BasketOrder(r["exchange"], r["tradingsymbol"], r["transaction_type"], r["product"], r["order_type"],
                          r["quantity"], r["price"], r["variety"]) for r in recorded["request"]]
    return orders, Fake(text=json.dumps(json.loads(path.read_text(encoding="utf-8"))["reply"]))


def test_ac1_a_sensex_basket_on_bfo_is_checked_not_refused() -> None:
    """AC-1 + ADR-094, REAL 2026-10-16 SENSEX (BFO) long-strangle reply, both limits above Kite's premium. Kite's
    final.total 14915 (option_premium 7041 and 7874, plain integers); 20 x 355 - 7041 = 59 and 20 x 401 - 7874 = 146,
    so the top-up is 205 and the requirement 15120."""
    orders, fake = _recorded_basket(SENSEX_STRANGLE_FILE)
    result = client(fake).fetch_basket_margin(orders)
    assert (result.zerodha_total, result.required_total) == (Decimal("14915"), Decimal("15120"))
    assert '"exchange": "BFO"' in fake.calls[0][3]


def test_adr094_the_client_adds_the_buy_premium_above_kites_figure() -> None:
    """ADR-094: real 2026-10-16 NIFTY long-strangle reply: Zerodha 6409, required 6409 + 263.25 + 393.25 = 7065.50."""
    orders, fake = _recorded_basket(STRANGLE_FILE)
    result = client(fake).fetch_basket_margin(orders)
    assert (result.zerodha_total, result.required_total) == (Decimal("6409"), Decimal("7065.50"))


class _Once:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def __call__(self, method, url, headers, body):
        raise self.exc


@pytest.mark.parametrize("exc", [http.client.IncompleteRead(b"x"), http.client.RemoteDisconnected("x"),
                                 ConnectionResetError("x"), TimeoutError("x"), UnicodeDecodeError("utf-8", b"\xff", 0, 1, "x"),  # noqa: E501
                                 ValueError("x"), RuntimeError("x")])
def test_ac1_every_transport_exception_is_the_typed_unavailable_error_and_blocks(exc: Exception) -> None:
    """AC-1 (round 2 item 4): whatever the transport raises -> kite_margin_unavailable; the gate blocks with the
    could-not-confirm message."""
    with pytest.raises(KiteMarginError) as raised:
        client(_Once(exc)).fetch_available_funds()
    assert raised.value.code == "kite_margin_unavailable"
    verdict = margin_verdict(client(_Once(exc)), condor())
    assert verdict.allowed is False
    assert verdict.message.what_happened == "We could not confirm your available margin with Zerodha. Execution is paused."  # noqa: E501


class _Response:
    def __init__(self, body: bytes, status: int = 200, fail_read: Exception | None = None) -> None:
        self.body, self.status, self.fail_read = body, status, fail_read

    def read(self) -> bytes:
        if self.fail_read:
            raise self.fail_read
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.mark.parametrize("response", [_Response(b"\xff\xfe"), _Response(b"", fail_read=http.client.IncompleteRead(b"x")),  # noqa: E501
                                      _Response(b"not json")])
def test_ac1_the_real_transport_turns_bad_bodies_into_the_typed_error(monkeypatch, response) -> None:
    """AC-1 (round 2 item 4): a 200 body that is not UTF-8, a read cut short, or not JSON -> typed error."""
    monkeypatch.setattr(kite_door._OPENER, "open", lambda request, timeout: response)
    with pytest.raises(KiteMarginError) as raised:
        KiteMargin(api_key="key", access_token=SECRET).fetch_available_funds()
    assert raised.value.code == "kite_margin_unavailable"


@pytest.mark.parametrize("fail_funds", [True, False])
def test_ac1_either_read_failing_blocks_the_basket(fail_funds: bool) -> None:
    """AC-1: funds read fails, or the basket read fails -> blocked with the could-not-confirm message, no retry."""
    calls = []

    def transport(method, url, headers, body):
        calls.append(url)
        is_basket = "basket" in url
        if is_basket != fail_funds:
            return 500, ""
        return (200, REPLY_TEXT) if is_basket else (200, funds_text("999999"))

    verdict = margin_verdict(client(transport), condor())
    assert verdict.allowed is False
    assert verdict.message.what_happened == "We could not confirm your available margin with Zerodha. Execution is paused."  # noqa: E501
    assert len(calls) == len(set(calls))  # nothing was retried


@pytest.mark.parametrize("change", [{"transaction_type": "HOLD"}, {"product": "CNC"}, {"order_type": "SL"},
                                    {"exchange": "NSE"}, {"exchange": "nfo"},{"variety": "amo"}, {"quantity": 0}, {"quantity": 65.0},  # noqa: E501
                                    {"price": 53.3}, {"price": Decimal("NaN")}, {"price": Decimal("-1")},
                                    {"tradingsymbol": 'X","y":1'}])
def test_ac1_basket_order_is_a_closed_shape(change: dict) -> None:
    """AC-1: anything outside the allowed order shape (side, product, type, exchange, float price...) raises."""
    base = {"exchange": "NFO", "tradingsymbol": "NIFTY26O1923150CE", "transaction_type": "SELL", "product": "NRML",
                "order_type": "LIMIT", "quantity": 65, "price": Decimal("53.3"), "variety": "regular"}
    with pytest.raises(ValueError):
        BasketOrder(**{**base, **change})


def test_ac1_an_empty_or_foreign_basket_is_refused_before_any_call() -> None:
    """AC-1: no orders, or a dict instead of a BasketOrder, raises and makes no HTTP call."""
    fake = Fake(text=REPLY_TEXT)
    for bad in ([], [RECORDED["request"][0]]):
        with pytest.raises(ValueError):
            client(fake).fetch_basket_margin(bad)
    assert fake.calls == []


@pytest.mark.parametrize("response", [_Response(b"\xff\xfe"), _Response(b"", fail_read=http.client.IncompleteRead(b"x"))])  # noqa: E501
def test_ac1_urllib_transport_itself_raises_only_the_typed_error(monkeypatch, response) -> None:
    """AC-1 (round 2 item 4): the shipped transport converts a bad UTF-8 body or a short read itself."""
    monkeypatch.setattr(kite_door._OPENER, "open", lambda request, timeout: response)
    with pytest.raises(KiteMarginError):
        urllib_transport("GET", "https://api.kite.trade/user/margins", {}, None)


@pytest.mark.parametrize("opener", ["[", '{"a":'], ids=["arrays", "objects"])
def test_ac1_deeply_nested_json_is_the_typed_error_and_blocks(opener: str) -> None:
    """AC-1 (round 3 M1): a reply nested past the recursion limit -> kite_margin_unavailable, never RecursionError;
    also on the error-body path (a 401 with such a body is still just refused)."""
    text = opener * 200000
    for call in (lambda c: c.fetch_available_funds(), lambda c: c.fetch_basket_margin(condor())):
        with pytest.raises(KiteMarginError) as raised:
            call(client(Fake(text=text)))
        assert raised.value.code == "kite_margin_unavailable"
    with pytest.raises(KiteMarginError) as raised:
        client(Fake(status=401, text=text)).fetch_available_funds()
    assert raised.value.code == "kite_margin_refused"
    assert margin_verdict(client(Fake(text=text)), condor()).allowed is False


class _Unreadable:
    def read(self, *args):
        raise http.client.IncompleteRead(b"x")

    def close(self) -> None:
        pass


def test_ac1_a_403_with_an_unreadable_body_still_reports_the_token_code(monkeypatch) -> None:
    """AC-1 (round 3 M3): the status alone decides when the error body cannot be read (IncompleteRead is not an
    OSError): 403 -> kite_margin_token, not kite_margin_unavailable."""
    import urllib.error  # noqa: PLC0415

    def refuse(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, _Unreadable())

    monkeypatch.setattr(kite_door._OPENER, "open", refuse)
    with pytest.raises(KiteMarginError) as raised:
        KiteMargin(api_key="key", access_token=SECRET).fetch_available_funds()
    assert raised.value.code == "kite_margin_token"


def test_transport_goes_through_the_kite_door_and_a_refusal_fails_closed(monkeypatch) -> None:
    """W-080 round 4: urllib_transport sends only via open_url; KiteCallRefused -> kite_margin_refused, no leak."""
    from ofo.broker.kite_http import KiteCallRefused  # noqa: PLC0415
    from ofo_app import kite_margin  # noqa: PLC0415

    seen: list[tuple] = []

    class _Ok:
        status = 200

        def read(self):
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_open(url, *, method="GET", data=None, headers=None, timeout=20):
        seen.append((method, url, data, timeout))
        return _Ok()

    monkeypatch.setattr(kite_margin, "kite_open_url", fake_open)
    assert urllib_transport("GET", "https://api.kite.trade/user/margins", {}, None) == (200, "{}")
    urllib_transport("POST", "https://api.kite.trade/margins/basket?consider_positions=true", {}, "[]")
    assert seen == [("GET", "https://api.kite.trade/user/margins", None, 20),
                    ("POST", "https://api.kite.trade/margins/basket?consider_positions=true", b"[]", 20)]

    def refuse(*a, **k):
        raise KiteCallRefused(f"secret {SECRET}")

    monkeypatch.setattr(kite_margin, "kite_open_url", refuse)
    with pytest.raises(KiteMarginError) as raised:
        urllib_transport("GET", "https://api.kite.trade/user/margins", {}, None)
    assert raised.value.code == "kite_margin_refused" and SECRET not in repr(raised.value.args)
