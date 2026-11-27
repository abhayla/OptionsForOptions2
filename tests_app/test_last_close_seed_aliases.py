"""The seed command against a file whose key names are not known in advance (PC export of 27 Nov 2026, 17 rows: 15 open
contracts + NIFTY 50 + SENSEX; every price the last tick at or before 15:30:00 IST, source "feed-stream").

Key names are matched from a small set; the keys found, the mapping chosen and the first row are printed BEFORE anything
is written; a required field that cannot be mapped stops the load naming it. The contract id may be the book's id,
Kite's
instrument token, the trading symbol or "EXCHANGE:symbol", all resolved through the catalogue to the book's id."""
from __future__ import annotations

import datetime
import json
from decimal import Decimal
from types import SimpleNamespace

import pytest
from ofo.instruments.models import ZERODHA
from ofo_app import last_close_store as lcs
from test_last_close_seed_command import FRI, OPTION_ID, SeedStore, at
from test_last_close_store import listed

CLOSE_AT = "2026-11-27T15:30:00+05:30"


def entries():
    return [SimpleNamespace(currently_listed=True, has_ref=lambda b: True, contract=lc.contract,
                            broker_refs={r.broker: r for r in lc.broker_refs}) for lc in listed()]


KNOWN, ALIASES = lcs.build_aliases(entries())


def zerodha_ref(book_id: str):
    lc = next(x for x in listed() if f"{x.contract.exchange_segment}:{x.contract.exchange_token}" == book_id)
    return lc.ref(ZERODHA)


def seed(rows, *, text=None, **kw):
    store, out = SeedStore(), []
    body = text if text is not None else json.dumps(rows)
    res = lcs.run_seed(body, store, KNOWN, aliases=ALIASES, out=out.append, **kw)
    return store, res, out


def test_the_pc_export_key_names_are_mapped_and_shown_before_anything_is_written():
    row = {"contract_id": OPTION_ID, "name": "NIFTY", "expiry": "2026-10-13", "last_price": "99.75",
           "time": CLOSE_AT, "source": "feed-stream"}
    store, res, out = seed([row])
    assert store.written == [[(OPTION_ID, FRI, Decimal("99.75"), at(FRI, 15, 30), "feed-stream")]]
    assert out[0].startswith("keys in the first row: ['contract_id', 'expiry', 'last_price', 'name', 'source', 'time']")
    assert out[1] == ("mapping chosen: instrument_id<-contract_id, name<-name, expiry<-expiry, price<-last_price, "
                      "price_at<-time, source<-source")
    assert out[2].startswith("first row: {") and "99.75" in out[2]
    assert res.written == 1


@pytest.mark.parametrize("missing,keys", [("price", {"instrument_id": "x", "price_at": CLOSE_AT, "source": "s"}),
                                          ("price_at", {"instrument_id": "x", "price": "1.00", "source": "s"}),
                                          ("source", {"instrument_id": "x", "price": "1.00", "price_at": CLOSE_AT}),
                                          ("instrument_id", {"price": "1.00", "price_at": CLOSE_AT, "source": "s"})])
def test_a_required_field_that_cannot_be_mapped_stops_the_load_naming_it(missing, keys, tmp_path):
    path = tmp_path / "f.json"
    path.write_text(json.dumps({"rows": [keys]}))
    store, out = SeedStore(), []
    assert lcs.seed_command(str(path), store, KNOWN, aliases=ALIASES, check=False, out=out.append) == lcs.EXIT_FAILED
    assert store.written == []
    assert f"cannot map the field {missing}" in out[-1] and "keys in the first row are" in out[-1]


def test_every_form_of_the_contract_id_resolves_to_the_books_id():
    ref = zerodha_ref(OPTION_ID)
    base = {"price": "99.75", "price_at": CLOSE_AT, "source": "feed-stream"}
    forms = [OPTION_ID, ref.broker_token, int(ref.broker_token), ref.broker_symbol, f"NFO:{ref.broker_symbol}",
             ref.broker_symbol.lower()]
    for form in forms:
        store, res, _ = seed([{"instrument_id": form, **base}])
        assert (res.written, res.skipped) == (1, []), (form, res.skipped)
        assert store.written[0][0][0] == OPTION_ID, form


def test_an_index_resolves_by_its_name_and_exchange_symbol():
    index_id = next(i for i in KNOWN if i.startswith("NSE_INDEX:"))
    ref = zerodha_ref(index_id)
    for form in (index_id, ref.broker_symbol, f"NSE:{ref.broker_symbol}", ref.broker_token):
        store, res, _ = seed([{"id": form, "ltp": "25000.50", "exchange_time": CLOSE_AT, "source": "feed-stream"}])
        assert (res.written, store.written[0][0][0]) == (1, index_id), form


def test_an_unknown_or_ambiguous_token_is_refused_not_guessed():
    _, res, _ = seed([{"instrument_id": "99999999", "price": "1.00", "price_at": CLOSE_AT, "source": "s"}])
    assert res.written == 0 and "unknown instrument id" in res.skipped[0][2]
    amb = {**ALIASES, "sym:DUP": ("NSE_FO:1", "BSE_FO:2")}
    res = lcs.run_seed(json.dumps([{"instrument_id": "dup", "price": "1.00", "price_at": CLOSE_AT, "source": "s"}]),
                       SeedStore(), KNOWN, aliases=amb)
    assert "ambiguous" in res.skipped[0][2]


def test_a_json_number_price_is_read_from_its_digits_and_a_sub_paisa_number_is_refused():
    index_id = next(i for i in KNOWN if i.startswith("NSE_INDEX:"))
    text = ('{"rows": [{"instrument_id": "' + OPTION_ID + '", "price": 99.75, "price_at": "' + CLOSE_AT
            + '", "source": "s"}, {"instrument_id": "' + index_id + '", "price": 25000.505, "price_at": "' + CLOSE_AT
            + '", "source": "s"}]}')
    store, res, _ = seed(None, text=text)
    assert store.written[0][0][2] == Decimal("99.75") and isinstance(store.written[0][0][2], Decimal)
    assert res.written == 1 and "not a whole number of paise" in res.skipped[0][2]


def test_a_time_with_no_zone_is_refused_unless_the_owner_says_ist():
    row = {"instrument_id": OPTION_ID, "price": "99.75", "price_at": "2026-11-27 15:30:00", "source": "s"}
    _, res, _ = seed([row])
    assert res.written == 0 and "time has no zone" in res.skipped[0][2]
    store, res, _ = seed([row], assume_ist=True)
    assert store.written[0][0][3] == at(FRI, 15, 30)


def test_a_bare_list_and_a_file_with_a_byte_order_mark_load(tmp_path):
    path = tmp_path / "close-2026-11-27.json"
    row = {"instrument_id": OPTION_ID, "price": "99.75", "price_at": CLOSE_AT, "source": "feed-stream"}
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps([row]).encode())
    store, out = SeedStore(), []
    assert lcs.seed_command(str(path), store, KNOWN, aliases=ALIASES, check=False, out=out.append) == 0
    assert store.written and any("written 1" in line for line in out)


def test_the_seeded_close_row_is_served_as_the_close_with_its_own_time():
    from test_last_close_store import provider_with  # noqa: PLC0415
    provider = provider_with()
    quote = lcs.quote_of(next(x for x in listed()
                              if f"{x.contract.exchange_segment}:{x.contract.exchange_token}" == OPTION_ID),
                         Decimal("99.75"), at(FRI, 15, 30))
    assert provider.book.seed_close(quote, at(datetime.date(2026, 11, 28), 10))
    q = provider.book.get(OPTION_ID, at(datetime.date(2026, 11, 28), 10, 1))
    assert (q.ltp, q.timestamp, q.price_at) == (Decimal("99.75"), at(FRI, 15, 30), at(FRI, 15, 30))
