"""W-101 core proof over HTTP (REQ-073 AC-3): Execute ENTRY, then the return from Kite, on the RUNNING replay API.

Runs only in CI's replay step, which starts an API with ``APP_ENV=test`` + ``EXECUTE_REPLAY=1`` (the recorded
2026-10-16 Kite replies; no live session, no live feed), seeds strategy 1 + a Pro grant
(``python -m ofo_app.seed_execute_replay``) and sets ``EXECUTE_REPLAY_URL``. Without that URL the normal app suite
skips this file. Expected values are the owner's real order (basket-121848.json: BUY 65 NIFTY26O1923650CE LIMIT, tag
OFS1V1L0) priced by hand on the recorded depth (best ask 3.35 x 56,810 covers 65, ADR-080 (3)), and the real 12:21:04
book (OFS1V1L0 COMPLETE 65, +65 held: plan 1 filled, platform 65 = Zerodha 65, no mismatch).
"""
from __future__ import annotations

import os
from http import HTTPStatus

import httpx
import pytest

URL = os.environ.get("EXECUTE_REPLAY_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="EXECUTE_REPLAY_URL unset: runs only against CI's replay API")


def test_ac3_execute_entry_then_return_closes_plan_1_filled_with_no_mismatch():
    """AC-3: POST Execute ENTRY -> exactly BUY 65 NIFTY26O1923650CE LIMIT "3.35" tag OFS1V1L0 (plan 1); POST the return
    -> plan 1 filled, 0 mismatches, platform 65 = Zerodha 65."""
    with httpx.Client(base_url=URL, timeout=30) as client:
        entry = client.post("/strategies/1/execute", json={"action": "ENTRY"})
        assert entry.status_code == HTTPStatus.OK, entry.text
        body = entry.json()
        assert body["plan_number"] == 1 and body["tags"] == ["OFS1V1L0"]
        assert [(o["transaction_type"], o["quantity"], o["tradingsymbol"], o["order_type"], o["price"], o["tag"])
                for o in body["orders"]] == [("BUY", 65, "NIFTY26O1923650CE", "LIMIT", "3.35", "OFS1V1L0")]
        assert body["basket"]["api_key"] == "kitekey"

        back = client.post("/strategies/1/execution/return")
        assert back.status_code == HTTPStatus.OK, back.text
        ret = back.json()
        assert [(p["plan_number"], p["action"], p["state"]) for p in ret["plans"]] == [(1, "ENTRY", "filled")]
        assert ret["mismatches"] == 0 and ret["blocked"] is False
        contracts = [(c["tradingsymbol"], c["platform_units"], c["zerodha_units"], c["mismatch"])
                     for c in ret["contracts"]]
        assert contracts == [("NIFTY26O1923650CE", 65, 65, None)]
