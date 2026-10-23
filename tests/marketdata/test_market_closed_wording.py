"""REQ-114 AC-7 / ADR-177: the market-closed wording has one set of characters in the backend and the frontend."""
from __future__ import annotations

import datetime
import pathlib
import re

import pytest
from ofo.marketdata.disconnect import market_closed_message

pytestmark = pytest.mark.repo_scan  # walks the source trees

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
AFTER_CLOSE = datetime.datetime(2026, 10, 8, 15, 30, tzinfo=IST)


def test_adr_177_one_wording_in_backend_and_frontend_and_the_old_wording_nowhere_a_user_sees_it():
    """AC-7 / ADR-177: the backend message and the frontend's marketClosedText are the same characters; the old
    "Market closed - last price" wording is in no backend, frontend source, or test tree."""
    root = pathlib.Path(__file__).resolve().parents[2]
    front = (root / "frontend" / "src" / "lib" / "sharedStateText.js").read_text(encoding="utf-8")
    prefix = re.search(r"MARKET_CLOSED_PREFIX = '([^']+)'", front)
    assert prefix is not None and prefix.group(1) == "Market closed. Prices are from "
    assert market_closed_message(AFTER_CLOSE) == f"{prefix.group(1)}03:30:00 PM."
    needle = "Market closed - last price"
    trees = [root / "backend", root / "frontend" / "src", root / "frontend" / "e2e", root / "frontend" / "tests",
             root / "tests_app", root / "tests"]
    me = pathlib.Path(__file__).resolve()
    hits = [str(f) for t in trees for f in t.rglob("*") if f.is_file() and f.suffix in {".py", ".js", ".ts", ".vue"}
            and f != me and needle in f.read_text(encoding="utf-8", errors="replace")]
    assert hits == []
