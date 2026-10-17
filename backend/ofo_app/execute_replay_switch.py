"""The TEST-ONLY Execute replay switch (W-101), kept apart from ``ofo_app.execute_replay`` so ``create_app`` can
read and refuse it WITHOUT importing the replay (which reads test fixtures): a production start-up never touches
tests/fixtures.
"""
from __future__ import annotations

import os

ENV_NAME = "EXECUTE_REPLAY"
_TRUE = {"1", "true", "yes", "on"}


class ExecuteReplayRefused(RuntimeError):
    """The Execute replay was requested outside APP_ENV=test."""


def replay_requested() -> bool:
    return os.environ.get(ENV_NAME, "").strip().lower() in _TRUE


def require_test_env(app_env: str) -> None:
    """Allow-list: exactly ``test``; every other value (empty, production, a case or space variant) is refused."""
    if app_env != "test":
        raise ExecuteReplayRefused(f"{ENV_NAME} is a test-only setting: it needs APP_ENV=test")
