"""GC-TP R-18 (ADR-209, REQ-084 AC-4): on a paper strategy the what-if target P&L, the Projected badge and the target
curve include the P&L already booked from exited legs ("includes +Rs 962.00 booked"); `include_booked` false (the chart
card's "Add Booked P&L" switch off) gives the open legs only.

Core proof: strategy 63's real roll book (frontend/tests/fixtures/paper-book-63.json, 8 orders, two exits) goes through
the one engine (ofo.tracking.orderbook.net_positions) to booked +962.00; the route adds it to the open-legs figure the
same request gets with the switch off, and the identity open + booked = shown is asserted (not absolute numbers). The
book read is the route's dependency `get_booked_reader`, overridden here with that real book. No database."""
from __future__ import annotations

import datetime
import json
import pathlib
import sys
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from ofo.errors.explanations import render_explanation
from ofo.tracking.orderbook import PaperOrder, net_positions
from ofo_app.main import create_app
from ofo_app.routes.outcome import MarketContext, get_answer_clock, get_booked_reader, get_market_context
from test_outcome_route import RATE, VALUATION, _body, provider_for_catalogue

D = Decimal
ROOT = pathlib.Path(__file__).resolve().parent.parent
BOOK_63 = ROOT / "frontend/tests/fixtures/paper-book-63.json"
HTTP_OK = 200
AT = "2026-10-12T15:00:00+05:30"
LINE = "includes +Rs 962.00 booked"


def _book_63_booked() -> Decimal:
    """Booked P&L of the real strategy 63 book, from the engine (never typed): the roll's two exits."""
    orders = json.loads(BOOK_63.read_text(encoding="utf-8"))["orders"]
    book = [PaperOrder(str(o["contract_id"]), o["side"], o["quantity"], D(o["price"]), o["kind"],
                       datetime.datetime.fromisoformat(o["placed_at"].replace("Z", "+00:00"))) for o in orders]
    return net_positions(book, {}).booked


@pytest.fixture(scope="module")
def provider():
    return provider_for_catalogue()


def _reader(booked: Decimal | None):
    async def read(_strategy_id: int) -> Decimal | None:  # None: the book could not be read
        return booked
    return lambda: read


async def _post(provider, booked: Decimal | None, **extra) -> dict:
    app = create_app()
    app.dependency_overrides[get_market_context] = lambda: MarketContext(provider, lambda: VALUATION, RATE)
    app.dependency_overrides[get_booked_reader] = _reader(booked)
    app.dependency_overrides[get_answer_clock] = lambda: (lambda: VALUATION)
    body = {**_body(provider), "both_views": True, "target_level": "23000", "target_at": AT, **extra}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post("/api/strategies/outcome", json=body)
    assert r.status_code == HTTP_OK, r.text
    return r.json()


def _pnl(out: dict) -> Decimal:
    return D(out["target"]["pnl"]["value"])


def _curve(out: dict) -> list[Decimal]:
    return [D(p["pnl"]) for p in out["target"]["curve"]["points"]]


def test_the_real_book_63_booked_is_962():
    assert _book_63_booked() == D("962.00")


async def test_core_paper_target_pnl_is_open_legs_plus_booked_with_the_line(provider):
    booked = _book_63_booked()
    off = await _post(provider, booked, paper_strategy_id=63, include_booked=False)
    on = await _post(provider, booked, paper_strategy_id=63)  # include_booked defaults to true
    assert _pnl(on) == _pnl(off) + booked  # open + booked = shown
    assert [c - o for c, o in zip(_curve(on), _curve(off), strict=True)] == [booked] * len(_curve(on))  # every point
    assert D(on["target"]["badge"]["amount"]) == _pnl(off) + booked  # the badge is the same whole figure
    t = on["target"]
    assert t["booked_display"] == "+962.00" and t["includes_booked_text"] == LINE
    assert t["includes_booked_text"] == render_explanation("target_includes_booked", amount=booked)


async def test_switch_off_is_exactly_the_open_legs_figures_and_has_no_line(provider):
    plan = await _post(provider, None)  # no paper strategy at all: today's reply
    off = await _post(provider, D("962.00"), paper_strategy_id=63, include_booked=False)
    assert off["target"] == plan["target"] and off["curves"] == plan["curves"]
    assert "includes_booked_text" not in off["target"] or off["target"]["includes_booked_text"] is None


async def test_a_plan_with_the_switch_on_is_unchanged(provider):
    plan = await _post(provider, D("962.00"))  # no paper_strategy_id: a plan never placed
    plain = await _post(provider, None, include_booked=False)
    assert plan["target"] == plain["target"]
    assert plan["target"].get("includes_booked_text") is None


async def test_booked_zero_shows_no_line_and_changes_nothing(provider):
    zero = await _post(provider, D("0.00"), paper_strategy_id=63)
    off = await _post(provider, D("0.00"), paper_strategy_id=63, include_booked=False)
    assert zero["target"] == off["target"]
    assert zero["target"].get("includes_booked_text") is None and zero["target"].get("booked_display") is None


async def test_max_profit_loss_and_scenario_figures_do_not_move_with_the_switch(provider):
    on = await _post(provider, D("962.00"), paper_strategy_id=63)
    off = await _post(provider, D("962.00"), paper_strategy_id=63, include_booked=False)
    for key in ("summary", "scenario", "payoff", "curves", "table"):
        assert on[key] == off[key], key


async def test_unreadable_book_gives_open_legs_only_with_the_reason(provider):
    off = await _post(provider, None, paper_strategy_id=63, include_booked=False)
    bad = await _post(provider, None, paper_strategy_id=63)  # the reader answers None: could not read
    assert _pnl(bad) == _pnl(off) and _curve(bad) == _curve(off)
    assert bad["target"].get("includes_booked_text") is None
    assert bad["target"]["booked_unreadable_text"] == render_explanation("target_booked_unreadable")


async def _bracket(provider, booked: Decimal, level: str, shift: Decimal) -> tuple[Decimal, Decimal]:
    """The open legs' P&L (switch off, so the route's plain figure) at the whole points just below and above
    ``level``."""
    low = int(D(level).to_integral_value(rounding="ROUND_FLOOR"))
    pnls = []
    for lv in (low, low + 1):
        probe = await _post(provider, booked, paper_strategy_id=63, include_booked=False, target_level=str(lv))
        pnls.append(_pnl(probe) + shift)
    return pnls[0], pnls[1]


async def test_fix1_target_breakevens_count_booked_so_open_legs_pnl_equals_minus_booked(provider):
    """ADR-209: switch ON: target breakevens are the levels where open legs P&L = -booked (real book 63). Each level
    lies between two whole points whose open-legs P&L + booked change sign; switch OFF keeps the plain zero
    crossings."""
    booked = _book_63_booked()
    off = await _post(provider, booked, paper_strategy_id=63, include_booked=False)
    on = await _post(provider, booked, paper_strategy_id=63)
    assert on["target"]["breakevens"] and off["target"]["breakevens"]
    assert on["target"]["breakevens"] != off["target"]["breakevens"]  # booked 962 moves them
    for level in on["target"]["breakevens"]:
        lo, hi = await _bracket(provider, booked, level, booked)
        assert lo * hi <= 0, (level, lo, hi)
    for level in off["target"]["breakevens"]:
        lo, hi = await _bracket(provider, booked, level, D(0))
        assert lo * hi <= 0, (level, lo, hi)
