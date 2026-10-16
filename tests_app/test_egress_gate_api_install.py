"""W-080 integration (REQ-073 AC-4): the API process installs the runtime egress gate in ``create_app``.

Importing ``ofo`` no longer installs the gate (so migrations and scripts may run git or ruff). These tests prove, each
in a FRESH Python process (the gate is process-wide and this suite's conftest already installed it here), that:

- after ``create_app()`` and before any request, the gate is installed: a connect to TEST-NET 192.0.2.1 (RFC 5737,
  never routed, never Kite) and a process start are both refused with ``EgressRefused``;
- the lifespan refuses to start an app whose process never installed the gate.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
TEST_NET = "192.0.2.1"


def _fresh(code: str) -> list[str]:
    env = {k: v for k, v in os.environ.items() if k not in {"LIVE_MARKET", "OUTCOME_REPLAY", "TEST_CATALOGUE_DATE"}}
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, cwd=BACKEND,  # noqa: S603
                         env=env, check=False)
    assert out.returncode == 0, out.stderr
    return out.stdout.split()


def test_create_app_installs_the_gate_before_the_first_request() -> None:
    code = ("import socket, subprocess, sys\nfrom ofo.broker import egress\nimport ofo_app.main as m\n"
            "print(egress.installed())\napp = m.create_app()\nprint(egress.installed())\n"
            f"try:\n    socket.create_connection(('{TEST_NET}', 443), timeout=2)\n"
            "except egress.EgressRefused:\n    print('connect-refused')\n"
            "try:\n    subprocess.run([sys.executable, '-c', 'pass'])\n"
            "except egress.EgressRefused:\n    print('spawn-refused')\n")
    assert _fresh(code) == ["False", "True", "connect-refused", "spawn-refused"]


def test_the_lifespan_refuses_a_process_without_the_gate() -> None:
    code = ("import asyncio\nfrom fastapi import FastAPI\nfrom ofo.broker import egress\nimport ofo_app.main as m\n"
            "async def run():\n    async with m._lifespan(FastAPI()):\n        print('started')\n"
            "try:\n    asyncio.run(run(), loop_factory=asyncio.SelectorEventLoop)\n"
            "except egress.EgressRefused:\n    print('refused')\nprint(egress.installed())\n")
    assert _fresh(code) == ["refused", "False"]
