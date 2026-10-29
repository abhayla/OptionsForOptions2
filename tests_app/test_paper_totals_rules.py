"""GC-TP step 4a rules without a database: the decay sign per contract, never a partial sum, newest first.

Spec basis: REQ-145 AC-2 / F-63 (Decay to the next market open), REQ-109 AC-5 (absent with the reason, never a partial
sum), ADR-008 (the server sums; exact Decimal). The market is the recorded replay (tests/marketdata/_kite_fixture).
"""
from __future__ import annotations

import datetime
import pathlib
import sys
from decimal import Decimal

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from marketdata._kite_fixture import all_instrument_ids, new_provider, replay  # noqa: E402
from ofo.outcome import read_snapshot  # noqa: E402
from ofo.tracking import paper, paper_decay  # noqa: E402
from ofo_app import paper_store  # noqa: E402
from ofo_app.routes.paper import _charges_total, _newest_first, _totals  # noqa: E402

D = Decimal
IDS = ["NSE_FO:44624", "NSE_FO:44632", "NSE_FO:44604", "NSE_FO:44595"]  # 22800 CE, 23000 CE, 22400 PE, 22200 PE


def _snapshot():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    provider.drain_subscription_changes()
    last = replay(provider, clock)
    return read_snapshot(provider, "NIFTY", IDS, last, D("0.065"), None)


def _open(snap, key: str, qty: int) -> paper_decay.OpenContract:
    c = snap.legs[key].contract.contract
    return paper_decay.OpenContract(key, paper_decay.Instrument(c.instrument_type), c.strike, c.expiry, qty,
                                    paper.leg_price(snap, key).price)


def test_a_bought_contract_decays_negative_a_sold_one_positive_and_the_book_is_the_signed_sum():
    snap = _snapshot()
    long_ = paper_decay.book_decay(snap, "NIFTY", [_open(snap, IDS[0], 65)])
    short = paper_decay.book_decay(snap, "NIFTY", [_open(snap, IDS[1], -65)])
    both = paper_decay.book_decay(snap, "NIFTY", [_open(snap, IDS[0], 65), _open(snap, IDS[1], -65)])
    assert long_.value < 0 < short.value, (long_, short)
    assert both == paper_decay.Decay(long_.value + short.value, None)
    flipped = paper_decay.book_decay(snap, "NIFTY", [_open(snap, IDS[1], 65)])
    assert flipped.value == -short.value  # the same contract held the other way decays the opposite amount


def test_an_option_without_a_solvable_iv_has_no_decay_and_no_open_contract_decays_zero():
    snap = _snapshot()
    held = _open(snap, IDS[0], 65)
    # the IV is solved from the snapshot's quote (the DB test drives a quote above the index); here a contract the
    # snapshot holds no quote for
    missing = paper_decay.OpenContract("NSE_FO:1", held.instrument, held.strike, held.expiry, 65, D("10"))
    assert paper_decay.book_decay(snap, "NIFTY", [missing]) == paper_decay.Decay(None, "no_iv")
    assert paper_decay.book_decay(snap, "NIFTY", []) == paper_decay.Decay(D(0), None)


def _strategy(booked: str, unbooked: str | None, reason: str | None = None) -> dict:
    return {"booked": D(booked), "unbooked": None if unbooked is None else D(unbooked), "pause_reason": reason,
            "charges": D("1.00"), "charges_reason": None}  # every route strategy carries its Charges (step 8a)


def test_one_strategy_without_unbooked_makes_the_totals_absent_never_a_partial_sum():
    live = paper_decay.Decay(D("-10.005"), None)
    got = _totals([_strategy("100.00", "50.00"), _strategy("-20.50", None, "contract_retired")],
                  [live, paper_decay.Decay(None, "contract_retired")])
    assert (got["booked"], got["unbooked"], got["total"], got["totals_reason"]) == (
        D("79.50"), None, None, "contract_retired")
    assert (got["decay"], got["decay_reason"]) == (None, "contract_retired")
    whole = _totals([_strategy("100.00", "50.00"), _strategy("-20.50", "0.25")], [live, live])
    assert (whole["unbooked"], whole["total"], whole["decay"]) == (D("50.25"), D("129.75"), D("-20.01"))


def _book(strategy_id: int, *hours: int) -> paper_store.UserBook:
    at = datetime.datetime(2026, 10, 29, 4, 0, tzinfo=datetime.UTC)
    orders = tuple(paper_store.StoredOrder(i, strategy_id, paper_store.NewOrder(
        1, "BUY", 65, D("10.00"), "open", at + datetime.timedelta(hours=h)), at) for i, h in enumerate(hours))
    return paper_store.UserBook(strategy_id, "x", "NIFTY", orders)


def test_newest_first_is_the_latest_first_order_then_the_highest_id():
    books = [_book(1, 5), _book(2, 1, 9), _book(3, 1)]
    assert [b.strategy_id for b in sorted(books, key=_newest_first, reverse=True)] == [1, 3, 2]


def test_charges_total_is_absent_with_the_first_absent_reason_never_a_partial_sum():
    # GC-TP step 8a (REQ-109 AC-10 with AC-5's never-a-partial-sum rule)
    priced = {"charges": D("25.73"), "charges_reason": None}
    futures = {"charges": None, "charges_reason": "not_priced"}
    assert _charges_total([priced, priced])["charges"] == D("51.46")
    got = _charges_total([priced, futures, {"charges": None, "charges_reason": "rates_unavailable"}])
    assert (got["charges"], got["charges_text"], got["charges_reason"]) == (None, None, "not_priced")
