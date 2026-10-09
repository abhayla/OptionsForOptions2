"""W-066 (issue #151, REQ-034 AC-7; ADR-003 Q226): every user-facing text the outcome API returns is a catalogue
render with typed slots, on the real W-063 NIFTY iron condor (replay of 2026-10-08), at all three UX levels and with
no provider; and the W-024 guards pass on the outcome route with no exemption. No database is needed.

Expected sentences are written literally (max loss 8,245.25, max profit 4,754.75, breakevens 22,326.85 / 22,873.15),
never computed by the code under test."""
from __future__ import annotations

import ast
import datetime
import pathlib
import sys
from decimal import Decimal

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tests_app"))

from marketdata._kite_fixture import all_instrument_ids, new_provider, replay  # noqa: E402

from ofo.errors.explanations import ExplanationText  # noqa: E402
from ofo.marketdata.kite_provider import IST  # noqa: E402

VALUATION = datetime.datetime(2026, 10, 8, 9, 20, 9, tzinfo=IST)
RATE = Decimal("0.065")
CONDOR = (("NSE_FO:44624", "SELL"), ("NSE_FO:44632", "BUY"), ("NSE_FO:44604", "SELL"), ("NSE_FO:44595", "BUY"))
#: Fields of the response that are NOT free text: closed codes, ids, symbols and numbers (typed in the model).
NOT_TEXT = {"state", "underlying", "ux_level", "kind", "view", "action", "instrument", "health", "side",
            "instrument_id", "symbol", "id", "row_id", "value", "per_unit", "vendor", "strike", "planned_entry", "ltp",
            "iv", "spot_level", "level", "pnl", "max_profit", "max_loss", "lower_be", "upper_be", "step", "start",
            "end", "bid", "ask", "expiry", "captured_at", "valuation", "spot_at", "markers"}

LOSE = "At most ₹8,245.25 at expiry."
MAKE = "At most ₹4,754.75 at expiry."
START = "If NIFTY ends below 22,326.85 or above 22,873.15 at expiry."


@pytest.fixture(scope="module")
def replayed():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    return provider


def _request(provider, ux_level):
    from ofo_app.routes.outcome import OutcomeRequest

    legs = [{"instrument_id": iid, "action": action, "lots": 1,
             "planned_entry": f"{provider.book.get(iid, VALUATION).ltp:f}", "captured_at": VALUATION.isoformat()}
            for iid, action in CONDOR]
    return OutcomeRequest.model_validate({"underlying": "NIFTY", "legs": legs, "ux_level": ux_level})


def _response(provider, ux_level, with_provider=True):
    from ofo_app.routes.outcome import MarketContext, outcome_response

    ctx = MarketContext(provider, lambda: VALUATION, RATE) if with_provider else None
    return outcome_response(_request(provider, ux_level), ctx)


def _leaf(path, name, value):
    """Yield (path, field name, value) for every leaf of a response model (lists and dicts walked)."""
    from pydantic import BaseModel

    here = f"{path}.{name}"
    if isinstance(value, BaseModel):
        for sub in type(value).model_fields:
            yield from _leaf(here, sub, getattr(value, sub))
    elif isinstance(value, (list, tuple)):
        for i, item in enumerate(value):
            yield from _leaf(f"{here}[{i}]", name, item) if isinstance(item, BaseModel) else [(f"{here}[{i}]", name, item)]
    elif isinstance(value, dict):
        for k, item in value.items():
            yield from _leaf(f"{here}[{k}]", name, item) if isinstance(item, BaseModel) else [(f"{here}[{k}]", name, item)]
    else:
        yield (here, name, value)


def _text_leaves(model):
    out = []
    for path, name, value in _leaf("$", "response", model):
        if isinstance(value, str) and name not in NOT_TEXT:
            out.append((path, value))
    return out


def test_the_response_model_is_an_api_model() -> None:
    from ofo_app.api_models import ApiModel
    from ofo_app.routes.outcome import OutcomeResponse

    assert issubclass(OutcomeResponse, ApiModel)


@pytest.mark.parametrize("ux", ["guided", "standard", "advanced"])
def test_every_text_field_is_a_catalogue_render_at_every_ux_level(replayed, ux) -> None:
    texts = _text_leaves(_response(replayed, ux))
    assert len(texts) >= 30  # status/output labels, leg labels, 20+ column labels, cell displays and reasons
    plain = [(p, repr(v)[:50]) for p, v in texts if type(v) is not ExplanationText]
    assert plain == []


def test_every_text_field_is_a_catalogue_render_with_no_provider(replayed) -> None:
    texts = _text_leaves(_response(replayed, "standard", with_provider=False))
    assert len(texts) >= 6
    assert [(p, repr(v)[:50]) for p, v in texts if type(v) is not ExplanationText] == []


async def test_the_three_plain_language_sentences_keep_the_w063_numbers(replayed) -> None:
    out = _response(replayed, "standard").model_dump(mode="json")
    s = out["summary"]
    assert (s["what_can_i_lose"], s["what_can_i_make"], s["where_do_i_start_losing"]) == (LOSE, MAKE, START)
    assert (s["max_loss"], s["max_profit"], s["breakevens"]) == ("8245.25", "4754.75", ["22326.85", "22873.15"])


def test_status_and_margin_texts_are_exact(replayed) -> None:
    none = _response(replayed, "standard", with_provider=False).model_dump(mode="json")
    assert none["status_label"] == "Draft - Live data not connected"
    assert none["reason"] == "no live market data provider is connected"
    assert none["margin"]["reason"] == "margin from Zerodha comes with the margin item (needs the Kite login)"
    assert all(leg["label"] == "Draft - Live data not connected" for leg in none["legs"])


def test_column_and_cell_texts_are_exact(replayed) -> None:
    out = _response(replayed, "standard").model_dump(mode="json")
    labels = [c["label"] for c in out["table"]["columns"]]
    assert labels[:3] == ["Leg", "Action", "Instrument"] and labels[-3:] == ["Lower Breakeven", "Upper Breakeven", "Status"]
    assert "CURRENT 22,533.25" in labels
    total = next(r for r in out["table"]["rows"] if r["row_id"] == "TOTAL")
    assert total["cells"]["lower_be"]["display"] == "22,326.85" and total["cells"]["upper_be"]["display"] == "22,873.15"
    assert total["cells"]["status"] == {"value": None, "display": "—", "kind": "text",
                                        "reason": "no strategy health was given", "side": None, "per_unit": None,
                                        "vendor": None}
    assert out["scenario"]["label"] == "At Expiry"


def test_the_outcome_route_passes_the_w024_guards_with_no_exemption() -> None:
    """The two W-024 guards, applied to the outcome route as they apply to every other route."""
    from fastapi.routing import APIRoute

    from ofo_app.api_models import ApiModel
    from ofo_app.main import create_app
    import test_error_boundary_scan as scan_module

    path = ROOT / "backend" / "ofo_app" / "routes" / "outcome.py"
    assert scan_module.scan(path.read_text(encoding="utf-8"), "routes/outcome.py") == []
    routes = [r for r in create_app().routes if isinstance(r, APIRoute) and r.path == "/api/strategies/outcome"]
    assert len(routes) == 1 and issubclass(routes[0].response_model, ApiModel)
    assert "HTTPException" not in {n.id for n in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                                   if isinstance(n, ast.Name)}
