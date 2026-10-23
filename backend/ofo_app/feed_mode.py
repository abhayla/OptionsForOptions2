"""REQ-113 AC-1/AC-3: where the Kite price socket lives, chosen once at start-up from an allow-list.

``inprocess``  the API process holds the socket (the one-process case; no bus). Refused when ``APP_ENV=production`` and
               a live market is requested: a deploy would cut every socket (AC-2).
``bus``        the API opens no Kite socket; the market-data process (``ofo_app.feed_main``) does, and the two talk
               through Redis Streams (``ofo_app.feed_bus``).

Any other value (including an empty one, other case or padding) refuses start-up: the value is matched exactly, so a
typo can never silently pick a mode.
"""
from __future__ import annotations

import os

INPROCESS, BUS = "inprocess", "bus"
MODES = frozenset({INPROCESS, BUS})


class FeedModeRefused(RuntimeError):
    """The feed mode (or the bus address it needs) is not allowed here; nothing was started."""


def feed_mode() -> str:
    """FEED_MODE exactly as set; ``inprocess`` when it is not set at all."""
    return os.environ.get("FEED_MODE", INPROCESS)


def redis_url() -> str:
    url = os.environ.get("REDIS_URL", "")
    if not url:
        raise FeedModeRefused("FEED_MODE=bus needs REDIS_URL (the bus address)")
    return url


def require_valid(app_env: str, live_requested: bool) -> str:
    """Returns the mode, or raises ``FeedModeRefused``. Called by ``create_app`` before anything is served."""
    mode = feed_mode()
    if mode not in MODES:
        raise FeedModeRefused(f"FEED_MODE must be one of {sorted(MODES)}; got {mode!r}")
    if mode == INPROCESS and app_env == "production" and live_requested:
        raise FeedModeRefused("FEED_MODE=inprocess with a live market is refused when APP_ENV=production: "
                              "use FEED_MODE=bus so an API deploy does not cut the price socket (REQ-113 AC-2)")
    if mode == BUS and live_requested:
        redis_url()
    return mode
