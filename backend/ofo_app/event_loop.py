"""The app runs only on asyncio's selector event loop (REQ-073 AC-4, W-080 round 7).

The runtime egress gate (``ofo.broker.egress``) sees a connect only through Python's ``socket.connect`` audit event.
Measured on Python 3.13: the Windows ProactorEventLoop connects without raising it, and uvloop is native code that
raises none. So every start path uses ``selector_loop`` (uvicorn: ``--loop ofo_app.event_loop:selector_loop``; uvicorn's
own ``--loop asyncio`` still picks the Proactor loop on Windows) and the lifespan refuses to start on any other loop.
"""
from __future__ import annotations

import asyncio

#: uvicorn's custom loop factory (``--loop ofo_app.event_loop:selector_loop``): a plain selector loop on every OS.
selector_loop = asyncio.SelectorEventLoop

UVICORN_LOOP = "ofo_app.event_loop:selector_loop"


class WrongEventLoop(RuntimeError):
    """The app was started on an event loop whose connects the egress gate cannot see."""


def require_selector_loop() -> None:
    """Raise unless the running loop is asyncio's selector loop (the Proactor loop and uvloop are refused)."""
    loop = asyncio.get_running_loop()
    if not isinstance(loop, asyncio.SelectorEventLoop):
        raise WrongEventLoop(f"the API runs only on asyncio's selector loop, not {type(loop).__name__}; start uvicorn "
                             f"with --loop {UVICORN_LOOP}")


__all__ = ["UVICORN_LOOP", "WrongEventLoop", "require_selector_loop", "selector_loop"]
