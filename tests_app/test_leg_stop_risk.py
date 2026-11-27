"""ADR-330 (6), P6: GET /paper/strategies/{id}/leg-stop-risk?contract_id=&level=, replay market, real PostgreSQL, every
test rolled back. A one-leg exit basket is priced AT THE STOP LEVEL (a given price, never a live read) through the one
engine (exit_risk, ADR-008) and answered with the widening line; it informs only and never blocks a save.

The book is the app's iron condor (65 units a leg, both spreads 200 wide): SELL 22800 CE 80, BUY 23000 CE 20,
SELL 22400 PE 130, BUY 22200 PE 34. Net credit 156 a unit = 10,140.00; Max Loss before = 13,000.00 - 10,140.00 =
2,860.00 (the 25 Nov "now" figure). A stop on the short call at 140.70 buys it back for 9,145.50, leaving the long call
and the put spread: Max Loss after = 2,860.00 + 9,145.50 = 12,005.50. The 25 Nov cent (12,005.51) is not reachable with
orders at 0.05 steps in any quantity (every booked amount is a multiple of 0.05). The real stop fills at the live
price, which can carry paisa; this line is an estimate at the stop level. The engine figure for this book is 12,005.50
and the test pins that, not a bent number."""
from __future__ import annotations

import datetime
from decimal import Decimal
from http import HTTPStatus

import pytest
from ofo.engine.extremes import ExitRisk
from ofo_app import paper_store
from ofo_app.routes import paper as paper_routes
from sqlalchemy import text
from test_strategy_store import _client
from test_strategy_tracking import _setup

D = Decimal
AT = datetime.datetime(2026, 11, 25, 5, 0, tzinfo=datetime.UTC)
PRICES = ("80", "20", "130", "34")  # SELL 22800 CE, BUY 23000 CE, SELL 22400 PE, BUY 22200 PE
SIDES = ("SELL", "BUY", "SELL", "BUY")
SHORT_CALL, LONG_CALL, SHORT_PUT, LONG_PUT = range(4)
LEGS = len(SIDES)


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def _book(db, **kw):
    app, stored, *_ = await _setup(db, **kw)
    ids = stored.saved.contract_ids
    await paper_store.place(db, stored.user_ref, stored.id, [
        paper_store.NewOrder(ids[i], SIDES[i], 65, D(PRICES[i]), "open", AT) for i in range(4)])
    return app, stored, ids


async def _ask(app, strategy_id, contract_id, level):
    async with _client(app) as c:
        return await c.get(f"/paper/strategies/{strategy_id}/leg-stop-risk",
                           params={"contract_id": contract_id, "level": level})


async def _orders(db, strategy_id) -> int:
    return (await db.execute(text("SELECT count(*) FROM public.paper_orders WHERE strategy_id = :i"),
                             {"i": strategy_id})).scalar_one()


async def test_25_nov_short_call_stop(db):
    app, stored, ids = await _book(db)
    reply = await _ask(app, stored.id, ids[SHORT_CALL], "140.70")
    assert reply.status_code == HTTPStatus.OK, reply.text
    body = reply.json()
    assert body["state"] == "yes"
    assert body["warning_text"] == "If this stop fires, max loss becomes Rs 12,005.50 (now Rs 2,860.00)."
    assert (body["max_loss_before"], body["max_loss_after"]) == ("-2860.00", "-12005.50")
    assert await _orders(db, stored.id) == LEGS  # read only


async def test_a_small_change_still_shows_the_line_whatever_its_size(db):
    """ADR-330 (6) states no threshold (ADR-256's "more than double" is the exit confirmation's): 2,860 -> 3,510."""
    app, stored, ids = await _book(db)
    body = (await _ask(app, stored.id, ids[SHORT_PUT], "10.00")).json()
    assert body["state"] == "yes"
    assert body["warning_text"] == "If this stop fires, max loss becomes Rs 3,510.00 (now Rs 2,860.00)."
    assert (body["max_loss_before"], body["max_loss_after"]) == ("-2860.00", "-3510.00")


async def _locked_profit_book(db):
    """Put side closed (short put bought back at 1, long put sold at 100): cash 16,575.00, calls open, so max loss is
    16,575.00 - 13,000.00 = +3,575.00, a profit, never a loss (M2)."""
    app, stored, ids = await _book(db)
    await paper_store.place(db, stored.user_ref, stored.id, [
        paper_store.NewOrder(ids[SHORT_PUT], "BUY", 65, D("1"), "exit", AT),
        paper_store.NewOrder(ids[LONG_PUT], "SELL", 65, D("100"), "exit", AT)])
    return app, stored, ids


async def test_a_book_with_locked_in_profit_still_a_profit_after_the_stop(db):
    app, stored, ids = await _locked_profit_book(db)
    body = (await _ask(app, stored.id, ids[SHORT_CALL], "140.70")).json()
    assert body["state"] == "yes"
    assert body["warning_text"] == ("If this stop fires, the book shows a profit of at least Rs 7,429.50 "
                                    "(now at least Rs 3,575.00).")


async def test_a_book_with_locked_in_profit_turned_into_a_loss_by_the_stop(db):
    app, stored, ids = await _locked_profit_book(db)
    body = (await _ask(app, stored.id, ids[SHORT_CALL], "400.00")).json()  # buys back for 26,000.00: 16,575 - 26,000
    assert body["warning_text"] == ("If this stop fires, max loss becomes Rs 9,425.00 "
                                    "(now a profit: at least Rs 3,575.00).")


async def test_a_book_with_locked_in_profit_turned_unlimited_by_the_stop(db):
    app, stored, ids = await _locked_profit_book(db)
    body = (await _ask(app, stored.id, ids[LONG_CALL], "5.00")).json()
    assert body["warning_lines"][1:] == [
        "Max loss now: none (the book shows a profit of at least Rs 3,575.00).",
        "Max loss then: no upper limit (worst case: NIFTY keeps rising)."]


async def test_a_stop_on_a_long_wing_leaves_the_short_leg_bare_so_it_is_yes_with_no_fixed_maximum(db):
    """The plan expected "no" here; the engine says yes: selling the long call leaves the short call with no cover."""
    app, stored, ids = await _book(db)
    body = (await _ask(app, stored.id, ids[LONG_CALL], "5.00")).json()
    assert body["state"] == "yes" and body["max_loss_after"] == "unlimited"
    assert body["warning_lines"] == [
        "If this stop fires, the sold NIFTY 13 Oct 22800 CE is left without protection.",
        "Max loss now: Rs 2,860.00.",
        "Max loss then: no upper limit (worst case: NIFTY keeps rising)."]  # a sold call: no amount is made up
    assert "Rs" not in body["warning_lines"][2]


async def test_a_stop_that_cannot_be_priced_is_cannot_tell_with_no_figure(db, monkeypatch):
    monkeypatch.setattr(paper_routes, "exit_risk", lambda *a, **k: ExitRisk("cannot_tell", None, None, ()))
    app, stored, ids = await _book(db)
    body = (await _ask(app, stored.id, ids[SHORT_CALL], "140.70")).json()
    assert body["state"] == "cannot_tell"
    assert body["max_loss_before"] is None and body["warning_text"] is None


async def test_another_users_or_a_missing_strategy_answers_not_found(db):
    app, stored, ids = await _book(db)
    other, *_ = await _setup(db)
    assert (await _ask(other, stored.id, ids[SHORT_CALL], "140.70")).status_code == HTTPStatus.NOT_FOUND
    assert (await _ask(app, 999999999, ids[SHORT_CALL], "140.70")).status_code == HTTPStatus.NOT_FOUND


async def test_a_contract_that_is_not_open_is_refused_like_the_save(db):
    app, stored, ids = await _book(db)
    await paper_store.place(db, stored.user_ref, stored.id, [
        paper_store.NewOrder(ids[SHORT_CALL], "BUY", 65, D("80"), "exit", AT)])  # the short call is now closed
    for contract in (ids[SHORT_CALL], 999999999):
        reply = await _ask(app, stored.id, contract, "140.70")
        assert HTTPStatus.BAD_REQUEST <= reply.status_code < HTTPStatus.INTERNAL_SERVER_ERROR, reply.text
        assert "state" not in reply.json()
        assert reply.json()["code"] == "STRATEGY_VALIDATION_441", reply.text


async def test_a_level_that_is_not_a_multiple_of_five_paise_is_refused_like_the_save(db):
    app, stored, ids = await _book(db)
    for bad in ("140.72", "0", "-5"):
        reply = await _ask(app, stored.id, ids[SHORT_CALL], bad)
        assert HTTPStatus.BAD_REQUEST <= reply.status_code < HTTPStatus.INTERNAL_SERVER_ERROR, (bad, reply.text)
        assert "state" not in reply.json()
        assert reply.json()["code"] == "STRATEGY_VALIDATION_440", reply.text


async def test_m1_a_long_put_stop_keeps_the_engine_figure_and_names_the_bare_put_as_the_screens_do(db):
    """Lane M, 27 Nov (B-N1 #194: "... Sold option with less protection: NIFTY 25750 PE 2028-12-01"). A stop on the
    LONG put at 5.00 leaves the short 22400 PE bare: the worst case is the index at 0, -22400 x 65 + 10,465.00 =
    -14,45,535.00 (the figure is right and kept). The leg is named as every screen names it (REQ-151): "NIFTY 13 Oct
    22400 PE", never the ISO record form "NIFTY 22400 PE 2026-10-13" (failed before the fix with exactly that text)."""
    app, stored, ids = await _book(db)
    body = (await _ask(app, stored.id, ids[LONG_PUT], "5.00")).json()
    assert body["state"] == "yes"
    assert (body["max_loss_before"], body["max_loss_after"]) == ("-2860.00", "-1445535.00")
    assert body["warning_lines"] == [  # ADR-330 (55): three lines, each fact on its own line, built by the server
        "If this stop fires, the sold NIFTY 13 Oct 22400 PE is left without protection.",
        "Max loss now: Rs 2,860.00.",
        "Max loss then: Rs 14,45,535.00 (worst case: NIFTY at zero)."]
    assert body["warning_text"] == "\n".join(body["warning_lines"])


async def _twin_2028(db, contract_id: int) -> int:
    """A long-dated twin of ``contract_id``: the same name, strike and type, expiry 1 Dec 2028 (the PC's catalogue holds
    781 such rows on 27 Nov), with its own token and Zerodha row."""
    twin = (await db.execute(text(
        "INSERT INTO public.catalogue_contracts "
        "(exchange_token, name, expiry, strike, instrument_type, exchange_segment) "
        "SELECT exchange_token + 900000, name, DATE '2028-12-01', strike, instrument_type, exchange_segment "
        "FROM public.catalogue_contracts WHERE id = :i RETURNING id"), {"i": contract_id})).scalar_one()
    await db.execute(text(
        "INSERT INTO public.broker_instruments (contract_id, broker, broker_token, broker_symbol, broker_segment, "
        "lot_size, tick_size) SELECT :t, broker, broker_token || '9', broker_symbol || '-2028', broker_segment, "
        "lot_size, tick_size FROM public.broker_instruments WHERE contract_id = :i"), {"t": twin, "i": contract_id})
    return int(twin)


async def test_m3_a_2028_twin_of_the_bare_put_is_never_named_or_used(db):
    """Lane M item 3, 27 Nov (B-N1: "Sold option with less protection: NIFTY 25750 PE 2028-12-01" while the book's put,
    contract 9111, expires 1 Dec 2026). With a 2028 twin of the short 22400 PE in the catalogue, the line and the engine
    read the book's own contract by its id: the same figure as without the twin, and the twin is in no name or term."""
    app, stored, ids = await _book(db)
    twin = await _twin_2028(db, ids[SHORT_PUT])
    body = (await _ask(app, stored.id, ids[LONG_PUT], "5.00")).json()
    assert (body["max_loss_before"], body["max_loss_after"]) == ("-2860.00", "-1445535.00")  # one expiry: the figure
    assert body["warning_lines"][0] == "If this stop fires, the sold NIFTY 13 Oct 22400 PE is left without protection."
    booked = await paper_store.load(db, stored.id)
    names, terms = await paper_routes.names_and_terms(db, "NIFTY", booked)
    assert str(twin) not in names and str(twin) not in terms
    assert terms[str(ids[SHORT_PUT])].expiry == datetime.date(2026, 10, 13)


async def test_55_a_stop_that_leaves_nothing_bare_keeps_the_one_line(db):
    """No sold option loses its cover: the old single sentence, and no lines list (the page prints the sentence)."""
    app, stored, ids = await _book(db)
    body = (await _ask(app, stored.id, ids[SHORT_CALL], "140.70")).json()
    assert body["warning_lines"] is None
    assert body["warning_text"] == "If this stop fires, max loss becomes Rs 12,005.50 (now Rs 2,860.00)."


# --- ADR-330 (55): the builder itself, with the index name from the trade and every answer state -----------------

from ofo.engine.extremes import ContractTerms  # noqa: E402
from ofo.engine.legs import Instrument  # noqa: E402
from ofo.engine.metrics import UNLIMITED  # noqa: E402

_EXP = datetime.date(2026, 12, 3)
_TERMS = {"sp": ContractTerms(Instrument.PE, D("84000"), _EXP), "sc": ContractTerms(Instrument.CE, D("86000"), _EXP)}
_NAMES = {k: paper_routes.display_contract(("SENSEX", t.instrument, t.strike, t.expiry)) for k, t in _TERMS.items()}


def _lines(exposed, before, after, underlying="SENSEX", at_zero=None):
    risk = ExitRisk("yes", before, after, tuple(exposed))
    return paper_routes.leg_stop_lines(risk, _NAMES, _TERMS, underlying, at_zero if at_zero is not None else after)


def test_55_sensex_trade_says_sensex_never_nifty():
    lines = _lines(["sp"], D("-7800"), D("-1674725"), "SENSEX")  # at zero = the max loss: the label is true
    assert lines == ["If this stop fires, the sold SENSEX 3 Dec 84000 PE is left without protection.",
                     "Max loss now: Rs 7,800.00.",
                     "Max loss then: Rs 16,74,725.00 (worst case: SENSEX at zero)."]
    assert "NIFTY" not in " ".join(lines)


def test_55_a_bare_call_has_no_amount_and_says_so_in_words():
    lines = _lines(["sc"], D("-7800"), UNLIMITED)
    assert lines[2] == "Max loss then: no upper limit (worst case: SENSEX keeps rising)."


def test_55_both_bare_unlimited_wins_and_both_legs_are_named():
    lines = _lines(["sp", "sc"], D("-7800"), UNLIMITED)
    assert "SENSEX 3 Dec 84000 PE" in lines[0] and "SENSEX 3 Dec 86000 CE" in lines[0]
    assert lines[0].startswith("If this stop fires, these sold options are left with less protection: ")
    assert lines[2].startswith("Max loss then: no upper limit")


def test_55_a_profit_now_is_never_printed_as_a_loss():
    lines = _lines(["sp"], D("3575"), D("-1000"))
    assert lines[1] == "Max loss now: none (the book shows a profit of at least Rs 3,575.00)."
    assert lines[2] == "Max loss then: Rs 1,000.00 (worst case: SENSEX at zero)."


def test_55_figures_that_cannot_be_worked_out_print_no_number():
    lines = _lines(["sp"], None, None)
    assert lines[1:] == ["Max loss now: could not be worked out.", "Max loss then: could not be worked out."]
    assert not any(ch.isdigit() for ch in lines[1] + lines[2])


def test_55_nothing_exposed_has_no_three_lines():
    assert _lines([], D("-7800"), D("-9000")) is None


def test_55_review_f2_the_zero_label_is_printed_only_when_the_loss_is_the_loss_at_zero():
    """Opus review (27 Nov) F2: a bare put whose max loss comes from elsewhere (a call spread above) must not read
    "worst case: NIFTY at zero"; the amount stays, no case is named."""
    lines = _lines(["sp"], D("-7800"), D("-1765125"), "NIFTY", at_zero=D("-1540125"))
    assert lines[2] == "Max loss then: Rs 17,65,125.00."
    assert "worst case" not in lines[2]


# --- the review's book shapes, through the whole answer (the engine's own figures, no database) ------------------

from types import SimpleNamespace  # noqa: E402

from ofo.tracking.orderbook import PaperOrder  # noqa: E402

_IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
_T0 = datetime.datetime(2026, 11, 27, 10, 0, tzinfo=_IST)
_E1, _E2 = datetime.date(2026, 12, 1), datetime.date(2026, 12, 29)


def _answer(legs, stop_id, level):
    """legs: (id, instrument, strike, expiry, side, quantity, price); the stop closes ``stop_id`` at ``level``."""
    from ofo.strategy.definition import display_contract  # noqa: PLC0415
    from ofo.tracking.orderbook import net_positions  # noqa: PLC0415
    terms = {i: ContractTerms(ins, D(k), e) for i, ins, k, e, *_ in legs}
    names = {i: display_contract(("NIFTY", ins, D(k), e)) for i, ins, k, e, *_ in legs}
    booked = []
    for i, _ins, _k, _e, side, qty, price in legs:
        order = PaperOrder(i, side, qty, D(price), "open", _T0)
        booked.append(SimpleNamespace(order=SimpleNamespace(as_paper=lambda o=order: o)))
    held = {p.instrument_id: p.net_quantity for p in net_positions(paper_routes._paper(booked), {}).positions}
    return paper_routes.leg_stop_answer(booked, held[stop_id], int(stop_id), D(level), names, terms, _T0, "NIFTY")


def test_55_review_f1_a_ratio_call_spread_says_no_upper_limit_both_before_and_after():
    legs = [("1", Instrument.CE, "25000", _E1, "BUY", 75, "200"), ("2", Instrument.CE, "25500", _E1, "SELL", 150, "80")]
    got = _answer(legs, "1", "5.00")
    assert got.warning_lines[1:] == ["Max loss now: no upper limit.",
                                     "Max loss then: no upper limit (worst case: NIFTY keeps rising)."]


def test_55_review_f1_a_calendar_call_keeps_the_unlimited_figure_the_engine_has():
    legs = [("1", Instrument.CE, "25000", _E1, "SELL", 75, "100"), ("2", Instrument.CE, "25000", _E2, "BUY", 75, "200")]
    got = _answer(legs, "2", "5.00")
    assert got.warning_lines[1:] == ["Max loss now: could not be worked out.",  # two expiries: no figure before
                                     "Max loss then: no upper limit (worst case: NIFTY keeps rising)."]


def test_55_review_f2_a_book_whose_worst_case_is_a_call_spread_above_does_not_say_zero():
    legs = [("1", Instrument.PE, "22000", _E1, "SELL", 75, "20"), ("2", Instrument.PE, "21500", _E1, "BUY", 75, "10"),
            ("3", Instrument.CE, "25000", _E1, "SELL", 750, "150"), ("4", Instrument.CE, "27500", _E1, "BUY", 750, "5")]
    got = _answer(legs, "2", "5.00")
    assert got.warning_lines[2] == "Max loss then: Rs 17,65,125.00."
