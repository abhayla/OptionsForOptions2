"""FD4 (coordinator 10:55): the real close snapshot of the PC (17 rows: 15 option contracts + NIFTY 50 + SENSEX) holds
the TRADING SYMBOL in its ``name`` column, not the catalogue's name; the seed refused 15 of 17 on its name check.
The name check now also accepts the contract's OWN trading symbol (never another contract's, never a loosened
match), and a refusal says WHY in one plain line with the fix to try. No database."""
from __future__ import annotations

import json

from ofo_app import last_close_store as lcs
from test_last_close_seed_aliases import ALIASES, CLOSE_AT, KNOWN, entries, zerodha_ref
from test_last_close_seed_command import SeedStore


def _rows():
    out = []
    for e in entries()[:30]:  # a sample of the catalogue's contracts (options and futures by trading symbol)
        c = e.contract
        book = f"{c.exchange_segment}:{c.exchange_token}"
        symbol = zerodha_ref(book).broker_symbol
        out.append({"contract_id": book, "name": symbol, "last_price": "99.75", "time": CLOSE_AT,
                    "source": "feed-stream"})
    return out


def test_a_snapshot_with_the_trading_symbol_in_the_name_column_is_taken_as_it_is():
    rows = _rows()
    assert any(r["name"] != KNOWN[r["contract_id"]][0] for r in rows)  # the symbol is not the catalogue name
    store, out = SeedStore(), []
    res = lcs.run_seed(json.dumps(rows), store, KNOWN, aliases=ALIASES, out=out.append)
    assert res.skipped == [], res.skipped
    assert res.written == len(rows)


def test_a_name_that_is_another_contracts_symbol_or_unknown_is_still_refused():
    a, b = _rows()[:2]
    wrong = {**a, "name": b["name"]}  # contract a, but named with contract b's trading symbol
    nonsense = {**b, "name": "NOT-A-CONTRACT"}
    rows_ = [wrong, nonsense]
    res = lcs.run_seed(json.dumps(rows_), SeedStore(), KNOWN, aliases=ALIASES)
    assert res.written == 0 and len(res.skipped) == len(rows_)
    assert all(reason.startswith("name does not match the catalogue") for _n, _i, reason in res.skipped)


def test_a_refused_row_gets_one_plain_why_line_with_the_fix_to_try():
    a = _rows()[0]
    res = lcs.run_seed(json.dumps([{**a, "name": "NOT-A-CONTRACT"}]), SeedStore(), KNOWN, aliases=ALIASES)
    text = lcs.format_result(res, "closes.json")
    why = [line for line in text.splitlines() if line.startswith("why: ")]
    assert len(why) == 1 and "name" in why[0] and "--map name=" in why[0], text
