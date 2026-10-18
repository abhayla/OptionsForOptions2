"""W-099 AC-4: circuit bands from Zerodha's GET /quote through the Kite read door.

No network, no database. The core test replays the owner's real 2026-10-16 15:07:20 quote of NIFTY26O1923650CE.
"""
import logging
import re
from decimal import Decimal
from pathlib import Path

import pytest
from ofo.broker.kite_endpoints import ALLOWED_CALLS
from ofo.broker.kite_endpoints import CALLER_KITE_READS
from ofo.broker.kite_http import KiteCallRefused, check_call
from ofo_app.kite_reads import KiteReadError, KiteReads

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "kite_replies" / "quote-150720.json"
SECRET = "tok-SECRET-123"
BASE = "https://api.kite.trade"
SYM = "NFO:NIFTY26O1923650CE"
OTHER = "NFO:NIFTY26O1923600PE"
QUOTE_PATH = "/quote"


class Replay:
    def __init__(self, text: str = "", status: int = 200, raises: Exception | None = None) -> None:
        self.text, self.status, self.raises, self.calls = text, status, raises, []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        if self.raises:
            raise self.raises
        return self.status, self.text


def client(transport) -> KiteReads:
    return KiteReads(api_key="key", access_token=SECRET, transport=transport)


def reply(quotes: dict[str, str]) -> str:
    """A Kite reply with one raw-JSON quote per symbol, so numbers stay JSON numbers."""
    body = ", ".join(f'"{k}": {v}' for k, v in quotes.items())
    return '{"status": "success", "data": {%s}}' % body  # noqa: UP031


def lim(lower: str, upper: str) -> str:
    return '{"lower_circuit_limit": %s, "upper_circuit_limit": %s}' % (lower, upper)  # noqa: UP031


def test_core_real_quote_gives_the_band() -> None:
    """AC-4 core: the owner's real quote, through the door, is the exact band 0.05 / 81.55; 3.35 in, 81.60 out."""
    fake = Replay(FIXTURE.read_text(encoding="utf-8"))
    bands = client(fake).fetch_circuit_bands([SYM])
    assert bands == {SYM: (Decimal("0.05"), Decimal("81.55"))}
    assert all(type(v) is Decimal for v in bands[SYM])
    lower, upper = bands[SYM]
    assert lower <= Decimal("3.35") <= upper
    assert not lower <= Decimal("81.60") <= upper
    assert fake.calls[0][:2] == ("GET", f"{BASE}/quote?i={SYM}")


def test_allow_list_entry_has_exactly_the_four_reads() -> None:
    """AC-4: the module's entry is the three W-093 reads plus GET /quote, nothing else."""
    assert ALLOWED_CALLS["ofo_app/kite_reads.py"] == frozenset({
        ("GET", "/orders"), ("GET", "/trades"), ("GET", "/portfolio/positions"), ("GET", "/portfolio/holdings"),
        ("GET", "/quote")})


def test_repeated_i_query_is_sent_in_asked_order() -> None:
    fake = Replay(reply({SYM: lim("1", "2")}))
    client(fake).fetch_circuit_bands([SYM, OTHER])
    assert fake.calls[0][1] == f"{BASE}/quote?i={SYM}&i={OTHER}"
    assert all(b is None and h["Authorization"] == f"token key:{SECRET}" for _, _, h, b in fake.calls)


@pytest.mark.parametrize("query", ["?", "?x=1", f"?i={SYM}&x=1", f"?i={SYM}&", "?i=", "?i=a b", f"?i={SYM}%2F",
                                   f"?j={SYM}", f"?i={SYM};x", f"?i={SYM}#f", f"?x=1&i={SYM}"])
def test_door_accepts_only_i_queries_on_quote(query) -> None:
    """AC-4: /quote takes the repeated i= query and nothing else."""
    with pytest.raises(KiteCallRefused):
        check_call("GET", f"{BASE}{QUOTE_PATH}{query}", caller=CALLER_KITE_READS)


def test_door_accepts_the_plain_i_queries() -> None:
    check_call("GET", f"{BASE}{QUOTE_PATH}", caller=CALLER_KITE_READS)
    check_call("GET", f"{BASE}{QUOTE_PATH}?i={SYM}", caller=CALLER_KITE_READS)
    check_call("GET", f"{BASE}{QUOTE_PATH}?i={SYM}&i={OTHER}", caller=CALLER_KITE_READS)


@pytest.mark.parametrize("method,path", [("POST", "/quote"), ("DELETE", "/quote"), ("GET", "/quote/ltp"),
                                         ("GET", "/quote/"), ("GET", "/quote/ohlc"), ("POST", "/orders")])
def test_door_refuses_other_methods_and_paths(method, path) -> None:
    fake = Replay(reply({}))
    with pytest.raises(KiteReadError) as raised:
        client(fake)._data(method, path)
    assert raised.value.code == "kite_read_refused" and fake.calls == []


def test_money_as_json_numbers_is_exact_decimal() -> None:
    """AC-4: live Kite sends numbers; 0.05 / 81.55 stay exact, an integer stays an exact value."""
    bands = client(Replay(reply({SYM: lim("0.05", "81.55"), OTHER: lim("5", "100")}))).fetch_circuit_bands([SYM, OTHER])
    assert bands[SYM] == (Decimal("0.05"), Decimal("81.55"))
    assert bands[OTHER] == (Decimal("5"), Decimal("100"))
    assert all(type(v) is Decimal for pair in bands.values() for v in pair)
    assert str(bands[SYM][1]) == "81.55"  # a float 81.55 would not print as 81.55 once converted by Decimal(float)


@pytest.mark.parametrize("quote", [
    "{}",
    '{"lower_circuit_limit": 1}',
    '{"upper_circuit_limit": 1}',
    lim('"abc"', "5"), lim("1", '"abc"'), lim("null", "5"), lim("1", "null"), lim("true", "5"), lim("1", "[]"),
    lim("5", "1"),                       # lower > upper
    lim("0", "5"), lim("1", "0"), lim("-1", "5"), lim("-5", "-1"),
    lim('"NaN"', "5"), lim("1", '"Infinity"'), lim("1e999999", "5"),
    "null", "[]", '"x"', "5",
])
def test_unknown_or_bad_band_leaves_the_instrument_absent(quote) -> None:
    """AC-4 / ADR-080: never a guessed band; the gate then blocks an ENTRY leg as band-unknown."""
    text = reply({SYM: quote, OTHER: lim("1", "9")})
    assert client(Replay(text)).fetch_circuit_bands([SYM, OTHER]) == {OTHER: (Decimal("1"), Decimal("9"))}


def test_recorder_shape_numeric_strings_are_read_exactly() -> None:
    """The recorded fixtures carry money as strings; a plain numeric string is read exactly, never via float."""
    bands = client(Replay(reply({SYM: lim('"0.05"', '"81.55"')}))).fetch_circuit_bands([SYM])
    assert bands == {SYM: (Decimal("0.05"), Decimal("81.55"))}


def test_missing_instrument_is_absent_not_defaulted() -> None:
    assert client(Replay(reply({}))).fetch_circuit_bands([SYM]) == {}


def test_equal_lower_and_upper_is_a_valid_band() -> None:
    assert client(Replay(reply({SYM: lim("5", "5")}))).fetch_circuit_bands([SYM]) == {SYM: (Decimal("5"), Decimal("5"))}


def test_extra_keys_in_the_reply_are_ignored() -> None:
    text = reply({SYM: lim("1", "9"), OTHER: lim("2", "8")})
    assert client(Replay(text)).fetch_circuit_bands([SYM]) == {SYM: (Decimal("1"), Decimal("9"))}


def test_no_instruments_sends_nothing() -> None:
    fake = Replay(reply({}))
    assert client(fake).fetch_circuit_bands([]) == {} and fake.calls == []


@pytest.mark.parametrize("bad", ["", "NIFTY", "NFO:", ":X", "NFO:A B", "NFO:A&i=B", "NFO:A%2F", "nfo:a/b", "NFO:A\nB",
                                 "NFO:A;B", "NFO:A#", "NFO:" + chr(0x661), "NFO:A\n"])
def test_a_malformed_instrument_is_refused_before_the_transport(bad) -> None:
    fake = Replay(reply({}))
    with pytest.raises(KiteReadError) as raised:
        client(fake).fetch_circuit_bands([SYM, bad])
    assert raised.value.code == "kite_read_refused" and fake.calls == []


def test_more_than_the_quote_limit_is_refused() -> None:
    fake = Replay(reply({}))
    with pytest.raises(KiteReadError) as raised:
        client(fake).fetch_circuit_bands([f"NFO:X{i}" for i in range(501)])
    assert raised.value.code == "kite_read_refused" and fake.calls == []


@pytest.mark.parametrize("status,code", [(403, "kite_read_token"), (429, "kite_read_busy"), (400, "kite_read_refused"),
                                         (500, "kite_read_unavailable")])
def test_http_errors_map_to_codes(status, code) -> None:
    with pytest.raises(KiteReadError) as raised:
        client(Replay("{}", status=status)).fetch_circuit_bands([SYM])
    assert raised.value.code == code


@pytest.mark.parametrize("text", ['{"status": "error", "data": {}}', '{"status": "success"}',
                                  '{"status": "success", "data": []}', '{"status": "success", "data": null}', "[]"])
def test_whole_reply_failure_is_bad_reply(text) -> None:
    with pytest.raises(KiteReadError) as raised:
        client(Replay(text)).fetch_circuit_bands([SYM])
    assert raised.value.code == "kite_read_bad_reply"


@pytest.mark.parametrize("text", ["", "not json", pytest.param("[" * 100000, id="deeply-nested")])
def test_junk_body_is_unavailable(text) -> None:
    with pytest.raises(KiteReadError) as raised:
        client(Replay(text)).fetch_circuit_bands([SYM])
    assert raised.value.code == "kite_read_unavailable"


def test_the_token_appears_nowhere(caplog) -> None:
    caplog.set_level(logging.DEBUG)
    door = client(Replay(SECRET, status=500))
    assert SECRET not in repr(door) and re.search(r"api_key|access_token", repr(door)) is None
    for fake in (Replay(SECRET, status=403), Replay(SECRET, status=500), Replay(SECRET),
                 Replay(raises=RuntimeError(SECRET))):
        with pytest.raises(KiteReadError) as raised:
            client(fake).fetch_circuit_bands([SYM])
        assert SECRET not in str(raised.value) and SECRET not in repr(raised.value.args)
        assert raised.value.__cause__ is None
    assert SECRET not in caplog.text
