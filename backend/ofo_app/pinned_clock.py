"""TEST-ONLY catalogue date pin (issue #237; ADR-023 trusted database clock stays the only clock outside APP_ENV=test).

A recorded instrument fixture ages past its expiries, so a browser flow over it can never run on the real database
clock. ``TEST_CATALOGUE_DATE=YYYY-MM-DD`` (with ``APP_ENV=test``) makes the ONE seam, ``pinned_today()``, answer that date;
``catalogue_picker.database_today`` (used by both catalogue routes) asks it first. The save path judges liveness from the
stored retired/delisted flags (``strategy_store.catalogue_resolver``) and reads no clock, so nothing else consults the pin.

Outside APP_ENV=test the variable is refused (the app does not start, ``main.create_app``; ``config.Settings`` refuses
it too) and is never read to change an answer: ``pinned_today`` raises rather than ignore it.
"""
from __future__ import annotations

import datetime
import os

ENV_NAME = "TEST_CATALOGUE_DATE"


class PinRefused(RuntimeError):
    """The catalogue date pin was requested outside APP_ENV=test (or is not a plain ISO date)."""


def parse_pin(value: str) -> datetime.date:
    try:
        return datetime.date.fromisoformat(value.strip())
    except ValueError:
        raise PinRefused(f"{ENV_NAME} must be a plain YYYY-MM-DD date") from None


def pin_requested() -> bool:
    return bool(os.environ.get(ENV_NAME, "").strip())


def require_test_env(app_env: str) -> None:
    if app_env != "test":
        raise PinRefused(f"{ENV_NAME} is a test-only setting: it needs APP_ENV=test")


def pinned_today() -> datetime.date | None:
    """The pinned date, or None when no pin is set. Raises PinRefused when a pin is set outside APP_ENV=test."""
    if not pin_requested():
        return None
    from ofo_app.config import app_env  # late: config is a leaf, but keep this module import-light

    require_test_env(app_env() or "")
    return parse_pin(os.environ[ENV_NAME])
