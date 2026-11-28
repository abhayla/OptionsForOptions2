"""Seed command, review round 2: zero prices, labels that would differ from the row's own time, ambiguous key names, a
seed that must never replace a frame the feed delivered, the database line, error exits, exchange prefixes, ambiguous
numeric ids, file encodings, INSERT ... ON CONFLICT DO NOTHING. Fakes only."""
from __future__ import annotations

import datetime
import json
from decimal import Decimal

import pytest
from ofo_app import last_close_store as lcs
from sqlalchemy.exc import IntegrityError, ProgrammingError
from test_last_close_seed_aliases import ALIASES, KNOWN, zerodha_ref
from test_last_close_seed_command import FRI, OPTION_ID, SeedStore, at
from test_last_close_store import listed, provider_with

CLOSE_AT = "2026-11-27T15:30:00+05:30"
BASE = {"instrument_id": OPTION_ID, "price": "99.75", "price_at": CLOSE_AT, "source": "feed-stream"}


def seed(rows, store=None, **kw):
    store = store or SeedStore()
    return store, lcs.run_seed(json.dumps({"rows": rows}), store, KNOWN, aliases=ALIASES, **kw)


# ---- M1 zero ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("price", ["0", "0.00", "-0.00", 0, 0.0])
def test_m1_a_zero_price_is_refused(price):
    store, res = seed([{**BASE, "price": price}])
    assert store.written == [] and "not a whole number of paise" in res.skipped[0][2]


def test_m1_check_row_refuses_zero_for_the_feed_writer_too():
    with pytest.raises(ValueError, match="paise"):
        lcs.check_row((OPTION_ID, FRI, Decimal("0.00"), at(FRI, 15, 29), "feed_book"))


# ---- M2 time must be a label-safe own time ---------------------------------------------------------------------------
@pytest.mark.parametrize("raw,reason", [
    ("2026-11-28T10:00:00+05:30", "not a trading day"),  # Saturday: the label would say 27 Nov 15:30:00
    ("2026-10-20T11:00:00+05:30", "not a trading day"),  # Dussehra, an NSE F&O holiday
    ("2026-11-27T08:00:00+05:30", "before the open"),
    ("2026-11-27", "time of day"),
    (1795800000, "time must be an ISO date-time with offset"),
])
def test_m2_a_row_whose_label_would_differ_from_its_own_time_is_refused(raw, reason):
    store, res = seed([{**BASE, "price_at": raw}], assume_ist=True)
    assert store.written == [] and reason in res.skipped[0][2], res.skipped


def test_m2_the_open_and_a_later_time_on_a_trading_day_are_kept_with_their_own_time():
    for raw in ("2026-11-27T09:15:00+05:30", "2026-11-27T18:05:00+05:30", CLOSE_AT):
        store, res = seed([{**BASE, "price_at": raw}])
        assert res.written == 1 and store.written[0][0][3] == datetime.datetime.fromisoformat(raw), raw


# ---- M3 ambiguous keys ---------------------------------------------------------------------------------------------
def test_m3_two_keys_for_one_field_are_refused_naming_both_and_a_map_flag_chooses():
    row = {"instrument_id": OPTION_ID, "ltp": "99.75", "timestamp": "2026-11-27T18:05:00+05:30",
           "last_trade_time": "2026-11-27T15:29:58+05:30", "source": "feed-stream"}
    with pytest.raises(lcs.SeedFileError) as err:
        seed([row])
    message = str(err.value)
    assert "timestamp" in message and "last_trade_time" in message and "--map price_at=<key>" in message
    store, _ = seed([row], overrides={"price_at": "last_trade_time"})
    assert store.written[0][0][3] == at(FRI, 15, 29, 58)


def test_m3_a_map_naming_a_key_that_is_not_in_the_first_row_is_refused():
    with pytest.raises(lcs.SeedFileError, match="no key nope"):
        seed([BASE], overrides={"price": "nope"})


def test_m3_close_is_not_a_price_name_it_is_the_previous_days_close():
    row = {"instrument_id": OPTION_ID, "close": "99.75", "price_at": CLOSE_AT, "source": "s"}
    with pytest.raises(lcs.SeedFileError, match="cannot map the field price"):
        seed([row])
    store, _ = seed([row], overrides={"price": "close"})  # the owner can still say so, explicitly
    assert store.written[0][0][2] == Decimal("99.75")


def test_m3_the_map_flag_parses_field_equals_key():
    assert lcs.parse_maps(["price_at=last_trade_time", "price=ltp"]) == {"price_at": "last_trade_time", "price": "ltp"}
    with pytest.raises(lcs.SeedFileError, match="field=key"):
        lcs.parse_maps(["price_at"])
    with pytest.raises(lcs.SeedFileError, match="unknown field"):
        lcs.parse_maps(["colour=red"])


# ---- M4 the feed's own frame is never replaced -----------------------------------------------------------------------
def test_m4_a_seed_never_replaces_a_frame_the_feed_delivered_for_the_same_day():
    provider = provider_with(("101.00", at(FRI, 15, 29, 58)))  # the broker's own by-close frame
    lc = next(x for x in listed() if f"{x.contract.exchange_segment}:{x.contract.exchange_token}" == OPTION_ID)
    assert not provider.book.seed_close(lcs.quote_of(lc, Decimal("99.75"), at(FRI, 15, 30)), at(FRI, 19))
    assert provider.book.get(OPTION_ID, at(FRI, 19, 1)).ltp == Decimal("101.00")


# ---- M5 the database line and the restart line ----------------------------------------------------------------------
class TargetStore(SeedStore):
    def target(self) -> str:
        return "db.example:5433/ofo"


@pytest.mark.parametrize("check", [False, True])
def test_m5_the_database_is_named_first_and_the_restart_line_closes_the_output(tmp_path, check):
    path = tmp_path / "f.json"
    path.write_text(json.dumps({"rows": [BASE]}))
    out: list[str] = []
    assert lcs.seed_command(str(path), TargetStore(), KNOWN, check=check, aliases=ALIASES, out=out.append) == 0
    assert out[0] == "database: db.example:5433/ofo"
    assert out[-1] == "Restart the API to load these closes (a running API reads the table once per close)."


def test_m5_the_target_never_shows_the_user_or_password():
    store = lcs.PostgresLastCloseStore("postgresql+asyncpg://someuser:pw-placeholder-example@db.example:5433/ofo")
    try:
        assert store.target() == "db.example:5433/ofo"
    finally:
        store.close()


# ---- M6 database errors exit 2 in one line ---------------------------------------------------------------------------
@pytest.mark.parametrize("error", [IntegrityError("INSERT ...", {}, Exception("duplicate key value\nDETAIL: x")),
                                   ProgrammingError("INSERT ...", {}, Exception("permission denied for table"))])
def test_m6_a_database_error_exits_2_with_one_line_and_no_traceback(tmp_path, error):
    class Boom(SeedStore):
        def insert_new(self, rows):
            raise error

    path = tmp_path / "f.json"
    path.write_text(json.dumps({"rows": [BASE]}))
    out: list[str] = []
    assert lcs.seed_command(str(path), Boom(), KNOWN, check=False, aliases=ALIASES, out=out.append) == lcs.EXIT_FAILED
    last = out[-1]
    assert "\n" not in last and type(error).__name__ in last and "Traceback" not in last


# ---- minor ---------------------------------------------------------------------------------------------------------
def test_the_exchange_prefix_must_match_the_contracts_segment():
    ref = zerodha_ref(OPTION_ID)  # an NSE_FO option
    _, ok = seed([{**BASE, "instrument_id": f"NFO:{ref.broker_symbol}"}])
    assert ok.written == 1
    for wrong in ("BFO", "NSE", "BSE"):
        _, res = seed([{**BASE, "instrument_id": f"{wrong}:{ref.broker_symbol}"}])
        assert res.written == 0 and "exchange prefix" in res.skipped[0][2], wrong


def test_a_number_that_is_both_a_kite_token_and_an_exchange_token_is_refused_with_the_form_to_use():
    known = {"NSE_FO:1": ("A", None), "NSE_FO:2": ("B", None)}
    aliases = {"token:5": ("NSE_FO:1",), "xtoken:5": ("NSE_FO:2",)}
    row = {**BASE, "instrument_id": 5}
    res = lcs.run_seed(json.dumps([row]), SeedStore(), known, aliases=aliases)
    assert res.written == 0 and "ambiguous" in res.skipped[0][2] and "book id" in res.skipped[0][2]
    only = lcs.run_seed(json.dumps([{**row, "instrument_id": 6}]), SeedStore(), known,
                        aliases={"xtoken:6": ("NSE_FO:2",)})
    assert only.written == 1


def test_utf16_with_a_byte_order_mark_loads_and_an_undecodable_file_says_save_as_utf8(tmp_path):
    good, bad = tmp_path / "u16.json", tmp_path / "bad.json"
    good.write_bytes(json.dumps({"rows": [BASE]}).encode("utf-16"))
    bad.write_bytes(b"\xff\xfe\x00")  # a UTF-16 mark followed by a truncated character
    out: list[str] = []
    assert lcs.seed_command(str(good), SeedStore(), KNOWN, check=False, aliases=ALIASES, out=out.append) == 0
    out.clear()
    assert lcs.seed_command(str(bad), SeedStore(), KNOWN, check=False, aliases=ALIASES,
                            out=out.append) == lcs.EXIT_FAILED
    assert "save the file as UTF-8" in out[-1]


def test_seeding_inserts_with_do_nothing_semantics_and_reports_a_lost_race_as_unchanged():
    class Racy(SeedStore):
        upserts = 0

        def write_closes(self, rows):
            type(self).upserts += 1
            return super().write_closes(rows)

        def insert_new(self, rows):  # another writer got there first for one of the two rows
            self.inserted = list(rows)
            return len(self.inserted) - 1

    index_id = next(i for i in KNOWN if i.startswith("NSE_INDEX:"))
    store, res = seed([BASE, {**BASE, "instrument_id": index_id}], Racy())
    assert Racy.upserts == 0 and len(store.inserted) == len((BASE, index_id))
    assert (res.written, res.unchanged) == (1, 1)
