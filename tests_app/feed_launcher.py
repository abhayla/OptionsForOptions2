"""TEST-ONLY launcher (REQ-113 AC-2): starts the market-data process or the API-side feed stack as a real OS process.

``python feed_launcher.py feed <config.json>``   the REAL ``ofo_app.feed_main.run_feed`` over the REAL ``KiteSocket``
``python feed_launcher.py api <config.json>``    the REAL ``LiveMarket.start`` in ``bus`` mode (the REAL ``BusSocket``),
                                                  writing its state to a file every 100 ms (a process the test can
                                                  kill and start again)

It is the only place that enters the egress gate's test mode (a loopback Kite address is allowed only there); production
code has no switch for it. The Kite token comes from the environment, never from a command-line argument.
"""
from __future__ import annotations

import asyncio
import contextlib
import datetime
import json
import os
import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))  # pytest.ini's pythonpath

from ofo.broker import egress

egress.install()
egress._enter_test_mode([sys.executable])

from ofo.instruments.parser import parse_instruments_csv  # noqa: E402
from ofo.marketdata.kite_provider import IST  # noqa: E402
from ofo_app import feed_bus, feed_main, live_market  # noqa: E402

INSTRUMENTS = (pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "kite_ws"
               / "instruments-2026-10-08-subscribed.csv")


def clock() -> datetime.datetime:
    return datetime.datetime.now(IST)


async def run_feed(cfg: dict) -> None:
    token = os.environ["OFO_TEST_KITE_TOKEN"]
    await feed_main.run_feed(user_ref=cfg["user"], api_key="KEY-launcher", access_token=token,
                             ws_url=cfg["ws_url"], redis_url=cfg["redis_url"], clock=clock)


class _Conn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Engine:
    def connect(self):
        return _Conn()


async def _stored_token(self, config):
    return os.environ["OFO_TEST_KITE_TOKEN"]


async def _no_catalogue(conn):
    return types.SimpleNamespace(all_entries=list)


async def run_api(cfg: dict) -> None:
    """The API side through the REAL ``LiveMarket.start`` (the app's own start path, ``FEED_MODE`` / ``REDIS_URL`` from
    the environment): only the database, the catalogue and the stored session are stood in, so a start that built a Kite
    socket instead of the bus socket would connect to the fake Kite and the test would see a second connection."""
    from ofo_app import catalogue_store, db  # noqa: PLC0415

    listed = list(parse_instruments_csv(INSTRUMENTS))
    db.get_engine = _Engine
    catalogue_store.load_catalogue = _no_catalogue
    live_market.listed_for_kite = lambda entries: listed
    live_market.get_settings = lambda: types.SimpleNamespace(KITE_WS_URL=cfg["ws_url"])
    live_market.LiveMarket._stored_token = _stored_token
    market = live_market.LiveMarket()
    await market.start(types.SimpleNamespace(api_key="KEY-launcher", token_key=b"k"))
    provider = market.feed.ctx.provider
    socket = market._socket
    provider.subscribe([f"{lc.contract.exchange_segment}:{lc.contract.exchange_token}" for lc in listed])
    target = pathlib.Path(cfg["state_file"])
    while True:
        last = socket.last_frame_at if hasattr(socket, "last_frame_at") else None
        state = {"pid": os.getpid(), "frames": provider.counters["frames"], "ticks": provider.counters["ticks"],
                 "last_frame_us": None if last is None else feed_bus.to_micros(last),
                 "phase": provider.feed.phase(clock()), "socket": type(socket).__name__}
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(state))
        with contextlib.suppress(PermissionError):  # Windows: the reader has the file open this instant; next tick
            os.replace(tmp, target)
        await asyncio.sleep(0.1)


def main() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    role, cfg = sys.argv[1], json.loads(pathlib.Path(sys.argv[2]).read_text())
    asyncio.run({"feed": run_feed, "api": run_api}[role](cfg))


if __name__ == "__main__":
    main()
