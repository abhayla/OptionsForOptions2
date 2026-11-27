"""The name column of a snapshot row: an index may carry its own name ("NIFTY 50") or its underlying ("NIFTY")."""
from __future__ import annotations

import json

import pytest
from ofo_app import last_close_store as lcs
from test_last_close_seed_aliases import ALIASES, KNOWN
from test_last_close_seed_command import SeedStore

INDEX_ID = next(i for i in KNOWN if i.startswith("NSE_INDEX:"))
ROW = {"instrument_id": INDEX_ID, "price": "25000.50", "price_at": "2026-11-27T15:30:00+05:30", "source": "feed-stream"}


@pytest.mark.parametrize("name,ok", [("NIFTY 50", True), ("nifty", True), ("SENSEX", False), ("BANKNIFTY", False)])
def test_an_index_row_may_name_the_index_or_its_underlying_and_nothing_else(name, ok):
    res = lcs.run_seed(json.dumps([{**ROW, "name": name}]), SeedStore(), KNOWN, aliases=ALIASES)
    assert (res.written == 1) is ok, res.skipped
