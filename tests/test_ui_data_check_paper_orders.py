# ruff: noqa: PLR2004, PLR0913 - the hand figures are the point of the asserts
"""GC-TP step 1b (REQ-109 AC-4, AC-5; ADR-207): the checker's --paper-orders mode recomputes a paper strategy's net
position per contract from the ORDERBOOK rows alone, with its own arithmetic.

The roll (hand figures): contract 1: open SELL 65 @ 100.00, exit BUY 65 @ 80.00 -> flat, booked (100 - 80) x 65 =
+1,300.00. Contract 2: open SELL 65 @ 60.00 (another strike), live 50.00 -> short 65, average 60.00, unbooked
(60 - 50) x 65 = +650.00. Strategy: booked 1,300.00, unbooked 650.00, total 1,950.00.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
# UI_DATA_CHECK_PATH points the suite at a scratch mutant copy (mutation run); unset = the real file
CHECKER = Path(os.environ.get("UI_DATA_CHECK_PATH") or ROOT / "scripts" / "checks" / "ui_data_check.py")
_spec = importlib.util.spec_from_file_location("ui_data_check_paper", CHECKER)
u = importlib.util.module_from_spec(_spec)
sys.modules["ui_data_check_paper"] = u
_spec.loader.exec_module(u)


MINUS = chr(0x2212)  # the server's minus on money text


def _order(oid, cid, side, qty, price, kind="open"):
    return {"id": oid, "contract_id": cid, "side": side, "quantity": qty, "price": price, "kind": kind}


def _pos(cid, net, average, booked, booked_text, ltp=None, unbooked=None, unbooked_text=None, total=None,
         total_text=None):
    return {"contract_id": cid, "net_quantity": net, "average": average, "booked": booked, "booked_text": booked_text,
            "ltp": ltp, "price_state": None if net == 0 else ("live" if ltp else "stale"), "unbooked": unbooked,
            "unbooked_text": unbooked_text, "total": total, "total_text": total_text}


def roll_reply() -> dict:
    return {
        "strategy_id": 7, "state": "LIVE",
        "orders": [_order(1, 1, "SELL", 65, "100.00"), _order(2, 1, "BUY", 65, "80.00", "exit"),
                   _order(3, 2, "SELL", 65, "60.00")],
        "positions": [
            _pos(1, 0, None, "1300.00", "+1,300.00", unbooked="0.00", unbooked_text="0.00", total="1300.00",
                 total_text="+1,300.00"),
            _pos(2, -65, "60.00", "0.00", "0.00", ltp="50.00", unbooked="650.00", unbooked_text="+650.00",
                 total="650.00", total_text="+650.00")],
        "booked": "1300.00", "unbooked": "650.00", "total": "1950.00",
        "booked_text": "+1,300.00", "unbooked_text": "+650.00", "total_text": "+1,950.00"}


def verdicts(reply) -> dict:
    return {f.name: f.verdict for f in u.check_paper_orders(reply).figures}


def test_the_roll_matches_the_hand_figures_and_every_figure_is_checked():
    rep = u.check_paper_orders(roll_reply())
    counts = rep.counts()
    assert counts[u.MISMATCH] == 0 and counts[u.NOT_CHECKABLE] == 0 and counts[u.MATCH] >= 20
    by_name = {f.name: f for f in rep.figures}
    # the recomputed side is the hand figure
    assert by_name["contract 1 booked"].independent == "1300.00"
    assert by_name["contract 2 unbooked"].independent == "650.00"
    assert by_name["contract 2 average (to the paisa)"].independent == "60.00"
    assert (by_name["strategy booked"].independent, by_name["strategy unbooked"].independent,
            by_name["strategy total"].independent) == ("1300.00", "650.00", "1950.00")


@pytest.mark.parametrize(("edit", "figure"), [
    (lambda r: r["positions"][0].update(booked="-1300.00"), "contract 1 booked"),  # a long's sign on a short roll
    (lambda r: r["positions"][1].update(unbooked="-650.00"), "contract 2 unbooked"),  # the short's sign flipped
    (lambda r: r["positions"][1].update(net_quantity=65), "contract 2 net quantity"),
    (lambda r: r["positions"][1].update(average="60.05"), "contract 2 average (to the paisa)"),
    (lambda r: r.update(total="1950.01"), "strategy total"),
    (lambda r: r.update(total_text="+1,950.01"), "strategy total text"),
    (lambda r: r["positions"][0].update(booked_text=MINUS + "1,300.00"), "contract 1 booked text"),
])
def test_one_altered_figure_is_a_mismatch_and_only_that_one(edit, figure):
    reply = roll_reply()
    edit(reply)
    assert verdicts(reply)[figure] == u.MISMATCH


def test_a_booked_short_is_positive_when_the_exit_is_below_the_average():
    """The sign of a short's booked: (average - exit) x qty. A checker that books (exit - average) shows -1,300.00."""
    by_name = {f.name: f for f in u.check_paper_orders(roll_reply()).figures}
    assert by_name["contract 1 booked"].independent == "1300.00"
    assert by_name["strategy booked text"].independent == "+1,300.00"


def test_a_contract_without_a_live_price_has_no_unbooked_or_total_and_showing_one_is_a_mismatch():
    reply = roll_reply()
    reply["positions"][1].update(ltp=None, price_state="stale", unbooked=None, unbooked_text=None, total=None,
                                 total_text=None)
    reply.update(state="PAUSED", unbooked=None, total=None, unbooked_text=None, total_text=None)
    v = verdicts(reply)
    assert v["contract 2 unbooked absent without a live price"] == u.MATCH
    assert v["strategy total absent when a contract is not live"] == u.MATCH
    assert not [n for n, verdict in v.items() if verdict == u.MISMATCH]
    reply["total"] = "1300.00"  # a total invented while a contract has no price
    assert verdicts(reply)["strategy total absent when a contract is not live"] == u.MISMATCH


def test_an_average_that_does_not_divide_out_is_compared_to_the_paisa_and_unbooked_stays_exact():
    reply = {"strategy_id": 8, "state": "LIVE",
             "orders": [_order(1, 5, "BUY", 1, "100.00"), _order(2, 5, "BUY", 1, "100.00"),
                        _order(3, 5, "BUY", 1, "100.05")],
             "positions": [_pos(5, 3, "100.02", "0.00", "0.00", ltp="101.00", unbooked="2.95", unbooked_text="+2.95",
                                total="2.95", total_text="+2.95")],
             "booked": "0.00", "unbooked": "2.95", "total": "2.95", "booked_text": "0.00", "unbooked_text": "+2.95",
             "total_text": "+2.95"}
    rep = u.check_paper_orders(reply)  # 300.05 / 3 = 100.0166..; unbooked = 303.00 - 300.05
    assert rep.counts()[u.MISMATCH] == 0 and rep.counts()[u.NOT_CHECKABLE] == 0


def test_an_order_through_zero_books_the_closing_part_and_opens_the_rest():
    reply = {"strategy_id": 9, "state": "LIVE",
             "orders": [_order(1, 3, "BUY", 65, "10.00"), _order(2, 3, "SELL", 100, "12.00", "exit")],
             "positions": [_pos(3, -35, "12.00", "130.00", "+130.00", ltp="11.00", unbooked="35.00",
                                unbooked_text="+35.00", total="165.00", total_text="+165.00")],
             "booked": "130.00", "unbooked": "35.00", "total": "165.00", "booked_text": "+130.00",
             "unbooked_text": "+35.00", "total_text": "+165.00"}
    rep = u.check_paper_orders(reply)  # booked (12 - 10) x 65; short 35 @ 12, live 11 -> (12 - 11) x 35
    assert rep.counts()[u.MISMATCH] == 0 and rep.counts()[u.NOT_CHECKABLE] == 0


def test_a_missing_book_or_a_refusal_is_not_checkable_never_a_match():
    for reply in ({}, {"state": "REFUSED", "reason": "HTTP 404"}, {"strategy_id": 1, "orders": []}):
        rep = u.check_paper_orders(reply)
        assert rep.counts() == {u.MATCH: 0, u.MISMATCH: 0, u.NOT_CHECKABLE: 1}


def test_the_cli_mode_reads_a_replay_prints_the_table_and_its_exit_code_follows_the_verdict(tmp_path, capsys):
    replay, out = tmp_path / "replay", tmp_path / "out"
    replay.mkdir()
    (replay / "paper_7.json").write_text(json.dumps(roll_reply()), encoding="utf-8")
    assert u.main(["--paper-orders", "7", "--replay", str(replay), "--out", str(out)]) == 0
    text = capsys.readouterr().out
    assert "| figure | reply | recomputed | verdict |" in text
    assert "| strategy total | 1950.00 | 1950.00 | match |" in text
    assert (out / "paper-orders-7.md").exists()
    bad = copy.deepcopy(roll_reply())
    bad["total"] = "1950.01"
    (replay / "paper_7.json").write_text(json.dumps(bad), encoding="utf-8")
    assert u.main(["--paper-orders", "7", "--replay", str(replay), "--out", str(out)]) == 1
    assert "| strategy total | 1950.01 | 1950.00 | mismatch |" in capsys.readouterr().out
