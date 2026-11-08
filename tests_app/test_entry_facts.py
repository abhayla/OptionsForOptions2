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

import asyncio
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
from sqlalchemy import text
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
        contract=SimpleNamespace(instrument_type=t, strike=D(k), expiry=EXPIRY)))) for cid, t, k in legs}


_ORDERS = [SimpleNamespace(contract_id=1, side="SELL", kind="open"),
           SimpleNamespace(contract_id=2, side="BUY", kind="open"),
           SimpleNamespace(contract_id=3, side="SELL", kind="open")]
_LEGS = ((1, "CE", "23400"), (2, "CE", "23600"), (3, "PE", "22700"))
ENTRY_IV = D("0.1432")


def _iv_answers(monkeypatch, answer):
    """``atm_iv_now`` (the check's ATM-IV figure) answers ``answer`` (a value, None, or an exception to raise)."""
    from ofo_app import adjustment_readers  # noqa: PLC0415
    seen = []

    async def fake(_ctx, underlying, expiry, spot):
        seen.append((underlying, expiry, spot))
        if isinstance(answer, Exception):
            raise answer
        return answer
    monkeypatch.setattr(adjustment_readers, "atm_iv_now", fake)
    return seen


def test_paper_route_entry_facts_from_the_live_spot_and_the_sold_strikes(monkeypatch):
    seen = _iv_answers(monkeypatch, None)
    state = _state(*_LEGS)
    assert asyncio.run(paper_route.entry_facts(_ctx(ENTRY_SPOT), "NIFTY", _ORDERS, state)) == REQ046_FACTS
    for ctx in (None, _ctx(ENTRY_SPOT, connected=False), _ctx(None), _ctx(D(0))):
        assert asyncio.run(paper_route.entry_facts(ctx, "NIFTY", _ORDERS, state)) is None  # never a guess
    assert seen == [("NIFTY", EXPIRY, ENTRY_SPOT)]  # the IV asked once, of the sold legs' expiry, at the live spot


def test_paper_route_entry_facts_carry_the_entry_atm_iv(monkeypatch):
    """ADR-270 (1): stated -> stored with the facts; unreadable (None, or the read fails) -> facts without IV."""
    state = _state(*_LEGS)
    _iv_answers(monkeypatch, ENTRY_IV)
    assert asyncio.run(paper_route.entry_facts(_ctx(ENTRY_SPOT), "NIFTY", _ORDERS, state)) == replace(
        REQ046_FACTS, entry_atm_iv=ENTRY_IV)
    _iv_answers(monkeypatch, RuntimeError("feed gone"))
    assert asyncio.run(paper_route.entry_facts(_ctx(ENTRY_SPOT), "NIFTY", _ORDERS, state)) == REQ046_FACTS
    seen = _iv_answers(monkeypatch, ENTRY_IV)  # no sold option: nothing to read an IV of
    assert asyncio.run(paper_route.entry_facts(_ctx(ENTRY_SPOT), "NIFTY", _ORDERS[1:2], state)) == (
        EntryFacts(ENTRY_SPOT, None, None)) and seen == []


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
    assert {a["basis_source"] for a in got.values() if a["step_basis"] is not None} == {"default"}, [
        (a["id"], a["step_basis"], a["refusal"]) for a in got.values()
    ]
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
    from sqlalchemy import text  # noqa: PLC0415
    from test_strategy_store import _user  # noqa: PLC0415

    user = _user()
    sid, c = await _strategy(db, user)
    await paper_store.place(db, user, sid, [_new(c[1], "SELL", 65, "82.75")], entry=REQ046_FACTS)
    for sql in ("UPDATE public.strategy_entry_facts SET entry_spot = 1 WHERE strategy_id = :id",
                "DELETE FROM public.strategy_entry_facts WHERE strategy_id = :id"):
        with pytest.raises(DBAPIError):
            async with db.begin_nested():
                await db.execute(text(sql), {"id": sid})
    assert await entry_facts_store.read(db, sid) == REQ046_FACTS


# --- migration 0046: the entry ATM IV beside the entry facts (ADR-270 (1)) ---------------------------------------

ENTRY_IV = D("0.1432")
MIGRATION_0046 = "0046_entry_atm_iv.py"
_IV_COLUMN = ("SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' "
              "AND table_name = 'strategy_entry_facts' AND column_name = 'entry_atm_iv'")


async def test_entry_atm_iv_round_trips_exactly_through_the_app_role(db):
    from test_strategy_store import _user  # noqa: PLC0415

    sid, _ = await _strategy(db, _user())  # db = the limited app role: its column INSERT grant covers the IV
    await entry_facts_store.record_first(db, sid, replace(REQ046_FACTS, entry_atm_iv=ENTRY_IV))
    stored = await entry_facts_store.read(db, sid)
    assert stored is not None and isinstance(stored.entry_atm_iv, D)
    assert str(stored.entry_atm_iv) == "0.1432"  # exact, never a float


async def test_entry_atm_iv_not_known_at_entry_reads_back_none(db):
    from test_strategy_store import _user  # noqa: PLC0415

    sid, _ = await _strategy(db, _user())
    await entry_facts_store.record_first(db, sid, REQ046_FACTS)
    stored = await entry_facts_store.read(db, sid)
    assert stored == REQ046_FACTS and stored.entry_atm_iv is None


async def test_entry_atm_iv_is_refused_when_not_positive(db):
    from test_strategy_store import _user  # noqa: PLC0415

    sid, _ = await _strategy(db, _user())
    with pytest.raises(DBAPIError, match="check"):  # the column's own CHECK, written past the store
        async with db.begin_nested():
            await db.execute(text("INSERT INTO public.strategy_entry_facts (strategy_id, entry_spot, entry_atm_iv) "
                                  "VALUES (:id, 23047, 0)"), {"id": sid})
    assert await entry_facts_store.read(db, sid) is None
    # the store never sends it: a 0 IV becomes "no IV" and the facts are still kept (written once, never again)
    await entry_facts_store.record_first(db, sid, replace(REQ046_FACTS, entry_atm_iv=D(0)))
    kept = await entry_facts_store.read(db, sid)
    assert kept is not None and kept.entry_spot == REQ046_FACTS.entry_spot and kept.entry_atm_iv is None


async def test_the_guard_refuses_an_update_of_entry_atm_iv(db):
    from sqlalchemy import text  # noqa: PLC0415
    from test_strategy_store import _user  # noqa: PLC0415

    sid, _ = await _strategy(db, _user())
    await entry_facts_store.record_first(db, sid, replace(REQ046_FACTS, entry_atm_iv=ENTRY_IV))
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(text("UPDATE public.strategy_entry_facts SET entry_atm_iv = 0.2 WHERE strategy_id = :id"),
                             {"id": sid})
    assert (await entry_facts_store.read(db, sid)).entry_atm_iv == ENTRY_IV  # type: ignore[union-attr]


async def test_a_stored_iv_that_is_not_an_exact_decimal_is_unreadable():
    row = SimpleNamespace(entry_spot=ENTRY_SPOT, call_distance=D("353"), put_distance=None, entry_atm_iv=0.1432,
                          created_at=AT)

    class _Conn:
        async def execute(self, *_a, **_k):
            return SimpleNamespace(first=lambda: row)

    with pytest.raises(entry_facts_store.EntryFactsUnreadable, match="not an exact Decimal"):
        await entry_facts_store.read(_Conn(), 1)


async def test_0046_round_trip_drops_and_restores_the_column_with_the_allowlist_passing(admin_engine):
    from _migration_replay import round_trip_sql  # noqa: PLC0415
    from sqlalchemy import text  # noqa: PLC0415

    own_down, own_up, down, up = round_trip_sql(MIGRATION_0046)
    assert "'pre'" in own_up[0] and "'post'" in own_up[-1] and "'post'" in own_down[-1]
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            assert (await conn.execute(text(_IV_COLUMN))).scalar() == 1
            for sql in down:  # ends with the allow-list post check against 0045's four-column block 31
                await conn.execute(text(sql))
            assert (await conn.execute(text(_IV_COLUMN))).scalar() == 0
            for sql in up:  # ends with the post check against the five-column block 31
                await conn.execute(text(sql))
            assert (await conn.execute(text(_IV_COLUMN))).scalar() == 1
        finally:
            await trans.rollback()


async def test_allowlist_post_check_fails_without_insert_on_entry_atm_iv(admin_engine, app_engine):
    from sqlalchemy import text  # noqa: PLC0415

    role = app_engine.url.username
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await conn.execute(text(f"SELECT public.ofo_assert_app_role_allowlist('{role}', 'post')"))  # passes
            await conn.execute(text(f'REVOKE INSERT (entry_atm_iv) ON public.strategy_entry_facts FROM "{role}"'))
            with pytest.raises(DBAPIError, match=r"lacks INSERT on strategy_entry_facts column entry_atm_iv"):
                async with conn.begin_nested():
                    await conn.execute(text(f"SELECT public.ofo_assert_app_role_allowlist('{role}', 'post')"))
        finally:
            await trans.rollback()


async def test_0046_downgrade_is_refused_with_a_count_while_an_iv_is_stored(admin_engine):
    from _migration_replay import recorded  # noqa: PLC0415
    from sqlalchemy import text  # noqa: PLC0415
    from test_strategy_store import _user  # noqa: PLC0415

    own_down = recorded(MIGRATION_0046, "downgrade")
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            sid, _ = await _strategy(conn, _user())
            await entry_facts_store.record_first(conn, sid, replace(REQ046_FACTS, entry_atm_iv=ENTRY_IV))
            with pytest.raises(DBAPIError, match=r"refusing to downgrade 0046_entry_atm_iv: 1 stored entry ATM IVs"):
                async with conn.begin_nested():
                    for sql in own_down:
                        await conn.execute(text(sql))
        finally:
            await trans.rollback()


@pytest.mark.parametrize("stored", [D("NaN"), D("Infinity")])
async def test_a_stored_iv_that_is_not_finite_is_unreadable(stored):
    """Tier A review (GC-ICTRACK 32): PostgreSQL's > 0 CHECK lets NaN and Infinity in; read fails closed on them."""
    row = SimpleNamespace(entry_spot=ENTRY_SPOT, call_distance=D("353"), put_distance=None, entry_atm_iv=stored,
                          created_at=AT)

    class _Conn:
        async def execute(self, *_a, **_k):
            return SimpleNamespace(first=lambda: row)

    with pytest.raises(entry_facts_store.EntryFactsUnreadable):
        await entry_facts_store.read(_Conn(), 1)


@pytest.mark.parametrize(("iv", "stored"), [(D("0.1432"), D("0.1432")), (D("NaN"), None), (D("Infinity"), None),
                                            (D(0), None), (D("-0.1"), None), (0.14, None), (None, None)])
def test_only_a_finite_positive_decimal_iv_is_stored(iv, stored):
    assert entry_facts_store.usable_iv(iv) == stored
