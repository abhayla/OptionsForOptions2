"""W-117 (REQ-011 AC-1; ADR-114): GET /api/strategy-templates lists the reviewed catalogue, read-only, no database.

Expected values come from the one catalogue loader (``ofo.strategy.loader.load_templates``), never typed here: the route
must show exactly the reviewed names and descriptions. The real app runs in-process without its lifespan, so no database
is opened.
"""
from __future__ import annotations

import pytest
from ofo.errors import render
from ofo.errors.explanations import render_explanation
from ofo.strategy.loader import load_templates
from ofo_app.main import create_app
from ofo_app.routes import strategy_templates
from starlette.testclient import TestClient

HTTP_OK = 200
HTTP_METHOD_NOT_ALLOWED = 405
CATALOGUE_SIZE = 21  # the catalogue file's own header: "The catalogue is 21 templates."


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("OUTCOME_REPLAY", "1")
    monkeypatch.delenv("LIVE_MARKET", raising=False)
    return TestClient(create_app())


def test_ac1_all_templates_equal_the_catalogue_loader(client: TestClient) -> None:
    """AC-1: the core proof. 21 templates, ids unique, every name, description, level, view and objective equal to
    the loader's values, in the catalogue's order."""
    response = client.get(strategy_templates.PATH)
    assert response.status_code == HTTP_OK
    got = response.json()["templates"]
    expected = load_templates()
    assert len(expected) == CATALOGUE_SIZE and len(got) == CATALOGUE_SIZE
    assert len({t["id"] for t in got}) == CATALOGUE_SIZE
    for row, template in zip(got, expected, strict=True):
        assert row == {"id": template.id, "name": template.name, "description": template.description,
                       "level": template.level, "views": list(template.views),
                       "objectives": list(template.objectives),
                       "legs": [leg.model_dump() for leg in strategy_templates.default_legs(template)]}


def test_ac1_unknown_query_parameters_do_not_change_the_answer(client: TestClient) -> None:
    """AC-1: the route takes no input; an unknown query parameter is ignored (the app's rule for a read without
    parameters), and the answer is the same."""
    plain = client.get(strategy_templates.PATH).json()
    with_extra = client.get(strategy_templates.PATH, params={"level": "Advanced", "x": "1"})
    assert with_extra.status_code == HTTP_OK and with_extra.json() == plain


def test_ac1_the_route_is_read_only(client: TestClient) -> None:
    """AC-1 (negative): only GET exists; a write gets 405 and the catalogue is unchanged."""
    before = client.get(strategy_templates.PATH).json()
    for send in (client.post, client.put, client.delete):
        assert send(strategy_templates.PATH).status_code == HTTP_METHOD_NOT_ALLOWED
    assert client.get(strategy_templates.PATH).json() == before


def test_ac1_a_text_the_catalogue_does_not_hold_cannot_pass_the_door() -> None:
    """AC-1 (negative): the catalogue-text slot takes only a name or description the loaded catalogue holds, so a
    route cannot put its own sentence in a template's name."""
    with pytest.raises(TypeError):
        render_explanation("catalogue_template_name", text="Buy this one now")
    with pytest.raises(TypeError):
        render_explanation("catalogue_template_description", text=render("user_input_request_invalid"))
    first = load_templates()[0]
    assert render_explanation("catalogue_template_name", text=first.name) == first.name


def test_w119_template_legs_are_the_catalogue_defaults() -> None:
    """REQ-024 AC-2 (W-119): each template carries its legs at the catalogue defaults, strikes in steps from ATM.
    Expected values from catalogue.yaml text: bull_call_spread k=0, w=4 (REQ-079 AC-3: BUY 22,800 / SELL 23,000 is 4 steps of 50) -> BUY CE k, SELL CE k + w."""
    by_id = {t.id: t for t in strategy_templates.strategy_templates().templates}
    assert [leg.model_dump() for leg in by_id["bull_call_spread"].legs] == [
        {"action": "BUY", "instrument": "CE", "strike_steps": 0, "expiry_slot": "near", "quantity_multiplier": 1},
        {"action": "SELL", "instrument": "CE", "strike_steps": 4, "expiry_slot": "near", "quantity_multiplier": 1}]
    assert all(t.legs for t in by_id.values())
