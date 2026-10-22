"""W-131 REQ-054 AC-1: the Kite broker reader (account, positions, orders, order status, margin) through the doors.

No network, no database. A replay transport serves recorded replies (positions, orders, funds) byte for byte.

HONEST NOTE (Core/Proof): no real ``GET /user/profile`` reply is recorded yet. ``PROFILE_REPLY`` below has the shape in
Kite's published documentation and is NOT a recording; the orchestrator runs the account read once on the owner's live
session and commits the redacted reply under ``tests/fixtures/kite_replies/``. Until then the profile tests prove our
parsing against the documented shape only.
"""
from __future__ import annotations

import ast
import csv
import dataclasses
import inspect
import json
import logging
import pathlib
import urllib.request
from decimal import Decimal as D

import pytest
from ofo.broker.egress import EgressRefused
from ofo.broker.kite_endpoints import ALLOWED_CALLS
from ofo.engine import Action
from ofo.execution.partial import BrokerOrderStatus, BrokerReader
from ofo.instruments.catalogue import Catalogue
from ofo.instruments.parser import parse_instruments_rows
from ofo.orders import Order, OrderState
from ofo_app import broker_sync, kite_broker_reader, kite_replies
from ofo_app.kite_broker_reader import KiteBrokerReader
from ofo_app.kite_margin import KiteMargin
from ofo_app.kite_reads import AccountProfile, KiteReadError, KiteReads
from ofo_app.kite_replies import ContractIndex, KiteReplyError, order_status_from_row

pytestmark = pytest.mark.repo_scan  # one test walks backend/ for the Kite header literal

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "kite_replies"
BASE = "https://api.kite.trade"
LOT = 65
TWO_READS = 2
SECRET = "tok-SECRET-123"  # noqa: S105 - a fake token
PII = ("trader@example.test", "Asha Trader", "Asha", "https://avatars.example.test/a.png", "demat-consent-token")
PROFILE_REPLY = json.dumps({"status": "success", "data": {  # documented shape, NOT a recording (see the module note)
    "user_id": "AB1234", "user_type": "individual", "email": PII[0], "user_name": PII[1], "user_shortname": PII[2],
    "broker": "ZERODHA", "exchanges": ["NSE", "NFO", "BSE", "BFO"], "products": ["CNC", "NRML", "MIS"],
    "order_types": ["MARKET", "LIMIT", "SL", "SL-M"], "avatar_url": PII[3], "meta": {"demat_consent": PII[4]}}})
PROFILE_KEYS = {"user_id", "broker", "exchanges", "products", "order_types"}


class Replay:
    def __init__(self, by_path: dict[str, str] | None = None, status: int = 200, text: str = "",
                 raises: Exception | None = None) -> None:
        self.by_path, self.status, self.text, self.raises, self.calls = by_path or {}, status, text, raises, []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, dict(headers), body))
        if self.raises:
            raise self.raises
        return self.status, self.by_path.get(url.removeprefix(BASE), self.text)


def door(transport) -> KiteReads:
    return KiteReads(api_key="key", access_token=SECRET, transport=transport)


def recorded(name: str) -> str:
    return (FIXTURES / f"{name}.json").read_text(encoding="utf-8")


def orders_reply(*rows: dict) -> str:
    return json.dumps({"status": "success", "data": list(rows)})


def row(order_id: str, status: str = "OPEN", *, filled: int = 0,
        tag: str | None = "OFS9V1L0", message: str | None = None) -> dict:
    return {"order_id": order_id, "tag": tag, "tradingsymbol": "NIFTY26OCT24000CE", "transaction_type": "BUY",
            "quantity": LOT, "filled_quantity": filled, "price": 7.45, "average_price": 7, "status": status,
            "status_message": message}


# -- the account read (Core) -------------------------------------------------------------------------------------


def test_core_account_read_through_the_door_keeps_exactly_five_keys() -> None:
    """AC-1 core: ``GET /user/profile`` through the door; the value has the five kept keys and nothing else."""
    fake = Replay(text=PROFILE_REPLY)
    profile = door(fake).fetch_profile()
    assert profile == AccountProfile("AB1234", "ZERODHA", ("NSE", "NFO", "BSE", "BFO"), ("CNC", "NRML", "MIS"),
                                     ("MARKET", "LIMIT", "SL", "SL-M"))
    assert {f.name for f in dataclasses.fields(profile)} == PROFILE_KEYS
    assert [(m, u, b) for m, u, _, b in fake.calls] == [("GET", f"{BASE}/user/profile", None)]
    assert fake.calls[0][2]["Authorization"] == f"token key:{SECRET}" and SECRET not in fake.calls[0][1]


def test_attack1_profile_pii_is_nowhere_in_the_value_a_log_or_a_repr(caplog) -> None:
    """AC-1 attack 1: email, name, short name, avatar and meta never reach the value, a repr, a log line or an error."""
    caplog.set_level(logging.DEBUG)
    profile = door(Replay(text=PROFILE_REPLY)).fetch_profile()
    seen = repr(profile) + json.dumps(dataclasses.asdict(profile)) + caplog.text
    assert not any(p in seen for p in PII) and "AB1234" not in repr(profile)
    # the error path: a 400 whose body carries the same PII
    with pytest.raises(KiteReadError) as raised:
        door(Replay(status=400, text=PROFILE_REPLY)).fetch_profile()
    assert not any(p in str(raised.value) + caplog.text for p in PII)


def test_a_new_key_kite_adds_later_is_dropped_unread() -> None:
    """AC-1: the key set is closed: an unexpected extra key (even one named like ours) changes nothing."""
    data = json.loads(PROFILE_REPLY)
    data["data"].update({"email_verified": True, "avatar": "x", "balance": 5})
    profile = door(Replay(text=json.dumps(data))).fetch_profile()
    assert {f.name for f in dataclasses.fields(profile)} == PROFILE_KEYS
    assert "balance" not in repr(profile)


@pytest.mark.parametrize("missing", sorted(PROFILE_KEYS))
def test_a_missing_required_profile_key_is_a_bad_reply(missing: str) -> None:
    """AC-1: each of the five keys is required; none is defaulted."""
    data = json.loads(PROFILE_REPLY)
    del data["data"][missing]
    with pytest.raises(KiteReadError) as raised:
        door(Replay(text=json.dumps(data))).fetch_profile()
    assert raised.value.code == "kite_read_bad_reply"


@pytest.mark.parametrize("key,value", [("user_id", ""), ("user_id", 5), ("broker", None), ("exchanges", "NSE"),
                                       ("products", [1]), ("order_types", {"a": 1}), ("exchanges", [""])])
def test_a_mistyped_profile_key_is_a_bad_reply(key: str, value: object) -> None:
    """AC-1: allow-list of types: text, or a list of text; anything else is refused."""
    data = json.loads(PROFILE_REPLY)
    data["data"][key] = value
    with pytest.raises(KiteReadError) as raised:
        door(Replay(text=json.dumps(data))).fetch_profile()
    assert raised.value.code == "kite_read_bad_reply"


def test_an_empty_list_in_the_profile_is_a_real_answer() -> None:
    """AC-1: empty exchanges / products / order types is a stated answer (kept as empty), not an error."""
    data = json.loads(PROFILE_REPLY)
    data["data"].update({"exchanges": [], "products": [], "order_types": []})
    profile = door(Replay(text=json.dumps(data))).fetch_profile()
    assert (profile.exchanges, profile.products, profile.order_types) == ((), (), ())


def test_each_profile_read_calls_kite_again() -> None:
    """AC-1 (orchestrator decision): no cache, no DB write: two reads are two calls."""
    fake = Replay(text=PROFILE_REPLY)
    client = door(fake)
    client.fetch_profile(), client.fetch_profile()
    assert len(fake.calls) == TWO_READS


def test_attack2_user_profile_outside_the_door_is_refused_by_the_egress_gate() -> None:
    """AC-1 attack 2: a bare urllib call to /user/profile from test code (not a door) never connects."""
    with pytest.raises(EgressRefused):
        urllib.request.urlopen(f"{BASE}/user/profile", timeout=2)  # noqa: S310


def test_attack7_allow_list_gains_exactly_the_profile_read() -> None:
    """AC-1 attack 7: kite_reads' entry is the six reads, and no write or order path is in any entry."""
    assert ALLOWED_CALLS["ofo_app/kite_reads.py"] == frozenset({
        ("GET", "/orders"), ("GET", "/trades"), ("GET", "/portfolio/positions"), ("GET", "/portfolio/holdings"),
        ("GET", "/quote"), ("GET", "/user/profile")})
    assert not any(p.startswith(("/orders", "/gtt")) and m != "GET" for calls in ALLOWED_CALLS.values()
                   for m, p in calls)


@pytest.mark.parametrize("path", ["/user/profile?x=1", "/user/profile#a", "/user/profile/", "/user/profiles"])
def test_the_profile_call_takes_no_query_and_no_other_path(path: str) -> None:
    """AC-1: only the bare path is allowed; the door refuses variants before sending."""
    fake = Replay(text=PROFILE_REPLY)
    with pytest.raises(KiteReadError) as raised:
        door(fake)._data("GET", path)
    assert raised.value.code == "kite_read_refused" and fake.calls == []


# -- every answer state, for each new read ----------------------------------------------------------------------

READS = {
    "profile": lambda c: c.fetch_profile(),
    "statuses": lambda c: c.fetch_order_statuses(["1"]),
}


def kite_error(error_type: str) -> str:
    return json.dumps({"status": "error", "message": "m", "error_type": error_type})


@pytest.mark.parametrize("name", READS)
@pytest.mark.parametrize("status,error_type,code", [
    (403, "TokenException", "kite_read_token"), (403, "PermissionException", "kite_read_token"),
    (503, "NetworkException", "kite_read_unavailable"), (400, "InputException", "kite_read_refused"),
    (500, "GeneralException", "kite_read_unavailable"), (429, "NetworkException", "kite_read_busy"),
    (400, "TokenException", "kite_read_token")])
def test_attack4_kite_error_types_map_to_the_doors_codes_with_one_call(name, status, error_type, code) -> None:
    """AC-1 attack 4: each Kite exception type / HTTP 429 -> the door's code; one call, never retried."""
    fake = Replay(status=status, text=kite_error(error_type))
    with pytest.raises(KiteReadError) as raised:
        READS[name](door(fake))
    assert raised.value.code == code and len(fake.calls) == 1


@pytest.mark.parametrize("name", READS)
@pytest.mark.parametrize("make,code", [
    (lambda: Replay(raises=TimeoutError()), "kite_read_unavailable"),
    (lambda: Replay(raises=OSError("reset")), "kite_read_unavailable"),
    (lambda: Replay(text="<html>not json"), "kite_read_unavailable"),
    (lambda: Replay(text=""), "kite_read_unavailable"),
    (lambda: Replay(text=json.dumps({"status": "error", "error_type": "GeneralException"})), "kite_read_bad_reply"),
    (lambda: Replay(text=json.dumps({"status": "success"})), "kite_read_bad_reply"),
    (lambda: Replay(text=json.dumps({"status": "success", "data": None})), "kite_read_bad_reply")])
def test_attack4_timeout_junk_and_missing_data(name, make, code) -> None:
    """AC-1 attack 4: timeout, junk JSON, status error at 200, missing data -> a code, one call, no raw exception."""
    fake = make()
    with pytest.raises(KiteReadError) as raised:
        READS[name](door(fake))
    assert raised.value.code == code and len(fake.calls) == 1


def test_a_failed_account_read_forgets_the_last_sync_and_a_good_one_notes_it() -> None:
    """AC-1: the profile read is a read like the others for the Settings page's sync time (W-089)."""
    broker_sync.forget()
    door(Replay(text=PROFILE_REPLY)).fetch_profile()
    assert broker_sync.last_read() is not None
    with pytest.raises(KiteReadError):
        door(Replay(status=403, text=kite_error("TokenException"))).fetch_profile()
    assert broker_sync.last_read() is None


# -- order status from the ONE orders list -----------------------------------------------------------------------


def test_attack3_statuses_one_orders_call_absent_id_is_explicit_not_found() -> None:
    """AC-1 attack 3: asked 3 ids, the list has 2: the third is None; exactly one ``GET /orders``."""
    fake = Replay({"/orders": orders_reply(row("A", "COMPLETE", filled=65), row("B"))})
    got = door(fake).fetch_order_statuses(["A", "B", "MISSING"])
    assert got["MISSING"] is None and got["A"]["order_id"] == "A" and got["B"]["order_id"] == "B"
    assert list(got) == ["A", "B", "MISSING"]
    assert [(m, u) for m, u, _, _ in fake.calls] == [("GET", f"{BASE}/orders")]


@pytest.mark.parametrize("ids,reply,expect_keys", [
    ([], orders_reply(row("A")), []),
    (["A", "A", "A"], orders_reply(row("A")), ["A"]),
    (["X"], orders_reply(), ["X"]),
    (["X", "Y"], orders_reply(), ["X", "Y"])])
def test_attack3_empty_ids_duplicates_and_empty_orders(ids, reply, expect_keys) -> None:
    """AC-1 attack 3: an empty id list, duplicate ids and an empty ``/orders`` list: no exception, one call."""
    fake = Replay({"/orders": reply})
    got = door(fake).fetch_order_statuses(ids)
    assert list(got) == expect_keys and len(fake.calls) == 1
    assert all(v is None for k, v in got.items() if k != "A")


@pytest.mark.parametrize("bad", ["", " ", None, 5, b"A"])
def test_an_id_that_is_not_text_is_refused_before_anything_is_sent(bad) -> None:
    """AC-1: an unusable id is refused (no call), never looked up as 'not found'."""
    fake = Replay({"/orders": orders_reply(row("A"))})
    with pytest.raises(KiteReadError) as raised:
        door(fake).fetch_order_statuses(["A", bad])
    assert raised.value.code == "kite_read_refused" and fake.calls == []


def test_two_rows_with_one_order_id_is_a_bad_reply() -> None:
    """AC-1 (ambiguous answer): never pick one of two rows for the same id."""
    with pytest.raises(KiteReadError) as raised:
        door(Replay({"/orders": orders_reply(row("A"), row("A", "COMPLETE", filled=65))})).fetch_order_statuses(["A"])
    assert raised.value.code == "kite_read_bad_reply"


def test_a_row_without_an_order_id_is_a_bad_reply() -> None:
    """AC-1: a row we cannot key makes the whole read unusable."""
    bad = row("A")
    del bad["order_id"]
    with pytest.raises(KiteReadError) as raised:
        door(Replay({"/orders": orders_reply(bad)})).fetch_order_statuses(["A"])
    assert raised.value.code == "kite_read_bad_reply"


def test_order_status_never_calls_a_per_order_path() -> None:
    """AC-1 attack 7: ``/orders/{id}`` is not reachable (not allow-listed), so statuses come from the list only."""
    fake = Replay({"/orders": orders_reply(row("A"))})
    with pytest.raises(KiteReadError) as raised:
        door(fake)._data("GET", "/orders/A")
    assert raised.value.code == "kite_read_refused" and fake.calls == []


# -- order row -> BrokerOrderStatus -----------------------------------------------------------------------------


@pytest.mark.parametrize("status,filled,state", [
    ("COMPLETE", 65, OrderState.EXECUTED), ("OPEN", 0, OrderState.PENDING), ("OPEN", 30, OrderState.PARTIALLY_EXECUTED),
    ("TRIGGER PENDING", 0, OrderState.PENDING), ("VALIDATION PENDING", 0, OrderState.PENDING),
    ("REJECTED", 0, OrderState.REJECTED), ("CANCELLED", 0, OrderState.CANCELLED),
    ("CANCELLED", 30, OrderState.CANCELLED)])
def test_status_word_to_state(status: str, filled: int, state: OrderState) -> None:
    """AC-1: Kite's status words map to the domain states; the cumulative fill is kept as read."""
    got = order_status_from_row(row("A", status, filled=filled))
    assert (got.broker_order_id, got.state, got.filled_quantity, got.client_tag) == ("A", state, filled, "OFS9V1L0")


@pytest.mark.parametrize("status,filled", [("COMPLETE", 30), ("COMPLETE", 0), ("SOMETHING NEW", 0), ("", 0),
                                           ("open", 0)])
def test_a_status_we_cannot_read_raises_never_defaults(status: str, filled: int) -> None:
    """AC-1: an unknown word, or COMPLETE without every unit filled, is refused: never read as pending."""
    with pytest.raises(KiteReplyError):
        order_status_from_row(row("A", status, filled=filled))


def test_the_rejection_text_is_kept_as_the_brokers_reason() -> None:
    """AC-1: REJECTED carries Kite's own status_message as the reason; blank or absent is None."""
    assert order_status_from_row(row("A", "REJECTED", message="RMS:Margin Exceeds")).reason == "RMS:Margin Exceeds"
    assert order_status_from_row(row("A", "REJECTED", message="  ")).reason is None
    assert order_status_from_row(row("A", "COMPLETE", filled=65)).reason is None


def test_recorded_real_orders_convert() -> None:
    """AC-1: the owner's real 2026-10-19 orders (recorded) all read as Executed with their tags."""
    rows = json.loads(recorded("orders-gc3l-2026-10-19"), parse_float=D)["data"]
    got = [order_status_from_row(r) for r in rows]
    assert got and all(g.state is OrderState.EXECUTED and g.filled_quantity == LOT for g in got)
    assert got[0].client_tag == "OFS9V1L0" and got[0].broker_order_id == "261019170382597"


# -- the reader ---------------------------------------------------------------------------------------------------

FUNDS = json.loads((ROOT / "tests/fixtures/kite_margins/funds-2026-10-16-122104.json").read_text(encoding="utf-8"))
CONDOR = json.loads((ROOT / "docs/research/kite-proof-2026-10-07/rest-2026-10-15/margins_basket.json")
                    .read_text(encoding="utf-8"))
LIST_CSV = ROOT / "tests/fixtures/kite_ws/instruments-2026-10-08-subscribed.csv"
NOW = __import__("datetime").datetime(2026, 10, 22, 10, 0, tzinfo=__import__("datetime").timezone.utc)


def catalogue() -> Catalogue:
    wanted = {r["tradingsymbol"] for r in CONDOR["request"]}
    with LIST_CSV.open(newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["tradingsymbol"] in wanted]
    cat = Catalogue()
    cat.load(parse_instruments_rows(rows))
    return cat


def reader(transport, margin_transport=None, cat=None) -> KiteBrokerReader:
    margin = KiteMargin(api_key="key", access_token=SECRET, transport=margin_transport or transport)
    return KiteBrokerReader(door(transport), margin, cat or Catalogue(), now=lambda: NOW)


def test_attack5_the_reader_has_the_brokerreaders_four_methods_with_its_signatures() -> None:
    """AC-1 attack 5: every BrokerReader method exists on KiteBrokerReader with the same parameter names."""
    names = [n for n, v in vars(BrokerReader).items() if callable(v) and not n.startswith("_")]
    assert sorted(names) == ["fetch_available_margin", "fetch_order_statuses", "fetch_positions",
                             "fetch_required_margin"]
    for name in names:
        want = list(inspect.signature(getattr(BrokerReader, name)).parameters)
        have = list(inspect.signature(getattr(KiteBrokerReader, name)).parameters)
        assert have == want, name


def test_the_reader_refuses_a_look_alike_door() -> None:
    """AC-1: only the real KiteReads and KiteMargin doors are accepted (no caller-supplied stand-in)."""
    class Fake:
        pass

    with pytest.raises(TypeError):
        KiteBrokerReader(Fake(), KiteMargin(api_key="k", access_token=SECRET), Catalogue())  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        KiteBrokerReader(door(Replay()), Fake(), Catalogue())  # type: ignore[arg-type]


def test_reader_positions_from_the_recorded_reply(monkeypatch) -> None:
    """AC-1: fetch_positions: the recorded 12:21 reply -> one NIFTY26O1923650CE line, tz-aware read time."""
    rows = json.loads(recorded("instruments-2026-10-16-slice"), parse_float=D)
    monkeypatch.setattr(ContractIndex, "from_catalogue", classmethod(lambda cls, c: cls.from_instrument_slice(rows)))
    fake = Replay({"/portfolio/positions": recorded("positions-122104")})
    lines, at = reader(fake).fetch_positions("1")
    assert [(ln.contract, ln.net_quantity) for ln in lines] == [("NIFTY26O1923650CE", LOT)]
    assert at == NOW and at.utcoffset() is not None
    assert [(m, u) for m, u, _, _ in fake.calls] == [("GET", f"{BASE}/portfolio/positions")]


def test_reader_order_statuses_pick_this_strategys_tag_with_one_call() -> None:
    """AC-1: strategy 9's tag OFS9V1L0 rows come back as statuses; one ``GET /orders``; another strategy gets none."""
    fake = Replay({"/orders": recorded("orders-gc3l-2026-10-19")})
    got, at = reader(fake).fetch_order_statuses("9")
    assert got and all(isinstance(s, BrokerOrderStatus) and s.client_tag.startswith("OFS9V") for s in got)
    assert at == NOW and len(fake.calls) == 1
    none, _ = reader(Replay({"/orders": recorded("orders-gc3l-2026-10-19")})).fetch_order_statuses("4")
    assert none == ()


@pytest.mark.parametrize("bad", ["", "S-9", "-1", "9.0", "٩", " 9"])
def test_reader_refuses_a_strategy_id_that_is_not_a_tag_number(bad: str) -> None:
    """AC-1: a strategy id that cannot be a tag's number is refused without a call, never 'no orders'."""
    fake = Replay({"/orders": recorded("orders-gc3l-2026-10-19")})
    with pytest.raises(KiteReadError):
        reader(fake).fetch_order_statuses(bad)
    assert fake.calls == []


def test_reader_leaves_out_untagged_and_foreign_tagged_orders_but_not_unreadable_ours() -> None:
    """AC-1: an order with no tag or a tag from another system is skipped; our tagged row that cannot be read raises."""
    text = orders_reply(row("A", tag=None), row("B", tag="mytag"), row("C", "COMPLETE", filled=65, tag="OFS9V1L1"))
    got, _ = reader(Replay({"/orders": text})).fetch_order_statuses("9")
    assert [s.broker_order_id for s in got] == ["C"]
    with pytest.raises(KiteReplyError):
        reader(Replay({"/orders": orders_reply(row("D", "WEIRD", tag="OFS9V1L1"))})).fetch_order_statuses("9")


def test_reader_status_by_id_gives_not_found_as_none() -> None:
    """AC-1 attack 3: by id, an absent id is None (not a status), a present one is its status; one call."""
    fake = Replay({"/orders": orders_reply(row("A", "COMPLETE", filled=65))})
    got = reader(fake).fetch_order_status_by_id(["A", "Z"])
    assert got["Z"] is None and got["A"].state is OrderState.EXECUTED and len(fake.calls) == 1


def test_reader_available_margin_is_zerodhas_recorded_funds() -> None:
    """AC-1: fetch_available_margin = Zerodha's equity.net from the recorded 2026-10-16 funds reply (671.50)."""
    fake = Replay({"/user/margins": json.dumps(FUNDS["reply"])})
    assert reader(fake).fetch_available_margin() == D("671.50")


def test_reader_required_margin_is_zerodhas_basket_figure() -> None:
    """AC-1: fetch_required_margin = Zerodha's required figure for exactly these orders (68,498.85, recorded)."""
    cat = catalogue()
    orders = [Order("S-9", f"L{i}", r["tradingsymbol"], Action(r["transaction_type"]), r["quantity"],
                    D(str(r["price"])), version_id="V-1") for i, r in enumerate(CONDOR["request"], start=1)]
    fake = Replay({"/margins/basket?consider_positions=true": json.dumps(CONDOR["reply"])})
    assert reader(fake, cat=cat).fetch_required_margin(orders) == D("68498.85")


def test_reader_account_read_is_the_profile_read() -> None:
    """AC-1: fetch_account returns the five-key profile."""
    assert isinstance(reader(Replay(text=PROFILE_REPLY)).fetch_account(), AccountProfile)


# -- attack 5/7: no second helper, no order path -----------------------------------------------------------------


def _source(name: str) -> ast.Module:
    return ast.parse((ROOT / "backend" / "ofo_app" / name).read_text(encoding="utf-8"))


def test_attack5_the_reader_repeats_no_header_host_parse_or_error_helper() -> None:
    """AC-1 attack 5: the reader's module has no Kite host or header literal, no JSON parse, no HTTP client, no error
    mapping; and the Kite version header literal lives only in the modules that already owned it."""
    tree = _source("kite_broker_reader.py")
    imports = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imports |= {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert imports == {"__future__", "datetime", "collections", "decimal", "ofo", "ofo_app"}  # allow-list
    strings = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    # no host / header literal
    assert not [s for s in strings if " " not in s and "kite" in s.lower() and ("." in s or "-" in s)]
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr in ("loads", "urlopen", "post")]
    owners = {p.name for p in (ROOT / "backend").rglob("*.py") if "X-Kite-Version" in p.read_text(encoding="utf-8")}
    assert owners == {"kite_client.py", "kite_history.py", "kite_margin.py"}


def test_attack7_the_reader_calls_only_the_read_methods_of_its_two_doors() -> None:
    """AC-1 attack 7: an allow-list of the door methods the reader may call, and of the ofo_app modules it imports;
    nothing else (no basket, no order send) is reachable from it."""
    tree = _source("kite_broker_reader.py")
    called = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
              and isinstance(n.func.value, ast.Attribute) and n.func.value.attr in ("_reads", "_margin")}
    assert called == {"fetch_profile", "fetch_positions", "fetch_orders", "fetch_order_statuses",
                      "fetch_available_funds"}
    imported = {n.module for n in ast.walk(tree)
                if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("ofo_app")}
    assert imported == {"ofo_app.checked_basket", "ofo_app.kite_margin", "ofo_app.kite_reads", "ofo_app.kite_replies"}
    assert kite_broker_reader.zerodha_required_margin.__module__ == "ofo_app.checked_basket"
    assert kite_replies.order_status_from_row is order_status_from_row
