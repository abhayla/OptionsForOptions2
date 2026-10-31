"""ADR-220 (1): the five server roles are named in code, and ``python -m ofo_app.liveprices`` is the liveprices role's
start command (REQ-113 market-data process), delegating to ``feed_main.main`` with no logic of its own."""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

from ofo_app import feed_main, liveprices, roles

BACKEND = pathlib.Path(roles.__file__).resolve().parents[1]


def test_the_five_roles_of_adr_220_are_named_with_their_start_modules():
    assert [r.name for r in roles.ROLES] == ["api", "maths", "user orders", "liveprices", "background"]
    assert {r.name: r.start_module for r in roles.ROLES} == {
        "api": None, "maths": None, "user orders": None, "liveprices": "ofo_app.liveprices", "background": None}


def test_python_m_ofo_app_liveprices_help_exits_0_without_starting_the_feed():
    env = {**os.environ, "PYTHONPATH": str(BACKEND) + os.pathsep + os.environ.get("PYTHONPATH", "")}
    done = subprocess.run([sys.executable, "-m", roles.LIVEPRICES.start_module, "--help"],  # noqa: S603 - fixed argv
                          cwd=BACKEND, env=env, capture_output=True, text=True, timeout=60, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    assert "liveprices" in done.stdout and "market-data process" in done.stdout
    assert "market-data process ended" not in done.stdout + done.stderr  # the feed itself never started


def test_liveprices_delegates_to_feed_main_main(monkeypatch):
    calls = []
    monkeypatch.setattr(feed_main, "main", lambda: calls.append("feed_main.main") or 0)
    assert liveprices.main([]) == 0
    assert calls == ["feed_main.main"]
