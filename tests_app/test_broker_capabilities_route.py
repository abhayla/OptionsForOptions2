"""REQ-117 AC-1, AC-4 (W-132): ``GET /api/broker/capabilities`` answers the seven named flags as on/off, from Zerodha's
declared data; a flag removed or a declaration that cannot load reads off; nothing in a request changes the answer.

Uses the real app (``create_app``) and the real declared data; no database is touched.
"""
from __future__ import annotations

import json

from fastapi.testclient import TestClient
from ofo.broker import kite_flags
from ofo_app.main import create_app

HTTP_OK = 200
HTTP_NOT_ALLOWED = 405
PATH = "/api/broker/capabilities"
SEVEN = ("basket_page_orders", "broker_held_triggers", "intraday_product", "order_update_stream", "funds_read",
         "positions_read", "basket_margin_quote")  # REQ-117 AC-1 wording
ZERODHA_ANSWER = {"basket_page_orders": True, "broker_held_triggers": False, "intraday_product": True,
                  "order_update_stream": True, "funds_read": True, "positions_read": True, "basket_margin_quote": True}


def _get(path: str = PATH, **kw):
    return TestClient(create_app(), raise_server_exceptions=False).get(path, **kw)


def test_ac1_the_route_answers_exactly_the_seven_flags_as_booleans() -> None:
    """AC-1/AC-2: exactly the seven keys, each a bool, held triggers off, every other Zerodha flag on."""
    response = _get()
    assert response.status_code == HTTP_OK
    assert response.json() == ZERODHA_ANSWER
    assert tuple(response.json()) == SEVEN
    assert "zerodha" not in response.text.lower() and "source" not in response.text.lower()


def test_ac4_a_flag_removed_from_the_declaration_reads_off(monkeypatch, tmp_path) -> None:
    """AC-4: remove basket_margin_quote from Zerodha's set -> the route says off for it and unchanged for the rest."""
    kept = json.loads(kite_flags.FLAG_FILE.read_text(encoding="utf-8"))
    del kept["basket_margin_quote"]
    flag_file = tmp_path / "kite_flags.json"
    flag_file.write_text(json.dumps(kept), encoding="utf-8")
    monkeypatch.setattr(kite_flags, "FLAG_FILE", flag_file)
    assert _get().json() == {**ZERODHA_ANSWER, "basket_margin_quote": False}


def test_ac4_a_declaration_that_cannot_load_reads_every_flag_off(monkeypatch, tmp_path) -> None:
    """AC-4: a malformed declaration (no source) and a loader that raises both answer 200 with all seven off."""
    bad = json.loads(kite_flags.FLAG_FILE.read_text(encoding="utf-8"))
    bad["funds_read"]["source"] = ""
    flag_file = tmp_path / "kite_flags.json"
    flag_file.write_text(json.dumps(bad), encoding="utf-8")
    monkeypatch.setattr(kite_flags, "FLAG_FILE", flag_file)
    assert _get().json() == dict.fromkeys(SEVEN, False)
    monkeypatch.setattr(kite_flags, "FLAG_FILE", tmp_path / "missing.json")  # a missing file is the same answer
    assert _get().json() == dict.fromkeys(SEVEN, False)
    monkeypatch.undo()

    def boom():
        raise OSError("unreadable")

    monkeypatch.setattr(kite_flags, "load_zerodha_flags", boom)
    response = _get()
    assert response.status_code == HTTP_OK and response.json() == dict.fromkeys(SEVEN, False)


def test_ac4_nothing_in_a_request_changes_the_answer_and_there_is_no_write_method() -> None:
    """Attack 7: query parameters and headers do not move a flag; POST/PUT/DELETE/PATCH are refused."""
    base = _get().json()
    for response in (_get(PATH + "?basket_margin_quote=false&broker_held_triggers=true&flags=all"),
                     _get(headers={"X-Capability": "broker_held_triggers", "X-Broker": "zerodha"})):
        assert response.json() == base
    client = TestClient(create_app(), raise_server_exceptions=False)
    for method in ("POST", "PUT", "DELETE", "PATCH"):
        refused = client.request(method, PATH, json={"broker_held_triggers": True})
        assert refused.status_code == HTTP_NOT_ALLOWED, method
    assert _get().json()["broker_held_triggers"] is False
