"""Issue #500 (finding stored-contract-priced-by-reused-token): a saved strategy's stored contract ids reach a feed key
(segment:token) only through ofo_app.tracked_contracts.resolve, app-wide.

The saved strategy is test_strategy_store's iron condor (expiry 2026-10-13): leg 0 is SELL 22800 CE on NSE_FO:44624.
Catalogue answer states (standing item d): live (key given), contract_retired, contract_delisted, token_reassigned
(delisted, then a NEW live 26000 CE 2026-11-24 takes NSE_FO:44624), contract_missing (no row). A leg that is not live
carries its reason and NO key, so the Builder can send no outcome request for it (fail closed); Execute refuses it.
"""
from __future__ import annotations

import pathlib
import sys
import types
from http import HTTPStatus

import pytest
from sqlalchemy import text

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests_app"))

from ofo_app.routes import execute as execute_routes  # noqa: E402
from ofo_app.routes.strategies import StrategyRefused  # noqa: E402
from test_strategy_store import _client  # noqa: E402
from test_strategy_tracking import _DELIST, _RETIRE, _REUSE, IDS, _setup  # noqa: E402
from test_strategy_tracking import db as _rolled_back_db  # noqa: E402

db = _rolled_back_db  # the fixture: one connection whose outer transaction is always rolled back (0 rows left)

NOT_LIVE = [((_DELIST, _REUSE), "token_reassigned"), ((_RETIRE,), "contract_retired"), ((_DELIST,), "contract_delisted")]
NOT_LIVE_IDS = ["token_reassigned", "contract_retired", "contract_delisted"]


async def _after(db, sqls):
    app, stored, *_ = await _setup(db)
    for sql in sqls:
        await db.execute(text(sql), {"id": stored.saved.contract_ids[0]})
    return app, stored


def _keys(legs: list[dict]) -> list[tuple[str, str | None, int | None]]:
    return [(leg["contract_state"], leg["exchange_segment"], leg["exchange_token"]) for leg in legs]


def _live(iid: str) -> tuple[str, str, int]:
    segment, token = iid.split(":")
    return ("live", segment, int(token))


async def test_a_live_saved_strategy_gives_every_leg_its_own_key(db):
    """All four legs live: each leg's key is its own contract's (the outcome request's ids), state live."""
    app, stored = await _after(db, ())
    async with _client(app) as c:
        got = await c.get(f"/strategies/{stored.id}")
    assert got.status_code == HTTPStatus.OK, got.text
    assert _keys(got.json()["definition"]["legs"]) == [_live(i) for i in IDS]


@pytest.mark.parametrize(("sqls", "state"), NOT_LIVE, ids=NOT_LIVE_IDS)
async def test_a_not_live_leg_has_no_key_and_names_why_on_load_and_history(db, sqls, state):
    """The reused-token case is the bug: before #500 leg 0 still carried NSE_FO:44624, now the NEW 26000 CE's token, so
    the Builder priced another contract. Now leg 0 has no key and its reason, on GET and on every history entry; the
    other legs keep theirs."""
    app, stored = await _after(db, sqls)
    async with _client(app) as c:
        got = await c.get(f"/strategies/{stored.id}")
        history = await c.get(f"/strategies/{stored.id}/history")
    assert got.status_code == HTTPStatus.OK, got.text
    want = [(state, None, None)] + [_live(i) for i in IDS[1:]]
    assert _keys(got.json()["definition"]["legs"]) == want
    assert history.status_code == HTTPStatus.OK, history.text
    entries = history.json()["entries"]
    assert all(_keys(e["definition"]["legs"]) == want for e in entries)  # a store-made draft may have no entry yet
    # display identity is still the stored contract's own terms, never the new holder's (22800 CE, not 26000 CE)
    leg0 = got.json()["definition"]["legs"][0]
    assert (leg0["strike"], leg0["expiry"]) == ("22800.00", "2026-10-13")


def _request(db) -> types.SimpleNamespace:
    return types.SimpleNamespace(action=execute_routes.ENTRY, db=db)


async def test_execute_prices_a_live_strategy_by_its_own_keys(db):
    """Execute's entry legs (order path; switched off by W-121, still routed through resolve): live -> own ids."""
    _app, stored = await _after(db, ())
    legs = await execute_routes._wanted(_request(db), stored, {})
    assert [f"{leg.instrument_id.exchange_segment}:{leg.instrument_id.exchange_token}" for leg in legs] == IDS


@pytest.mark.parametrize(("sqls", "state"), NOT_LIVE, ids=NOT_LIVE_IDS)
async def test_execute_refuses_a_leg_that_is_not_live(db, sqls, state):
    """A not-live leg is refused before any price read; the reused token's new holder is never ordered."""
    _app, stored = await _after(db, sqls)
    with pytest.raises(StrategyRefused) as refused:
        await execute_routes._wanted(_request(db), stored, {})
    assert refused.value.args == ("gate_contract_not_live",), state
