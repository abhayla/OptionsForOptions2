"""Lane R round 2: with NO logging configured (as under `uvicorn --factory`), the request line reaches stderr."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

SCRIPT = textwrap.dedent("""
    import asyncio
    from httpx import ASGITransport, AsyncClient
    from ofo_app.db import get_db
    from ofo_app.main import create_app

    class Db:
        async def execute(self, *a, **k):
            return None

    async def main():
        app = create_app()
        async def db():
            yield Db()
        app.dependency_overrides[get_db] = db
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            await c.get("/health")
            await c.get("/health")

    asyncio.run(main())
""")


def test_unconfigured_process_prints_the_request_line_once_per_request_with_time() -> None:
    env = {k: v for k, v in os.environ.items() if k.lower() not in {"https_proxy", "http_proxy", "all_proxy"}}
    env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent / "backend")
    out = subprocess.run(  # noqa: S603
        [sys.executable, "-c", SCRIPT], capture_output=True, text=True, env=env, timeout=120,
        check=False)
    lines = [ln for ln in out.stderr.splitlines() if "request GET /health 200" in ln]
    assert len(lines) == 2, out.stderr[-2000:]  # noqa: PLR2004
    assert re.match(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", lines[0]), lines[0]
