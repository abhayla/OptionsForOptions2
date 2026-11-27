"""REQ-049 AC-4 (Lane Q1 round 2) + ADR-056 (wording integrity): one adjustment check scans each distinct platform text
once, not once per read of the same message; a refused text is refused every time (a failure is never remembered).

Real PostgreSQL, the app's real route. The scan is counted by a profile hook on the checker's own code object (the
checker must not be swapped or wrapped: ADR-056 (1), the identity check refuses a swapped one).
"""
from __future__ import annotations

import collections
import sys

import pytest
from httpx import ASGITransport, AsyncClient
from ofo import wording
from ofo_app import db as app_db
from test_adjustment_check import _reset_engine, _seeded, app_db_url  # noqa: F401
from test_plan_watch import _arm

_SCAN = wording.check_platform_text.__code__


class _Count:
    def __init__(self) -> None:
        self.texts: collections.Counter[str] = collections.Counter()

    def __call__(self, frame, event, _arg):
        if event == "call" and frame.f_code is _SCAN:
            self.texts[str(frame.f_locals.get("text"))] += 1


async def _get(client: AsyncClient, url: str) -> None:
    r = await client.get(url)
    assert r.status_code == 200, (url, r.status_code, r.text[:200])  # noqa: PLR2004


async def test_one_check_scans_each_distinct_text_once(app_db_url, monkeypatch):  # noqa: F811
    sid = await _seeded(app_db_url, monkeypatch, "ADJ-01")
    await _arm(app_db_url, sid)
    from ofo_app.main import create_app  # noqa: PLC0415 - the env above must be set first
    _reset_engine()
    app = create_app()
    url = f"/api/strategies/{sid}/adjustment-check"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        await _get(ac, url)  # warm: imports, caches
        for mod in ("ofo.errors.model", "ofo.errors.explanations"):  # a cold start: the scans the request itself makes
            getattr(sys.modules[mod], "_PASSED", {}).clear()
        count = _Count()
        sys.setprofile(count)
        try:
            await _get(ac, url)
        finally:
            sys.setprofile(None)
    await app_db.close_db()
    assert count.texts, "the check made no wording scan at all: the spy is blind"
    repeated = {t[:70]: n for t, n in count.texts.items() if n > 1}
    assert not repeated, f"{sum(count.texts.values())} scans of {len(count.texts)} distinct texts; repeated: {repeated}"


def test_a_refused_text_is_refused_every_time():
    """The same advice text, and a good one, through the message builder's own check: the advice text raises on the
    first and every later call (a failure is never remembered); the good text passes every time."""
    from ofo.errors import model  # noqa: PLC0415
    from ofo.errors.classes import ErrorClass  # noqa: PLC0415

    def fields(what: str) -> dict:
        return {"error_class": ErrorClass.USER_INPUT, "code": "USER_INPUT_001", "what_happened": what,
                "impact": "Nothing is placed.", "what_is_blocked": "The order is blocked.",
                "next_action": "Open the strategy and read the numbers.", "external": None}

    for _ in range(3):
        with pytest.raises(ValueError, match="banned wording"):
            model._checked(fields("You should buy this, it is the best trade"))  # noqa: SLF001
        assert model._checked(fields("The lot size entered is not valid."))["code"] == "USER_INPUT_001"  # noqa: SLF001
