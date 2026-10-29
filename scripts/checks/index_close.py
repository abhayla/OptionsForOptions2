"""GC-TP 5a: read an index's official daily close from Kite's DAY candle, through the app's own door (read-only).

Usage (the orchestrator, after 15:30 IST):
    python scripts/orchestrator/dev_run.py <repo> python scripts/checks/index_close.py <NIFTY|SENSEX> <YYYY-MM-DD>

Spec basis: REQ-109 AC-7 ("at its intrinsic value from the official closing value of its index that day"). This is the
core proof of the settlement; the settlement job itself is a later step. It makes exactly one read-only Kite call
(``GET /instruments/historical/<token>/day``) through ``ofo_app.kite_history``; the allow-list door refuses the rest.

Refuses unless DATABASE_URL names ofo_dev (the way ``dev_run.py`` sets it). Opens the owner's cached Kite token the
way ``live_market`` does. Prints exactly one line and never the token:
    <INDEX> <date> close <value> | <INDEX> <date> no candle | <INDEX> <date> read failed: <error class>
"""
from __future__ import annotations

import asyncio
import datetime
import os
import sys
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INDEXES = {"NIFTY": ("NSE_INDEX", 1001), "SENSEX": ("BSE_INDEX", 1)}  # = ofo.instruments.models.INDEX_ROWS keys
USAGE = "usage: index_close.py <NIFTY|SENSEX> <YYYY-MM-DD>"


def refuse_unless_dev(database_url: str | None) -> None:
    if not database_url or not database_url.rstrip("/").endswith("/ofo_dev"):
        sys.exit("REFUSED: DATABASE_URL does not name ofo_dev (run through scripts/orchestrator/dev_run.py)")


def result_line(index: str, day: datetime.date, close: Decimal | None) -> str:
    return f"{index} {day.isoformat()} no candle" if close is None else f"{index} {day.isoformat()} close {close}"


def failed_line(index: str, day: datetime.date, exc: BaseException) -> str:
    return f"{index} {day.isoformat()} read failed: {type(exc).__name__}"  # the class name only, never the message


def parse_args(argv: list[str]) -> tuple[str, datetime.date]:
    if len(argv) != 2 or argv[0] not in INDEXES:  # noqa: PLR2004
        sys.exit(USAGE)
    try:
        return argv[0], datetime.date.fromisoformat(argv[1])
    except ValueError:
        sys.exit(USAGE)


async def read_close(index: str, day: datetime.date) -> str:
    from ofo.instruments.models import ZERODHA  # noqa: PLC0415 - loads only after the dev-database check
    from ofo_app import catalogue_store  # noqa: PLC0415
    from ofo_app.broker_config import load_broker_config  # noqa: PLC0415
    from ofo_app.broker_crypto import TokenCipher  # noqa: PLC0415
    from ofo_app.broker_token_store import access_token_for  # noqa: PLC0415
    from ofo_app.db import get_engine  # noqa: PLC0415
    from ofo_app.kite_history import KiteHistory  # noqa: PLC0415
    from ofo_app.live_market import OWNER_REF, listed_for_kite  # noqa: PLC0415

    config = load_broker_config()
    async with get_engine().connect() as conn:
        token = await access_token_for(conn, OWNER_REF, TokenCipher(config.token_key))
    if token is None:
        return f"{index} {day.isoformat()} read failed: NoBrokerSession"
    async with get_engine().connect() as conn:
        entries = (await catalogue_store.load_catalogue(conn)).all_entries()
    segment, exchange_token = INDEXES[index]
    row = [e for e in entries if (e.contract.exchange_segment, e.contract.exchange_token) == (segment, exchange_token)
           and e.has_ref(ZERODHA)]
    if not row:
        return f"{index} {day.isoformat()} read failed: IndexNotInCatalogue"
    kite_token = row[0].broker_refs[ZERODHA].broker_token  # Kite's instrument token (the URL's), not the exchange token
    try:
        close = KiteHistory(listed_for_kite(row), api_key=config.api_key, access_token=token).day_close(kite_token, day)
    except Exception as exc:  # noqa: BLE001 - every failure is one line naming its class
        return failed_line(index, day, exc)
    return result_line(index, day, close)


def main(argv: list[str]) -> int:
    refuse_unless_dev(os.environ.get("DATABASE_URL"))
    index, day = parse_args(argv)
    sys.path.insert(0, os.path.join(ROOT, "backend"))
    try:
        print(asyncio.run(read_close(index, day)))
    except Exception as exc:  # noqa: BLE001
        print(failed_line(index, day, exc))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
