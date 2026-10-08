"""W-062 AC-3 (REQ-051): the core. One-minute bars built from the REAL 2026-10-08 frames equal Kite's own candles.

Input: tests/fixtures/kite_history/ - two real recordings (09:20-09:24 and 15:06-15:12, 8 instruments) replayed through
the merged W-059 KiteProvider, and Kite's candles for the same minutes parsed as Decimal from the recorded body text.
"""
import datetime
from decimal import Decimal

from _history_fixture import WINDOWS, at, candle_bars, index_ids, replay_window
from ofo.history.bars import BarSource, MinuteBar, MinuteBarBuilder

NIFTY_CE, NIFTY_PE = "NSE_FO:44614", "NSE_FO:44615"
SENSEX_OPTIONS = ["BSE_FO:889331", "BSE_FO:889150", "BSE_FO:889773", "BSE_FO:889349"]
# the first and last minute of each window are partial; 15:08-15:10 touch the recorded network drop (checked below)
PARTIAL = {"09:19", "09:24", "15:05", "15:12"}
GAP_TOUCHED = {"15:08", "15:09", "15:10"}


def build(window: str):
    builder = MinuteBarBuilder()
    live: list[MinuteBar] = []

    def wire(fan, ids):
        fan.subscribe(lambda q: live.extend(builder.on_quote(q)), ids)

    _, _, last = replay_window(window, wire)
    live.extend(builder.flush(last + datetime.timedelta(minutes=1)))
    return builder, live


def hhmm(bar: MinuteBar) -> str:
    return bar.minute.strftime("%H:%M")


def compare(window: str):
    """(builder, live bars by id/minute, [(id, kite candle, live bar or None)] for the full non-gap minutes)."""
    builder, live = build(window)
    by = {(b.instrument_id, b.minute): b for b in live}
    rows = []
    for iid, wins in candle_bars().items():
        for k in wins[window]:
            if hhmm(k) in PARTIAL | GAP_TOUCHED:
                continue
            rows.append((iid, k, by.get((iid, k.minute))))
    return builder, by, rows


def test_every_full_minute_is_built_and_ids_are_the_eight_recorded():
    for window in WINDOWS:
        _, by, rows = compare(window)
        assert {r[0] for r in rows} == set(candle_bars())
        assert all(live is not None for _, _, live in rows)
        assert {b.source for b in by.values()} == {BarSource.LIVE}


def test_oi_volume_and_close_match_kite_per_instrument():
    stats: dict[str, dict[str, list[int]]] = {}
    oi_misses = []
    for window in WINDOWS:
        _, _, rows = compare(window)
        for iid, k, live in rows:
            s = stats.setdefault(iid, {"minutes": [0], "close": [0], "ohlc": [0], "volume": [0], "oi": [0]})
            s["minutes"][0] += 1
            s["close"][0] += live.close == k.close
            s["ohlc"][0] += (live.open, live.high, live.low, live.close) == (k.open, k.high, k.low, k.close)
            s["volume"][0] += live.volume == k.volume
            s["oi"][0] += live.oi == k.oi
            if live.oi != k.oi:
                oi_misses.append((iid, hhmm(k), live.oi, k.oi))
    report = "\n".join(f"{iid}: " + " ".join(f"{name}={v[0]}" for name, v in s.items()) for iid, s in stats.items())

    # volume: the sum of cumulative-volume rises equals Kite's minute volume on every full minute of every option
    for iid in [NIFTY_CE, NIFTY_PE, *SENSEX_OPTIONS]:
        assert stats[iid]["volume"] == stats[iid]["minutes"], report
    # OI: equal everywhere except ONE measured case: the NIFTY put's OI changed at 09:22:00 (the exchange stamps it with
    # the new minute) while Kite's 09:21 candle already carries it. The live bar keeps the earlier value; finalize fixes it.
    assert oi_misses == [(NIFTY_PE, "09:21", 4367480, 4612660)], report
    # close: every SENSEX option and the SENSEX index on every full minute; NIFTY is the weak case (F-34: 45 of 74)
    for iid in [*SENSEX_OPTIONS, "BSE_INDEX:1"]:
        assert stats[iid]["close"] == stats[iid]["minutes"], report
    total = sum(s["close"][0] for s in stats.values())
    assert total >= 45 and sum(s["minutes"][0] for s in stats.values()) == 56, report
    # an index has neither volume nor OI
    for iid in index_ids():
        assert all(r[2].volume is None and r[2].oi is None for w in WINDOWS for r in compare(w)[2] if r[0] == iid)


def test_expected_minutes_as_literal_decimals_from_kites_candles_file():
    _, by, _ = compare("0920-0924")
    sensex = by[("BSE_FO:889349", at(9, 21))]
    assert (sensex.close, sensex.volume, sensex.oi) == (Decimal("2.15"), 332680, 2141880)
    nifty = by[(NIFTY_CE, at(9, 22))]
    assert (nifty.close, nifty.volume, nifty.oi) == (Decimal("125.2"), 628940, 2939040)
    assert nifty.minute == at(9, 22) and nifty.source is BarSource.LIVE
    _, by, _ = compare("1506-1512")
    sensex = by[("BSE_FO:889349", at(15, 7))]
    assert (sensex.close, sensex.volume, sensex.oi) == (Decimal("1.4"), 207320, 3205900)
    nifty = by[(NIFTY_CE, at(15, 11))]
    assert (nifty.close, nifty.volume, nifty.oi) == (Decimal("39.1"), 97240, 5643755)


def test_the_1509_minute_is_absent_live_for_all_eight_and_present_in_kites_candles():
    builder, live = build("1506-1512")
    live_ids_1509 = {b.instrument_id for b in live if b.minute == at(15, 9)}
    assert live_ids_1509 == set()
    kite_1509 = {iid: [k for k in wins["1506-1512"] if k.minute == at(15, 9)] for iid, wins in candle_bars().items()}
    assert all(len(v) == 1 for v in kite_1509.values()) and len(kite_1509) == 8
    nifty = kite_1509[NIFTY_CE][0]
    assert (nifty.close, nifty.volume, nifty.oi, nifty.source) == (Decimal("38.3"), 132925, 5721170, BarSource.KITE)
    # the builder saw the drop: a 114 s silence from 15:08:14 to 15:10:08 across all eight instruments
    first = builder.gaps[0]
    assert (first[0], first[1]) == (at(15, 8, 14), at(15, 10, 8))


def test_trades_across_the_drop_are_not_counted_into_the_minute_after_it():
    # without the gap rule 15:10 would carry the drop's trades (NIFTY CE volume 526175 vs Kite's 236730 in the first run)
    _, live = build("1506-1512")
    by = {(b.instrument_id, b.minute): b for b in live}
    kite = {(k.instrument_id, k.minute): k for wins in candle_bars().values() for k in wins["1506-1512"]}
    for iid in [NIFTY_CE, NIFTY_PE, *SENSEX_OPTIONS]:
        assert by[(iid, at(15, 10))].volume < kite[(iid, at(15, 10))].volume
