"""SQL fragments for the database's India clock. The zone name itself has one home, `ofo.timeutil.IST_ZONE_NAME`."""
from __future__ import annotations

from typing import Final

from ofo.timeutil import IST_ZONE_NAME

#: Reads a timestamp on India's wall clock: `now() AT TIME ZONE 'Asia/Kolkata'`.
IST_SQL_ZONE: Final = f"AT TIME ZONE '{IST_ZONE_NAME}'"
