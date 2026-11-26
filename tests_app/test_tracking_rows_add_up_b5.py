"""B5 guard (ADR-328 (3), ADR-008, REQ-109 AC-4): the tracking reply's per-leg rows are the book's NETTED positions, one
row per contract, each row the engine's own TOTAL (booked + unbooked) for that contract, so the rows add up to the book
total, whatever the order history of a contract. Real PostgreSQL on the recorded replay; every test rolls back.

Shapes: a plain iron condor; a contract closed and then re-opened; a contract bought and then sold (the book holds one
flat position, not two rows). A row keyed any other way than by the book's contract total (e.g. the open part only,
or one row per stored order) breaks the sum in the second and third case."""
from __future__ import annotations

from decimal import Decimal
from http import HTTPStatus

import pytest
from test_strategy_store import _client
from test_strategy_tracking import ENTRY_PRICES, _open_book, _paper_body, _setup, db  # noqa: F401

D = Decimal
LEGS = 4
SKEWED = ["40.15", "11.95", "82.75", "35.80"]  # entries off the recorded LTPs, so an exit books a real result


async def _exit(c, stored, index, side=None):
    leg = stored.saved.definition.legs[index]
    side = side or ("BUY" if leg.action.value == "SELL" else "SELL")
    done = await c.post(f"/paper/strategies/{stored.id}/orders", json={"orders": [
        {"contract_id": stored.saved.contract_ids[index], "kind": "exit", "price": "1.00", "quantity": leg.quantity,
         "side": side}]})
    assert done.status_code == HTTPStatus.CREATED, done.text


async def _reopen(c, stored, index):
    leg = stored.saved.definition.legs[index]
    done = await c.post(f"/paper/strategies/{stored.id}/orders", json={"orders": [
        {"contract_id": stored.saved.contract_ids[index], "kind": "open", "price": SKEWED[index],
         "quantity": leg.quantity, "side": leg.action.value}]})
    assert done.status_code == HTTPStatus.CREATED, done.text


def _assert_rows_add_up(reply: dict, rows: int) -> None:
    legs = reply["legs"]
    assert len(legs) == rows, [(x["contract_id"], x["pnl"]) for x in legs]
    assert len({x["contract_id"] for x in legs}) == rows  # one row per contract, never two of one contract
    assert reply["state"] == "LIVE", reply["state"]
    assert all(x["pnl"] is not None for x in legs)
    assert sum((D(x["pnl"]) for x in legs), D(0)) == D(reply["paper_pnl"]), (
        [x["pnl"] for x in legs], reply["paper_pnl"])
    assert D(reply["booked"]) + D(reply["unbooked"]) == D(reply["paper_pnl"])


async def test_a_plain_iron_condor_rows_add_up_to_the_book_total(db):  # noqa: F811
    app, stored, *_ = await _setup(db)
    async with _client(app) as c:
        reply = await _open_book(c, stored, SKEWED)
        assert reply.status_code == HTTPStatus.OK, reply.text
        _assert_rows_add_up(reply.json(), LEGS)


async def test_a_closed_and_reopened_contract_is_one_row_with_its_booked_part(db):  # noqa: F811
    app, stored, *_ = await _setup(db)
    async with _client(app) as c:
        await _open_book(c, stored, SKEWED)
        await _exit(c, stored, 0)
        await _reopen(c, stored, 0)
        reply = await c.get(f"/strategies/{stored.id}/tracking")
        body = reply.json()
        _assert_rows_add_up(body, LEGS)
        assert D(body["booked"]) == D("65.00")  # the closed lifecycle's result is in the book and in the one row


async def test_a_buy_and_a_sell_of_one_contract_is_one_netted_row(db):  # noqa: F811
    app, stored, *_ = await _setup(db)
    async with _client(app) as c:
        await _open_book(c, stored, SKEWED)
        await _exit(c, stored, 1)  # leg 1 is a BUY: the SELL closes it, the book holds one flat position
        body = (await c.get(f"/strategies/{stored.id}/tracking")).json()
        _assert_rows_add_up(body, LEGS)
        same = [x for x in body["legs"] if x["contract_id"] == stored.saved.contract_ids[1]]
        assert len(same) == 1
        assert same[0]["exit_price"] is not None
        assert D(same[0]["pnl"]) == D(body["booked"])  # the only closed contract: its row is the book's booked


async def _compare_with_legs_table(c, stored):
    track = (await c.get(f"/strategies/{stored.id}/tracking")).json()
    book = (await c.get(f"/paper/strategies/{stored.id}")).json()
    by_contract = {p["contract_id"]: p for p in book["positions"]}
    return track, by_contract


async def test_untouched_contracts_show_the_legs_table_figure_in_the_tracking_row(db):  # noqa: F811
    """The legs table (GET /paper/strategies/{id}) and the tracking rows say the same total for an open contract."""
    app, stored, *_ = await _setup(db)
    async with _client(app) as c:
        await _open_book(c, stored, SKEWED)
        await _exit(c, stored, 1)
        track, by_contract = await _compare_with_legs_table(c, stored)
        compared = 0
        for row in track["legs"]:
            if row["contract_id"] in by_contract:  # every contract of the book
                assert row["pnl_text"] == by_contract[row["contract_id"]]["total_text"], row["contract_id"]
                compared += 1
        assert compared == LEGS


@pytest.mark.xfail(strict=True, reason=(
    "OWNER FORK (B5): for a contract closed and re-opened the legs table row is the last lifecycle only "
    "(+65.00; the earlier lifecycle is its own closed row, D-10) while the tracking row, and so the panel's "
    "book-sum, is the contract's netted total (+130.00). Both cannot hold with one row per contract."))
async def test_reopened_contract_row_equals_the_legs_table_row(db):  # noqa: F811
    app, stored, *_ = await _setup(db)
    async with _client(app) as c:
        await _open_book(c, stored, SKEWED)
        await _exit(c, stored, 0)
        await _reopen(c, stored, 0)
        track, by_contract = await _compare_with_legs_table(c, stored)
        row = next(x for x in track["legs"] if x["contract_id"] == stored.saved.contract_ids[0])
        assert row["pnl_text"] == by_contract[row["contract_id"]]["total_text"]
