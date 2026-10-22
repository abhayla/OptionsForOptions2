"""REQ-048 AC-5 (W-134): the browser never decides execution eligibility (T1 #176).

A browser that adds its own ``eligible`` / ``executable`` / ``tradable`` claim to a request on the execute or the
planned-entry route is refused (422, ``extra="forbid"``); the claim never reaches the server's gate. No database: the
planned-entry route is driven on the recorded 2026-10-08 replay, the execute route up to its body validation.
Guards knowledge/findings/caller-supplied-verdict-trusted.json."""
import pytest
from httpx import ASGITransport, AsyncClient

CLAIMS = ["eligible", "executable", "tradable"]
INPUT_REFUSED = "USER_INPUT_002"  # the catalogue answer for a body the model refuses
LIVE_ID = "NSE_FO:44616"  # a leg with a recorded quote (tests_app/test_catalogue_picker_api.py)


@pytest.fixture(scope="module")
def replay_ctx():
    from ofo_app.replay_mode import build_replay_context  # noqa: PLC0415

    return build_replay_context()


async def _post(app, path: str, body: dict):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        return await ac.post(path, json=body)


def _app(replay_ctx):
    from ofo_app.main import create_app  # noqa: PLC0415
    from ofo_app.routes.outcome import get_market_context  # noqa: PLC0415

    app = create_app()
    app.dependency_overrides[get_market_context] = lambda: replay_ctx
    return app


@pytest.mark.parametrize("claim", CLAIMS)
@pytest.mark.parametrize("value", [True, "yes"])
async def test_a_browser_claim_on_planned_entry_is_refused_and_the_answer_is_unchanged(replay_ctx, claim, value):
    body = {"underlying": "NIFTY", "instrument_ids": [LIVE_ID]}
    clean = await _post(_app(replay_ctx), "/api/strategies/planned-entry", body)
    assert clean.status_code == 200, clean.text  # noqa: PLR2004
    claimed = await _post(_app(replay_ctx), "/api/strategies/planned-entry", body | {claim: value})
    assert claimed.status_code == 422, claimed.text  # noqa: PLR2004
    assert claimed.json()["code"] == INPUT_REFUSED  # the catalogue's refused-input answer; the clean body got 200
    assert "entries" not in claimed.json()  # no priced answer was produced for the claimant


@pytest.mark.parametrize("claim", CLAIMS)
async def test_a_browser_claim_on_execute_is_refused_and_no_basket_is_made(replay_ctx, claim, monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("OFO_ORDER_PATH", "1")
    resp = await _post(_app(replay_ctx), "/strategies/1/execute", {"action": "ENTRY", claim: True})
    assert resp.status_code == 422, resp.text  # noqa: PLR2004
    assert resp.json()["code"] == INPUT_REFUSED
    assert "basket" not in resp.json()  # the decision stays the server's: nothing was prepared for a claimant


def test_the_execute_and_planned_entry_bodies_forbid_extra_fields():
    from ofo_app.routes.execute import ExecuteIn  # noqa: PLC0415
    from ofo_app.routes.planned_entry import PlannedEntryIn  # noqa: PLC0415

    for model in (ExecuteIn, PlannedEntryIn):
        assert model.model_config.get("extra") == "forbid", model.__name__
