"""W-080 integration (REQ-073 AC-4): every process that can reach Kite installs the runtime egress gate.

Importing ``ofo`` alone no longer installs the gate (so migrations and scripts may run git or ruff). It is installed by
``create_app`` and by importing any Kite door module. These tests prove, each in a FRESH Python process (the gate is
process-wide and this suite's conftest already installed it here), that:

- after ``create_app()`` and before any request, a connect to TEST-NET 192.0.2.1 (RFC 5737, never routed, never
  Kite) and a process start are both refused with ``EgressRefused``;
- a process that imports any Kite door, or runs ``ofo_app.history_finalize`` (never calls create_app), is gated;
- the lifespan refuses to start when the gate is not installed.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "backend"
TEST_NET = "192.0.2.1"

_HEAD = "import socket, subprocess, sys\nfrom ofo.broker import egress\n"
_PROBE = (f"try:\n    socket.create_connection(('{TEST_NET}', 443), timeout=2)\n"
          "except egress.EgressRefused:\n    print('connect-refused')\n"
          "try:\n    subprocess.run([sys.executable, '-c', 'pass'])\n"
          "except egress.EgressRefused:\n    print('spawn-refused')\n")


def _fresh(code: str) -> list[str]:
    env = {k: v for k, v in os.environ.items() if k not in {"LIVE_MARKET", "OUTCOME_REPLAY", "TEST_CATALOGUE_DATE"}}
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, cwd=BACKEND,  # noqa: S603
                         env=env, check=False)
    assert out.returncode == 0, out.stderr
    return out.stdout.split()


def test_create_app_installs_the_gate_before_the_first_request() -> None:
    """The API entry module loads the Kite doors (its import already installs the gate) and create_app installs it
    again, unconditionally: after create_app, before any request, a connect and a process start are refused."""
    code = _HEAD + "import ofo_app.main as m\napp = m.create_app()\nprint(egress.installed())\n" + _PROBE
    assert _fresh(code) == ["True", "connect-refused", "spawn-refused"]


@pytest.mark.parametrize("module", ["ofo_app.kite_http", "ofo_app.kite_ws", "ofo_app.kite_history",
                                    "ofo_app.kite_margin", "ofo.broker.kite_http", "ofo.instruments.downloader"])
def test_a_process_that_imports_a_kite_door_is_gated_without_create_app(module: str) -> None:
    """Review MAJOR: importing any Kite door installs the gate, so a process that reaches Kite without create_app
    refuses a connect to TEST-NET and a process start."""
    code = _HEAD + f"import {module}\nprint(egress.installed())\n" + _PROBE
    assert _fresh(code) == ["True", "connect-refused", "spawn-refused"]


def test_history_finalize_entry_point_is_gated_before_it_does_anything() -> None:
    """``python -m ofo_app.history_finalize`` builds KiteHistory and never calls create_app. Its main() imports the
    Kite door on its first line, so the gate is on before argument parsing, the database or Kite. A bad argument
    stops main() right after those imports (argparse exits 2)."""
    code = (_HEAD + "import ofo_app.history_finalize as h\nprint(egress.installed())\n"
            "try:\n    h.main(['--no-such-flag'])\nexcept SystemExit:\n    pass\nprint(egress.installed())\n" + _PROBE)
    assert _fresh(code) == ["False", "True", "connect-refused", "spawn-refused"]


def test_the_lifespan_refuses_when_the_gate_is_not_installed() -> None:
    """Defence in depth: the lifespan reads installed() itself. The hook cannot be removed, so the not-installed state
    is simulated in a fresh process by clearing the flag the lifespan reads (test only)."""
    code = ("import asyncio\nfrom fastapi import FastAPI\nfrom ofo.broker import egress\nimport ofo_app.main as m\n"
            "egress._state['installed'] = False\n"
            "async def run():\n    async with m._lifespan(FastAPI()):\n        print('started')\n"
            "try:\n    asyncio.run(run(), loop_factory=asyncio.SelectorEventLoop)\n"
            "except egress.EgressRefused:\n    print('refused')\n")
    assert _fresh(code) == ["refused"]
