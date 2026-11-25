"""Phase 3 / B6 (modular doors; D-41 server half): the strategy's money figures are ASSEMBLED once.

Before: ``routes/paper.py _figures`` / ``_extremes`` / ``_after`` and ``routes/tracking.py _book_figures`` each turned the
open contracts' price answers into a live-price map and called the one engine (net_positions / lifecycles) themselves, so
the book page and the tracking page could not be shown to agree except by luck (D-41, two readers). After:
``ofo_app.strategy_money.strategy_money_view`` is the one assembly; the engine maths stays in ``ofo.tracking.orderbook``
(ADR-008: one engine owns every P&L number), and each route keeps its own reply shape. No database.

Rows: all live; one open contract unpriced (paused: no unbooked, no total; the priced one keeps its own figure, ADR-311);
no price at all; a closed book; the tracking route's "totals paused" basis; and the two routes' figures agree at one price set.
"""
from __future__ import annotations

import datetime
import inspect
from decimal import Decimal
from types import SimpleNamespace

import pytest
from ofo.engine.legs import Action, Instrument
from ofo.tracking import book, paper
from ofo.tracking.orderbook import PaperOrder, lifecycles, net_positions
from ofo_app import strategy_money
from ofo_app.routes import paper as P
from ofo_app.routes import tracking as T

D = Decimal
AT = datetime.datetime(2026, 11, 25, 4, 0, tzinfo=datetime.UTC)


def _orders(*rows):
    return [PaperOrder(str(cid), side, 65, D(price), kind, AT) for cid, side, price, kind in rows]


BOOK = _orders((1, "SELL", "100", "open"), (2, "BUY", "50", "open"))
LIVE = {1: paper.Price("NSE_FO:1", paper.LIVE, D("90.00"), AT), 2: paper.Price("NSE_FO:2", paper.LIVE, D("60.00"), AT)}
HALF = {1: paper.Price("NSE_FO:1", paper.LIVE, D("90.00"), AT), 2: paper.Price("NSE_FO:2", "missing", None, None)}
NONE = {1: paper.Price("NSE_FO:1", "missing", None, None), 2: paper.Price("NSE_FO:2", "stale", None, AT)}


def test_core_live_prices_give_the_engines_own_figures():
    view = strategy_money_view(BOOK, LIVE)
    gold = net_positions(BOOK, {"1": D("90.00"), "2": D("60.00")})
    assert (view.book.booked, view.book.unbooked, view.book.total) == (gold.booked, gold.unbooked, gold.total)
    assert view.paused is False
    assert view.priced == view.live == {"1": D("90.00"), "2": D("60.00")}
    assert view.lifecycle().total == gold.total  # the list's lifecycle split gives the same totals (D-10)


def test_one_unpriced_contract_pauses_the_totals_but_the_priced_one_keeps_its_figure():
    view = strategy_money_view(BOOK, HALF)
    assert view.paused is True
    assert (view.book.unbooked, view.book.total) == (None, None)
    assert view.priced == {"1": D("90.00")}
    assert view.by_contract["1"].unbooked == D("650.00")  # ADR-311: its own figure (SELL 100, now 90, 65 units)
    assert view.by_contract["2"].unbooked is None


def test_no_price_at_all_is_paused_with_the_booked_figure_known():
    view = strategy_money_view(BOOK, NONE)
    assert view.paused is True and view.priced == {}
    assert view.book.booked == D("0") and view.book.total is None


def test_a_closed_book_is_not_paused_and_has_no_price_to_read():
    closed = _orders((1, "SELL", "100", "open"), (1, "BUY", "80", "exit"))
    view = strategy_money_view(closed, {})
    assert view.paused is False
    assert view.book.booked == D("1300.00") and view.book.total == D("1300.00")


def test_the_tracking_routes_paused_or_unconnected_basis_empties_the_totals_only():
    view = strategy_money_view(BOOK, LIVE, totals_priced=False)
    assert view.live == {} and (view.book.unbooked, view.book.total) == (None, None)
    assert view.priced == {"1": D("90.00"), "2": D("60.00")}  # per contract the legs still show their own price
    assert view.by_contract["1"].unbooked == D("650.00")


@pytest.mark.parametrize("prices", [LIVE, HALF, NONE], ids=["live", "half", "none"])
def test_core_the_paper_page_and_the_tracking_page_show_the_same_money_at_one_price_set(prices):
    """D-41 server half: ``routes/paper.py _figures`` and ``routes/tracking.py _book_figures`` at the same prices."""
    found = {c: SimpleNamespace(contract_id=c, state="live", feed_key=f"NSE_FO:{c}", identity=f"c{c}",
                                stored=SimpleNamespace(listed=SimpleNamespace(contract=SimpleNamespace(
                                    name="NIFTY", instrument_type="CE", strike=D("23000"),
                                    expiry=datetime.date(2026, 12, 2), lot_size=65)))) for c in (1, 2)}
    stored = [SimpleNamespace(order=SimpleNamespace(contract_id=int(o.instrument_id), as_paper=lambda o=o: o, kind=o.kind,
                                                    reason=None, placed_at=o.placed_at)) for o in BOOK]
    page = P._figures(stored, found, prices, True, datetime.date(2026, 11, 25))
    legs = tuple(SimpleNamespace(instrument_id=str(c), exited=False) for c in (1, 2))
    bk = SimpleNamespace(strategy_id=170, orders=tuple(BOOK), legs=legs)
    view = SimpleNamespace(paused=any(not paper.is_live(p) for p in prices.values()), legs=[prices[1], prices[2]])
    figures, per_leg, _ = T._book_figures(bk, view)
    assert (page["booked"], page["unbooked"], page["total"]) == tuple(
        None if v is None else P._exact(v) for v in (figures.booked, figures.unbooked, figures.total))
    assert per_leg == [p.unbooked for p in net_positions(BOOK, {k: p.price for k, p in
                                                                ((str(c), prices[c]) for c in prices) if paper.is_live(p)}).positions]


@pytest.mark.parametrize("fn", [P._figures, P._extremes, P._after, T._book_figures])
def test_core_the_routes_assemble_through_the_door_and_call_no_engine_function_themselves(fn):
    """C3 (a structural guarantee): the one assembly is the only path; the detector is the second layer."""
    source = inspect.getsource(fn)
    assert "strategy_money_view(" in source
    assert "net_positions(" not in source and "lifecycles(" not in source


def test_the_assembly_does_no_arithmetic_of_its_own():
    """ADR-008: the module only picks live prices and calls the engine."""
    import ast  # noqa: PLC0415
    tree = ast.parse(inspect.getsource(strategy_money))
    math = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)  # `int | str` annotations are BitOr
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.AugAssign) or (isinstance(n, ast.BinOp) and isinstance(n.op, math))]
    assert lifecycles is not None


# ---- the tracking reply's rows: contract id, and one figure per contract on both pages (D-41) -------------------------

KEYS = {5001: "NSE_FO:44601", 5002: "NSE_FO:44602"}  # the feed identity of the tracking reply's `instrument_id`
CBOOK = [PaperOrder(str(cid), side, 65, D(price), "open", AT) for cid, side, price in ((5001, "SELL", "100"), (5002, "BUY", "50"))]
CLIVE = {5001: paper.Price(KEYS[5001], paper.LIVE, D("90.00"), AT), 5002: paper.Price(KEYS[5002], paper.LIVE, D("60.00"), AT)}
CHALF = {5001: paper.Price(KEYS[5001], paper.LIVE, D("90.00"), AT), 5002: paper.Price(KEYS[5002], "missing", None, None)}
CNONE = {5001: paper.Price(KEYS[5001], "missing", None, None), 5002: paper.Price(KEYS[5002], "stale", None, AT)}


def _tracking_rows(prices, connected=True):
    legs = [paper.TrackedLeg(KEYS[c], Action(o.side), Instrument.CE, D("23000"), datetime.date(2026, 12, 2), 65, o.price, AT)
            for c, o in zip((5001, 5002), CBOOK, strict=True)]
    bk = T._Book(170, tuple(CBOOK), book.contract_legs(CBOOK))
    paused = any(not paper.is_live(p) for p in prices.values())
    view = paper.TrackingView(paused, "prices_not_live" if paused else None, None, AT if paused else None,
                              tuple(prices[c] for c in (5001, 5002)), None, None, ()) if connected else None
    return T._figures(bk, legs, view, [None, None], "NIFTY", None)["legs"]


def test_tracking_rows_carry_the_contract_id():
    """D-41: the join key of the screen. `instrument_id` stays the feed identity ("NSE_FO:..."); `contract_id` is the book's key."""
    rows = _tracking_rows(CLIVE)
    assert [r["contract_id"] for r in rows] == [5001, 5002]
    assert all(isinstance(r["contract_id"], int) for r in rows)
    assert [r["instrument_id"] for r in rows] == ["NSE_FO:44601", "NSE_FO:44602"]
    assert [r["contract_id"] for r in _tracking_rows(CLIVE, connected=False)] == [5001, 5002]  # not connected: still stated


@pytest.mark.parametrize("prices", [CLIVE, CHALF, CNONE], ids=["live", "one-unpriced", "none-priced"])
def test_book_page_and_tracking_rows_agree_per_contract_at_one_price_set(prices):
    """Each contract's own unbooked figure is the same on the book page's positions and on the tracking rows (None on both
    sides for an unpriced contract, ADR-311), whichever contracts have a price."""
    found = {c: SimpleNamespace(contract_id=c, state="live", feed_key=KEYS[c], identity=KEYS[c],
                                stored=SimpleNamespace(listed=SimpleNamespace(contract=SimpleNamespace(
                                    name="NIFTY", instrument_type="CE", strike=D("23000"),
                                    expiry=datetime.date(2026, 12, 2), lot_size=65)))) for c in (5001, 5002)}
    stored = [SimpleNamespace(order=SimpleNamespace(contract_id=int(o.instrument_id), as_paper=lambda o=o: o, kind=o.kind,
                                                    reason=None, placed_at=o.placed_at)) for o in CBOOK]
    page = {p["contract_id"]: p["unbooked"] for p in P._figures(stored, found, prices, True, datetime.date(2026, 11, 25))["positions"]}
    rows = {r["contract_id"]: r["pnl"] for r in _tracking_rows(prices)}
    assert page == rows
    assert sorted(page) == [5001, 5002]
    if prices is CLIVE:
        assert page == {5001: D("650.00"), 5002: D("650.00")}
    if prices is CHALF:
        assert page == {5001: D("650.00"), 5002: None}
    if prices is CNONE:
        assert page == {5001: None, 5002: None}


def test_history_route_uses_the_door_live_prices():
    """B6: the adjustment history picks its live prices through the one door, not a fifth copy of the comprehension."""
    from ofo_app.routes import adjustment_history as H  # noqa: PLC0415
    source = inspect.getsource(H)
    assert "live_prices(" in source
    assert "p.price for cid, p in prices.items() if paper_prices.is_live(p)" not in source


def test_by_contract_is_computed_at_most_once_per_view(monkeypatch):
    """The list route never asks for per-contract figures: `by_contract` (and `book`) are lazy and cached; with live totals the
    book is reused, so the engine is called once; with paused totals it is called once more for the per-contract basis."""
    calls = []
    real = strategy_money.net_positions

    def counting(orders, live):
        calls.append(dict(live))
        return real(orders, live)

    monkeypatch.setattr(strategy_money, "net_positions", counting)
    view = strategy_money_view(BOOK, LIVE)
    assert calls == []  # building the view runs no engine call
    first, second = view.by_contract, view.by_contract
    assert first is second and len(calls) == 1
    assert view.book is view.book and len(calls) == 1  # the same book is reused for the totals
    calls.clear()
    paused = strategy_money_view(BOOK, LIVE, totals_priced=False)
    assert (paused.by_contract is paused.by_contract) and (paused.book is paused.book)
    assert len(calls) == 2  # the totals' basis (empty) and the per-contract basis
    calls.clear()
    assert strategy_money_view(BOOK, LIVE).lifecycle().total is not None and len(calls) == 0


strategy_money_view = strategy_money.strategy_money_view
