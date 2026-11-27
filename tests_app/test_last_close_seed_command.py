"""The one-time seed command (coordinator ruling 27 Nov 2026): `python -m ofo_app.last_close_store seed <file.json>`.

Fakes only (no database here). The snapshot row is a price read AFTER the close on Fri 27 Nov 2026: it keeps its own
time and source, the screens print that time (never 15:30:00), and the feed writer's rows keep the 15:30 limit.
Answer states for a row: written, unchanged (same row already stored), refused (each reason), kept (a different close is
already stored for that day). Exit 0 with the counts; 2 only when the file cannot be read or the database is down.
"""
from __future__ import annotations

import datetime
import json
from decimal import Decimal

import pytest
from ofo_app import last_close_store as lcs
from test_last_close_store import (
    OPTION_ID,
    TUE,
    WED,
    FakeStore,
    at,
    listed,
    provider_with,
    real_day,
)

FRI = datetime.date(2026, 11, 27)
SNAPSHOT_AT = "2026-11-27T18:05:00+05:30"
SOURCE = "owner_snapshot_2026-11-27"
INDEX_ID = "NSE_INDEX:256265"
KNOWN = {OPTION_ID: ("NIFTY", datetime.date(2026, 12, 1)), INDEX_ID: ("NIFTY", None)}


class SeedStore(FakeStore):
    """FakeStore plus what the command reads: the rows already stored for given keys."""

    def __init__(self, read_fail: bool = False) -> None:
        super().__init__(read_fail=read_fail)
        self.rows: dict = {}

    def read_rows(self, keys):
        if self.read_fail:
            raise OSError("database down")
        return {k: v for k, v in self.rows.items() if k in set(keys)}

    def write_closes(self, rows):
        n = super().write_closes(rows)
        self.rows.update({(r[0], r[1]): (r[2], r[3], r[4]) for r in rows})
        return n


def snap(**over) -> dict:
    row = {"instrument_id": OPTION_ID, "name": "NIFTY", "expiry": "2026-12-01", "price": "99.75",
           "price_at": SNAPSHOT_AT, "source": SOURCE}
    row.update(over)
    return row


def run(rows, store=None, *, check=False, known=KNOWN):
    store = store or SeedStore()
    return store, lcs.run_seed(json.dumps({"rows": rows}), store, known, check=check)


def contract():
    return next(x for x in listed() if f"{x.contract.exchange_segment}:{x.contract.exchange_token}" == OPTION_ID)


def test_a_snapshot_row_is_written_with_its_own_time_and_source_and_the_counts_are_printed():
    store, res = run([snap()])
    assert store.written == [[(OPTION_ID, FRI, Decimal("99.75"), at(FRI, 18, 5), SOURCE)]]
    assert (res.written, res.unchanged, res.skipped) == (1, 0, [])
    text = lcs.format_result(res, "snap.json")
    assert text == "last_close seed snap.json: 1 rows read\nwritten 1\nunchanged 0\nskipped 0"


@pytest.mark.parametrize("over,reason", [
    ({"price": True}, "price must be a string or a number"),
    ({"price": 99.755}, "not a whole number of paise"),
    ({"price": None}, "price must be a string or a number"),
    ({"price": "99.755"}, "not a whole number of paise"),
    ({"price": "abc"}, "price is not a number"),
    ({"price": "-1.00"}, "not a whole number of paise"),
    ({"price_at": None}, "missing time"),
    ({"price_at": "2026-11-27T18:05:00"}, "time has no zone"),
    ({"price_at": "yesterday"}, "time is not ISO"),
    ({"instrument_id": "NSE_FO:1"}, "unknown instrument id"),
    ({"instrument_id": ""}, "missing instrument id"),
    ({"name": "BANKNIFTY"}, "name does not match"),
    ({"expiry": "2026-12-08"}, "expiry does not match"),
    ({"source": ""}, "missing source"),
    ({"source": "feed_book"}, "after the close"),
])
def test_each_bad_row_is_refused_with_its_reason_and_nothing_is_written(over, reason):
    store, res = run([snap(**over)])
    assert store.written == [] and res.written == 0 and len(res.skipped) == 1
    assert reason in res.skipped[0][2], res.skipped


def test_a_row_that_is_not_an_object_and_a_duplicate_in_the_file_are_refused():
    store, res = run([snap(), "text", snap(price="100.00")])
    assert res.written == 1 and [r[0] for r in res.skipped] == [2, 3]
    assert "not an object" in res.skipped[0][2] and "duplicate" in res.skipped[1][2]
    assert store.written[0][0][2] == Decimal("99.75")


def test_a_second_run_writes_nothing_and_says_unchanged():
    store, first = run([snap()])
    _, second = run([snap()], store)
    assert (first.written, second.written, second.unchanged) == (1, 0, 1) and len(store.written) == 1
    assert "unchanged 1" in lcs.format_result(second, "snap.json")


def test_a_different_close_already_stored_for_the_day_is_kept_never_overwritten():
    store, _ = run([snap()])
    _, res = run([snap(price="50.00")], store)
    assert res.written == 0 and "already stored" in res.skipped[0][2] and len(store.written) == 1


def test_check_counts_the_same_without_writing():
    store, res = run([snap(), snap(price="1.001", instrument_id=INDEX_ID, expiry=None)], check=True)
    assert store.written == [] and (res.written, len(res.skipped), res.checked) == (1, 1, True)
    text = lcs.format_result(res, "snap.json")
    assert "would write 1" in text and "skipped 1" in text and "row 2 " + INDEX_ID in text


def test_without_a_catalogue_an_unknown_id_cannot_be_told_and_the_report_says_so():
    _, res = run([snap(instrument_id="NSE_FO:1")], known=None)
    assert res.written == 1 and "catalogue not checked" in lcs.format_result(res, "snap.json")


def test_exit_codes_unreadable_file_and_dead_database_are_2_a_refused_row_is_0(tmp_path):
    good, bad = tmp_path / "good.json", tmp_path / "bad.json"
    good.write_text(json.dumps({"rows": [snap(), snap(price="1.505", instrument_id=INDEX_ID, expiry=None)]}))
    bad.write_text("{not json")
    out: list[str] = []
    assert lcs.seed_command(str(good), SeedStore(), KNOWN, check=False, out=out.append) == 0
    assert any("skipped 1" in line for line in out)
    assert any("not a whole number of paise" in line for line in out)
    failed = lcs.EXIT_FAILED
    assert lcs.seed_command(str(bad), SeedStore(), KNOWN, check=False, out=out.append) == failed
    assert lcs.seed_command(str(tmp_path / "gone.json"), SeedStore(), KNOWN, check=False, out=out.append) == failed
    assert lcs.seed_command(str(good), SeedStore(read_fail=True), KNOWN, check=False, out=out.append) == failed


def test_a_stored_after_close_row_is_served_as_the_first_frame_after_the_close_with_its_own_time():
    provider = provider_with()
    quote = lcs.quote_of(contract(), Decimal("99.75"), at(FRI, 18, 5))
    assert provider.book.seed_close(quote, at(TUE, 8))
    q = provider.book.get(OPTION_ID, at(TUE, 8, 1))
    assert (q.ltp, q.timestamp, q.price_at) == (Decimal("99.75"), at(FRI, 18, 5), at(FRI, 18, 5))
    assert not provider.book.seed_close(lcs.quote_of(contract(), Decimal("1.00"), at(FRI, 19)), at(TUE, 8, 2))


def test_a_stored_close_made_by_the_close_beats_a_stored_after_close_row_of_the_same_day():
    provider = provider_with()
    provider.book.seed_close(lcs.quote_of(contract(), Decimal("99.75"), at(FRI, 18, 5)), at(TUE, 8))
    provider.book.seed_close(lcs.quote_of(contract(), Decimal("98.00"), at(FRI, 15, 29)), at(TUE, 8))
    assert provider.book.get(OPTION_ID, at(TUE, 9)).ltp == Decimal("98.00")


def test_a_stored_after_close_row_never_replaces_a_live_frame_or_a_held_close():
    provider = real_day()  # Tue 1 Dec: 99.75 made by the close, later frames 99.60 / 100.10
    assert not provider.book.seed_close(lcs.quote_of(contract(), Decimal("7.00"), at(TUE, 18, 5)), at(TUE, 19))
    assert provider.book.get(OPTION_ID, at(TUE, 19)).ltp == Decimal("99.75")


def test_the_seeded_after_close_row_is_hidden_while_open_and_the_label_calls_it_a_later_leg():
    from ofo_app.routes.outcome import MarketState, closed_label  # noqa: PLC0415
    provider = provider_with()
    provider.book.seed_close(lcs.quote_of(contract(), Decimal("99.75"), at(FRI, 18, 5)), at(TUE, 8))
    assert provider.book.get(OPTION_ID, at(TUE, 10)) is None
    held = lcs.quote_of(contract(), Decimal("90.00"), at(FRI, 15, 29, 59))
    out = closed_label(MarketState(closed=True, last_price_at=None),
                       [held, provider.book.get(OPTION_ID, at(TUE, 8, 5))], None)
    assert str(out.text) == "Market closed. Prices are from 15:29:59; 1 leg as of 18:05:00."


@pytest.mark.parametrize("source,price_at,ok", [("feed_book", at(TUE, 15, 30, 1), False),
                                                ("feed_book", at(TUE, 15, 30), True),
                                                ("owner_snapshot", at(TUE, 18, 5), True),
                                                ("owner_snapshot", at(WED, 0, 5), False)])
def test_check_row_keeps_the_close_limit_for_the_feed_writer_only(source, price_at, ok):
    row = ("X:1", TUE, Decimal("99.75"), price_at, source)
    if ok:
        lcs.check_row(row)
    else:
        with pytest.raises(ValueError):
            lcs.check_row(row)
