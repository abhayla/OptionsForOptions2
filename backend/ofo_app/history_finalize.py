"""The after-close job that makes one trading day final from Kite's own one-minute candles (W-067, ADR-067).

``finalize_trading_day`` applies the W-062 rule (``ofo.history.finalize.finalize_into``) through the store, so the
store - not this job - decides every bar's source and refuses a change to a final day. This job adds only what a job
must: it refuses before the day's trading has finished, and it does nothing (no Kite call, no write) on a day already
final. It is not scheduled anywhere: putting it on a host's timer is deploy work. Kite's candles are internal use only
(ADR-066); nothing here publishes them.

Run by hand: ``python -m ofo_app.history_finalize --day 2026-10-08 --instruments-csv <Zerodha instruments csv>``
with DATABASE_URL (the application role), KITE_API_KEY and KITE_ACCESS_TOKEN in the environment. Exit codes: 0 the
day is final, 2 refused (too early), 3 the day stays provisional (a fetch or the store failed; the reason is counted).
"""
from __future__ import annotations

import argparse
import datetime
import logging
import os
import sys
from typing import Sequence

from ofo.history.bars import IST, SESSION_CLOSE, SESSION_OPEN
from ofo.history.candles import MinuteCandleSource
from ofo.history.finalize import DayResult, finalize_into
from ofo.history.store import DayStatus, HistoryStore

log = logging.getLogger("ofo_app.history_finalize")

#: The session closes 15:30 IST, but expiring SENSEX options traded until 15:39 on 2026-10-08 (F-33): finalizing at
#: 15:30 would make the day final before those minutes exist. Ten minutes after the close covers it (an earlier run
#: is refused), and the Kite range runs to 15:59 so those late minutes replace the live ones.
FINALIZE_NOT_BEFORE = datetime.time(15, 40)
FETCH_UNTIL = datetime.time(15, 59)


class FinalizeRefused(RuntimeError):
    """The day's trading has not finished, so its candles are not complete: nothing was fetched or written."""


def finalize_trading_day(store: HistoryStore, day: datetime.date, source: MinuteCandleSource,
                         instrument_ids: Sequence[str], *, now: datetime.datetime) -> DayResult:
    earliest = datetime.datetime.combine(day, FINALIZE_NOT_BEFORE, IST)
    if now.astimezone(IST) < earliest:
        raise FinalizeRefused(f"{day} cannot be finalized before {earliest:%H:%M} IST (the session closes "
                              f"{SESSION_CLOSE:%H:%M}); now is {now.astimezone(IST):%Y-%m-%d %H:%M}")
    if store.day_status(day) is DayStatus.FINAL:  # a final day never changes: no fetch, no write
        return DayResult(DayStatus.FINAL, None, {})
    start = datetime.datetime.combine(day, SESSION_OPEN, IST)
    end = datetime.datetime.combine(day, FETCH_UNTIL, IST)
    return finalize_into(store, day, list(instrument_ids), source, start=start, end=end)


def main(argv: Sequence[str] | None = None, *, now: datetime.datetime | None = None) -> int:
    from ofo.instruments.parser import parse_instruments_csv
    from ofo_app.history_store import PostgresHistoryStore
    from ofo_app.kite_history import KiteHistory

    parser = argparse.ArgumentParser(prog="python -m ofo_app.history_finalize", description=__doc__.split("\n")[0])
    parser.add_argument("--day", required=True, type=datetime.date.fromisoformat)
    parser.add_argument("--instruments-csv", required=True, help="the Zerodha instruments list the feed was built from")
    args = parser.parse_args(argv)
    now = now or datetime.datetime.now(IST)

    listed = list(parse_instruments_csv(args.instruments_csv))
    ids = [f"{lc.contract.exchange_segment}:{lc.contract.exchange_token}" for lc in listed]
    source = KiteHistory(listed, api_key=os.environ["KITE_API_KEY"], access_token=os.environ["KITE_ACCESS_TOKEN"])
    store = PostgresHistoryStore(os.environ["DATABASE_URL"])
    try:
        result = finalize_trading_day(store, args.day, source, ids, now=now)
    except FinalizeRefused as exc:
        print(f"refused: {exc}")
        return 2
    finally:
        store.close()
    print(f"{args.day}: {result.status.value}; counts={result.counts}; errors={result.errors}; "
          f"gap_minutes_missing={result.gap_minutes_missing}")
    return 0 if result.status is DayStatus.FINAL else 3


if __name__ == "__main__":
    sys.exit(main())
