"""The one home of India's clock constants: the IST offset, its zone name and the named market times.

Standard library only (the domain layer imports nothing third-party). `tests/test_one_home_constants.py` fails when
any of these values is written anywhere else under `backend/`.

Two IST tzinfo objects exist on purpose, so no caller's behaviour changed when the eleven local copies were merged:
both are the same fixed +05:30 offset and compare equal, but `IST` names itself "IST" (`strftime("%Z")`, `tzname()`)
while `IST_UNNAMED` prints "UTC+05:30", which is what the modules that built `timezone(offset)` without a name had.
"""
from __future__ import annotations

import datetime
from typing import Final

#: India Standard Time's fixed offset from UTC (no daylight saving).
IST_OFFSET: Final = datetime.timedelta(hours=5, minutes=30)
#: IST as a tzinfo whose name is "IST".
IST: Final = datetime.timezone(IST_OFFSET, "IST")
#: IST as a tzinfo with no name (tzname "UTC+05:30").
IST_UNNAMED: Final = datetime.timezone(IST_OFFSET)

#: The IANA zone name, for the database's clock.
IST_ZONE_NAME: Final = "Asia/Kolkata"
#: (The SQL fragment built from it lives in the app layer, `ofo_app.sql_time.IST_SQL_ZONE`: the domain has no SQL.)

#: The regular trading session of NSE/BSE index derivatives, IST wall clock (naive times).
SESSION_OPEN: Final = datetime.time(9, 15)
SESSION_CLOSE: Final = datetime.time(15, 30)
#: Contract expiry: the session close, as an IST-aware time.
EXPIRY_CLOSE: Final = datetime.time(15, 30, tzinfo=IST)
#: On expiry day, broker positions from this IST time on are treated as settled (naive time).
EXPIRY_DAY_SETTLE_FROM: Final = datetime.time(15, 39)
#: Minute history for a trading day is fetched up to this IST time (naive time), past the 15:30 close.
HISTORY_FETCH_UNTIL: Final = datetime.time(15, 59)


SATURDAY: Final = 5  # datetime.weekday(): Monday is 0, so 0..4 are the trading weekdays



# The market-hours check is NOT here: it needs the holiday calendar (ADR-119, REQ-114 AC-7), which this
# standard-library-only constants module cannot read. The one check is `ofo.market_calendar.is_market_open`.
