"""ADR-243 roll basis "Entry distance from spot" (contract "Your adjustment settings" step 2): each strategy's entry
facts are stored ONCE at its first fill (migration 0039, ``paper_store.place``), and the Compare / approaches reply
builds every roll on the basis in force and names it (step_basis, step_value, basis_source).

Core proof (DB, fresh database): a first fill stores entry spot 23,047 with the short call 353 above and the short put
347 below; a later fill never rewrites it; for a user whose basis is "Entry distance" the roll at spot 23,300 is the
REQ-046 placement 23,650 / 23,850, named "entry_distance" 353 from source "user". A strategy with no stored facts
(first filled before this change) is refused by name under "Entry distance" (fail closed, no roll).
Answer states of every read: present / absent / unreadable (``roll_basis_of``, ``entry_facts_store.read``).
"""
from __future__ import annotations

import datetime
import json
from dataclasses import replace
from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from ofo.adjustment.approaches import (
    NO_STRATEGY_BASIS,
    ROLL_ENTRY_DISTANCE,
    ROLL_TARGET_DELTA,
    ChainRow,
    EntryFacts,
    Position,
    PositionLeg,
    build_approach,
    entry_facts_of,
)
from ofo.settings import layers
from ofo_app import adjustment_check as check
from ofo_app import entry_facts_store, paper_store, user_preferences_store
from ofo_app.routes import paper as paper_route
from sqlalchemy.exc import DBAPIError

AT = datetime.datetime(2026, 11, 5, 5, 0, tzinfo=datetime.UTC)
EXPIRY = datetime.date(2026, 11, 10)
ENTRY_SPOT = D("23047")
SPOT = D("23300")
REQ046_FACTS = EntryFacts(ENTRY_SPOT, D("353"), D("347"))


def _values(own_basis: D | None, admin: D = D(1)) -> user_preferences_store.UserValues:
    """The store's own record: ``adjustments.roll_basis`` the user's own (``own_basis``) or the admin default."""
    from ofo import settings  # noqa: PLC0415

    defaults = settings.defaults()
    answers = {k: user_preferences_store.Answer(k, defaults[k], "default", defaults[k], None)
               for k in user_preferences_store.preference_keys()}
    answers[layers.ROLL_BASIS] = (user_preferences_store.Answer(layers.ROLL_BASIS, admin, "default", admin, None)
                                  if own_basis is None else
                                  user_preferences_store.Answer(layers.ROLL_BASIS, own_basis, "yours", admin, AT))
    return user_preferences_store.UserValues(answers)


def _delta(strike: int, typ: str) -> D:
    away = (strike - SPOT) if typ == "CE" else (SPOT - strike)
    raw = D("0.50") - D(away) / D(2500)
    value = max(D("0.02"), raw) if away >= 0 else min(D("0.98"), raw)
    return value if typ == "CE" else -value


def _chain() -> list[ChainRow]:
    return [ChainRow(D(k), t, EXPIRY, f"NIFTY{k}{t}", D("10.00"), D("9.95"), D("10.05"), _delta(k, t))
            for k in range(22000, 24601, 50) for t in ("CE", "PE")]


def _condor() -> Position:
    legs = (PositionLeg("BUY", "PE", D("22500"), EXPIRY, 1, D("5"), "p1"),
            PositionLeg("SELL", "PE", D("22700"), EXPIRY, 1, D("20"), "p2"),
            PositionLeg("SELL", "CE", D("23400"), EXPIRY, 1, D("20"), "c1"),
            PositionLeg("BUY", "CE", D("23600"), EXPIRY, 1, D("5"), "c2"))
    return Position("NIFTY", 65, "weekly", datetime.date(2026, 11, 5), legs)


def _cfg(basis):
    from ofo import settings  # noqa: PLC0415
    from ofo.adjustment import preferences  # noqa: PLC0415

    cfg = preferences.from_values(settings.defaults()).approach  # the registry defaults, explicitly
    return replace(cfg, target_short_delta={"weekly": D("0.20"), "monthly": D("0.20")}, roll_basis=basis)


def _calls(built) -> list[D]:
    return sorted(x.strike for x in built.after if x.type == "CE")


# --- roll_basis_of: every answer state (no database) -------------------------------------------------------------


def test_roll_basis_of_user_entry_distance_with_stored_facts_carries_both_distances():
    basis = check.roll_basis_of(D(1), _values(D(2)), None, REQ046_FACTS)
    assert (basis.code, basis.source, basis.reason) == (ROLL_ENTRY_DISTANCE, layers.SOURCE_USER, None)
    assert (basis.entry_spot, basis.call_distance, basis.put_distance) == (ENTRY_SPOT, D("353"), D("347"))


@pytest.mark.parametrize("entry", [None, layers.Unreadable("boom")], ids=["absent", "unreadable"])
def test_roll_basis_of_without_readable_facts_carries_no_distance(entry):
    basis = check.roll_basis_of(D(1), _values(D(2)), None, entry)
    assert basis.code == ROLL_ENTRY_DISTANCE and (basis.call_distance, basis.put_distance) == (None, None)


def test_roll_basis_of_plan_override_and_default_and_unreadable_layers():
    assert check.roll_basis_of(D(1), _values(D(2)), {layers.ROLL_BASIS: "1"}, REQ046_FACTS).source == \
        layers.SOURCE_STRATEGY
    default = check.roll_basis_of(D(1), _values(None), None, None)
    assert (default.code, default.source) == (ROLL_TARGET_DELTA, layers.SOURCE_DEFAULT)
    assert check.roll_basis_of(D(1), _values(D(2)), layers.Unreadable("x"), None).reason == layers.STRATEGY_UNREADABLE
    assert check.roll_basis_of(D(1), {layers.ROLL_BASIS: D(2)}, None, None).reason == layers.USER_UNREADABLE
    assert check.roll_basis_of(None, _values(None), None, None).reason == layers.DEFAULT_UNREADABLE


def test_admin_of_reads_the_admin_layer_only():
    assert check.admin_of(_values(D(2), admin=D(1)), layers.ROLL_BASIS) == D(1)
    # no admin layer read (a plain mapping, no user read path): the REGISTRY default (1), never the mapping's own 2
    assert check.admin_of({layers.ROLL_BASIS: D(2)}, layers.ROLL_BASIS) == D(1)
    assert check.admin_of(None, layers.ROLL_BASIS) == D(1)


# --- the paper route's entry facts read (no database) ------------------------------------------------------------


def _ctx(ltp, connected=True):
    quote = None if ltp is None else SimpleNamespace(ltp=ltp)
    provider = SimpleNamespace(status=lambda: SimpleNamespace(connected=connected),
                               underlying_quote=lambda _u: quote)
    return SimpleNamespace(provider=provider)


def _state(*legs):
    return {cid: SimpleNamespace(stored=SimpleNamespace(listed=SimpleNamespace(
        contract=SimpleNamespace(instrument_type=t, strike=D(k))))) for cid, t, k in legs}


def test_paper_route_entry_facts_from_the_live_spot_and_the_sold_strikes():
    orders = [SimpleNamespace(contract_id=1, side="SELL", kind="open"),
              SimpleNamespace(contract_id=2, side="BUY", kind="open"),
              SimpleNamespace(contract_id=3, side="SELL", kind="open")]
    state = _state((1, "CE", "23400"), (2, "CE", "23600"), (3, "PE", "22700"))
    assert paper_route.entry_facts(_ctx(ENTRY_SPOT), "NIFTY", orders, state) == REQ046_FACTS
    for ctx in (None, _ctx(ENTRY_SPOT, connected=False), _ctx(None), _ctx(D(0))):
        assert paper_route.entry_facts(ctx, "NIFTY", orders, state) is None  # nothing stored, never a guess


# --- the approaches reply names the basis per roll (no database) -------------------------------------------------


def _reply(monkeypatch, own_basis, facts):
    import test_adjustment_approaches_route as harness  # noqa: PLC0415
    from ofo_app.routes import outcome  # noqa: PLC0415

    # the harness's own clock seam (its autouse fixture): spot judged at the scenario's clock
    monkeypatch.setattr(outcome, "server_now", lambda: harness._SCENARIO_NOW[0])
    async def values(_session, _user, at=None):
        return _values(own_basis)

    monkeypatch.setattr(user_preferences_store, "values_for", values)
    c = harness.client_for(harness.load("ADJ-02"))

    async def roll_inputs(_sid):
        return None, facts

    from ofo_app.routes import adjustment as route  # noqa: PLC0415

    c.app.dependency_overrides[route.get_roll_inputs_reader] = lambda: roll_inputs
    r = harness.post(c, body={"approaches": ["A-01", "A-05"]})
    assert r.status_code == 200, r.text  # noqa: PLR2004
    got = {a["id"]: a for a in r.json()["approaches"]}
    assert set(got) == {"A-01", "A-05"}, r.json()["spot"]  # never a vacuous pass on an empty reply
    return got


def test_reply_names_entry_distance_and_its_source_per_roll(monkeypatch):
    got = _reply(monkeypatch, D(2), EntryFacts(D("23000"), D("300"), D("300")))
    for a in got.values():
        assert (a["step_basis"], a["basis_source"]) == (ROLL_ENTRY_DISTANCE, "user"), a
        assert a["step_value"] == "300"


def test_reply_default_basis_is_target_delta_named_default(monkeypatch):
    got = _reply(monkeypatch, None, None)
    assert {a["basis_source"] for a in got.values() if a["step_basis"] is not None} == {"default"}, [(a["id"], a["step_basis"], a["refusal"]) for a in got.values()]
    assert all(a["step_basis"] in ("delta", "points", None) for a in got.values())


def test_reply_entry_distance_without_stored_facts_refuses_every_roll_by_name(monkeypatch):
    got = _reply(monkeypatch, D(2), None)
    for a in got.values():
        assert a["refusal"] is not None and "spot at entry is not stored" in json.dumps(a["refusal"]), a
        assert a.get("trades") is None


# --- the core proof on a real database ---------------------------------------------------------------------------


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def _strategy(db, user: str) -> tuple[int, list[int]]:
    from test_strategy_store import _with_draft  # noqa: PLC0415

    ids, stored = await _with_draft(db, user)
    return stored.id, sorted(ids.values())


def _new(contract: int, side: str, qty: int, price: str, kind: str = "open") -> paper_store.NewOrder:
    return paper_store.NewOrder(contract, side, qty, D(price), kind, AT)


async def test_core_first_fill_stores_entry_facts_once_and_entry_distance_places_req046(db):
    from test_strategy_store import _user  # noqa: PLC0415

    user = _user()
    sid, c = await _strategy(db, user)
    assert await entry_facts_store.read(db, sid) is None  # nothing before the first fill
    first = entry_facts_of(ENTRY_SPOT, [("PE", D("22700")), ("CE", D("23400"))])
    await paper_store.place(db, user, sid, [_new(c[1], "SELL", 65, "82.75")], entry=first)
    assert await entry_facts_store.read(db, sid) == REQ046_FACTS
    # a later fill never rewrites them (the second roll keeps 353)
    await paper_store.place(db, user, sid, [_new(c[0], "BUY", 65, "35.80")],
                            entry=EntryFacts(D("23500"), D("150"), D("800")))
    stored = await entry_facts_store.read(db, sid)
    assert stored == REQ046_FACTS
    basis = check.roll_basis_of(D(1), _values(D(2)), None, stored)
    built = build_approach(_condor(), _chain(), SPOT, "A-05", _cfg(basis))
    assert built.refusal is None
    assert _calls(built) == [D("23650"), D("23850")]
    assert (built.step_basis, built.step_value, built.basis_source) == (ROLL_ENTRY_DISTANCE, D("353"), "user")


async def test_core_strategy_with_no_stored_facts_is_refused_by_name_under_entry_distance(db):
    from test_strategy_store import _user  # noqa: PLC0415

    user = _user()
    sid, c = await _strategy(db, user)
    await paper_store.place(db, user, sid, [_new(c[1], "SELL", 65, "82.75")], entry=None)  # as before 0039
    assert await entry_facts_store.read(db, sid) is None
    basis = check.roll_basis_of(D(1), _values(D(2)), None, await entry_facts_store.read(db, sid))
    built = build_approach(_condor(), _chain(), SPOT, "A-05", _cfg(basis))
    assert built.trades == () and built.refusal_message.code == "USER_INPUT_191"  # type: ignore[union-attr]
    assert "spot at entry is not stored" in built.refusal
    # Target delta users are unaffected by the missing facts
    today = build_approach(_condor(), _chain(), SPOT, "A-05", _cfg(NO_STRATEGY_BASIS))  # today's rule, stated
    default = build_approach(_condor(), _chain(), SPOT, "A-05",
                             _cfg(check.roll_basis_of(D(1), _values(None), None, None)))
    assert (default.trades, default.after) == (today.trades, today.after)


async def test_stored_entry_facts_cannot_be_updated_or_deleted_by_the_app_role(db):
    from test_strategy_store import _user  # noqa: PLC0415
    from sqlalchemy import text  # noqa: PLC0415

    user = _user()
    sid, c = await _strategy(db, user)
    await paper_store.place(db, user, sid, [_new(c[1], "SELL", 65, "82.75")], entry=REQ046_FACTS)
    for sql in ("UPDATE public.strategy_entry_facts SET entry_spot = 1 WHERE strategy_id = :id",
                "DELETE FROM public.strategy_entry_facts WHERE strategy_id = :id"):
        with pytest.raises(DBAPIError):
            async with db.begin_nested():
                await db.execute(text(sql), {"id": sid})
    assert await entry_facts_store.read(db, sid) == REQ046_FACTS
