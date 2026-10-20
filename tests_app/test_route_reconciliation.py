"""#380-2 core proof (REQ-060 AC-6/AC-7; ADR-109 (2); Q224; fix-380 draft T3; #423): ONE reconciler for the Execute
route and the return route, on the owner's REAL 2026-10-19 Kite replies.

Real inputs (tests/fixtures/kite_replies/, README there): ``orders-2026-10-19-roundtrip.json`` and
``positions-2026-10-19-roundtrip.json``, copied from
``D:/Abhay/Ventures/ofo-kite-ticks/2026-10-19/replies-after-exit/`` (``orders-saved.json``, ``positions-saved.json``;
client id redacted to XX0000): OFS9V1L0 BUY 65 NIFTY26OCT24000CE COMPLETE, OFS9V2L0 SELL 65 COMPLETE, Zerodha's net
row quantity 0. Token 13156354 = exchange token 51392 (13156354 >> 8); NSE's contract file of 2026-10-16 (same
folder) lists 51392 as NIFTY 24000 CE, expiry 2026-10-27, lot 65.

Expected values come from the spec by hand: ADR-109 ("strategy BUY 65 NIFTY CE, Kite 130 -> not blocked, 65 outside;
... Kite 0 -> blocked"), REQ-060 AC-7 ("A broker position in no strategy and not recorded as standalone ... blocks no
strategy"). No database: the store is the injected fake of ``reconcile_attribution``'s three reads, the connection
a fake that answers the standalone read with no rows.
"""
from __future__ import annotations

import ast
import asyncio
import copy
import datetime
import inspect
import json
from decimal import Decimal
from pathlib import Path

import pytest
from ofo.engine import Instrument
from ofo.errors.templates import CATALOGUE
from ofo.instruments import Catalogue
from ofo.instruments.parser import zerodha_listed
from ofo.reconciliation.compare import MismatchKind
from ofo.timeutil import IST
from ofo_app import reconcile_attribution as ra
from ofo_app import route_reconciliation as rr
from ofo_app.execution_plan_store import PlanOrder, StoredPlan
from ofo_app.kite_replies import orders_from_reply
from ofo_app.strategy_store import StrategySummary

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "kite_replies"
TOKEN = 13156354
IID = f"NSE_FO:{TOKEN >> 8}"
KEY = ("NIFTY", Instrument.CE, Decimal("24000"), datetime.date(2026, 10, 27))
AT = datetime.datetime(2026, 10, 19, 10, 45, tzinfo=IST)  # after the 10:43:35 exit fill, before the close
SID = 9
USER = "user-1"


def clock() -> datetime.datetime:
    return AT


def _recorded(name: str) -> object:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"), parse_float=Decimal)["data"]


def listed() -> object:
    """NIFTY26OCT24000CE as NSE's 2026-10-16 contract file lists it (the real 2026-10-19 round trip's contract)."""
    return zerodha_listed(
        instrument_token=TOKEN, exchange_token=TOKEN >> 8, tradingsymbol="NIFTY26OCT24000CE", name="NIFTY",
        expiry=datetime.date(2026, 10, 27), strike=Decimal("24000"), tick_size=Decimal("0.05"), lot_size=65,
        instrument_type="CE", segment="NFO-OPT", exchange="NFO")


def _catalogue() -> Catalogue:
    cat = Catalogue()
    cat.load([listed()])
    return cat


class _Rows:
    def all(self) -> list:
        return []


class _Conn:
    """Answers the standalone read with no rows; any other statement fails the test (nothing else may run here)."""

    def __init__(self) -> None:
        self.statements: list[str] = []

    async def execute(self, statement, params=None):
        self.statements.append(str(statement))
        assert "reconciliation_standalone" in str(statement), str(statement)
        return _Rows()


def _plans(numbers: tuple[int, ...]) -> tuple[StoredPlan, ...]:
    """The real order rows of plans ``numbers`` as strategy 9's closed plans (fills as Kite reported them)."""
    out = []
    for row in orders_from_reply(_recorded("orders-2026-10-19-roundtrip")):
        number = int(row.tag[len(f"OFS{SID}V"):].split("L")[0])
        if number in numbers:
            order = PlanOrder(0, row.tag, IID, row.tradingsymbol, row.side.value, row.quantity, row.price,
                              row.filled_quantity)
            out.append(StoredPlan(SID, number, "ENTRY" if number == 1 else "EXIT", "closed", (order,), AT, AT,
                                  "filled" if number == 1 else "exited"))
    return tuple(out)


def _reader(plans: tuple[StoredPlan, ...], others: dict[int, tuple[StoredPlan, ...]] | None = None,
            ) -> ra.StoreReader:
    """Strategy 9 with ``plans``; ``others``: further strategies of the same user, by id, with their plans."""
    by_id = {SID: plans, **(others or {})}

    async def list_strategies(conn, user_ref):
        return [StrategySummary(sid, "NIFTY", "draft", AT, AT) for sid in sorted(by_id)]

    async def plans_for(conn, user_ref, strategy_id):
        return by_id[strategy_id]

    async def mismatches_for(conn, user_ref, strategy_id):
        return ()

    return ra.StoreReader(list_strategies, plans_for, mismatches_for)


@pytest.fixture(autouse=True)
def _test_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")  # the fake store reader is accepted only here


def _positions(quantity: int) -> object:
    data = copy.deepcopy(_recorded("positions-2026-10-19-roundtrip"))
    data["net"][0]["quantity"] = quantity
    data["net"][0]["average_price"] = data["net"][0]["buy_price"]  # a held row carries a price (the real buy, 7)
    return data


def _attribute(plans, positions, others=None, at=AT) -> tuple[ra.Attribution, object]:
    return asyncio.run(rr.attribute(_Conn(), USER, _catalogue(), positions, _recorded("orders-2026-10-19-roundtrip"),
                                    at=at, clock=lambda: at, reader=_reader(plans, others)))


def _run(plans, positions, others=None) -> ra.Attribution:
    return _attribute(plans, positions, others)[0]


def test_core_real_roundtrip_gives_no_mismatch():
    """Core (#380-2): plan 1 filled + plan 2 exited on the real replies, Zerodha's real net row 0 -> 0 mismatches,
    nothing blocked, nothing outside, nothing to store."""
    attribution = _run(_plans((1, 2)), _recorded("positions-2026-10-19-roundtrip"))
    assert attribution.report.mismatches == ()
    assert attribution.blocked == frozenset()
    assert dict(attribution.outside) == {}
    assert dict(attribution.raw_net) == {}
    assert rr.mismatch_rows(attribution, _catalogue()) == ()


def test_core_hand_exit_blocks_with_one_row():
    """Core (#380-2), ADR-109 "Kite 0 -> blocked": only plan 1 is the app's (the exit happened on Kite by hand), the
    real net is 0 -> strategy 9 blocked, exactly one row to store: expected 65, Zerodha 0, missing platform position,
    keyed by the contract's stored text."""
    attribution = _run(_plans((1,)), _recorded("positions-2026-10-19-roundtrip"))
    assert attribution.blocked == frozenset({"9"})
    rows = rr.mismatch_rows(attribution, _catalogue())
    assert rows == (rr.StoredRow(SID, IID, 65, 0, MismatchKind.MISSING_PLATFORM_POSITION),)


def test_brief_plus_65_on_an_exited_strategy_is_outside_not_blocked():
    """REQ-060 AC-7 / ADR-109 (2): the brief's "+65 on the strategy's contract" with plans 1 and 2 both stored leaves
    the strategy holding 0, so the 65 is in no strategy: outside, blocking nothing (reported as a brief conflict)."""
    attribution = _run(_plans((1, 2)), _positions(65))
    assert attribution.blocked == frozenset()
    assert dict(attribution.outside) == {KEY: 65}
    assert rr.mismatch_rows(attribution, _catalogue()) == ()


def test_surplus_while_holding_is_outside_and_shortfall_blocks():
    """ADR-109: strategy BUY 65 (plan 1 only), Kite 130 -> not blocked, 65 outside; Kite 0 -> blocked (above)."""
    attribution = _run(_plans((1,)), _positions(130))
    assert attribution.blocked == frozenset()
    assert dict(attribution.outside) == {KEY: 65}


def test_unreadable_positions_reply_is_refused_not_guessed():
    """Answer state "failed/ambiguous": a positions reply without ``net`` raises; nothing is decided."""
    with pytest.raises(ValueError, match="net"):
        _run(_plans((1,)), {"day": []})


def test_standalone_key_outside_the_catalogue_is_refused():
    """A stored standalone the catalogue cannot place is refused, never dropped (it would read as outside lots)."""
    with pytest.raises(ra.AttributionError, match="not in the catalogue"):
        rr.standalone_keys({"NSE_FO:1": 25}, _catalogue())
    assert rr.standalone_keys({IID: 25}, _catalogue()) == {KEY: 25}


def test_every_mismatch_kind_has_a_catalogue_template():
    """The code a route shows for each compare kind is a real catalogue template id."""
    assert set(rr.MISMATCH_CODES) == set(MismatchKind)
    assert all(code in CATALOGUE for code in rr.MISMATCH_CODES.values())


def test_reconciler_takes_no_net_or_verdict_from_its_caller():
    """#423 (finding caller-supplied-verdict-trusted): the routes' one call takes Zerodha's RAW replies and parses
    them itself; no parameter carries a net, held units, a verdict or a "reconciled" flag."""
    for fn in (rr.reconcile_account, rr.attribute):
        params = set(inspect.signature(fn).parameters)
        assert params & {"net", "broker_net", "zerodha_net", "zerodha_net_now", "held", "blocked", "reconciled",
                         "verdict", "attribution"} == set(), fn.__name__
    assert set(inspect.signature(rr.reconcile_account).parameters) == {
        "conn", "user_ref", "catalogue", "positions_reply", "order_rows", "at", "clock", "source"}


def _calls(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}


@pytest.mark.parametrize("route", ["execute.py", "execution_return.py"])
def test_both_routes_call_the_one_reconciler(route):
    """T3: both routes call ``route_reconciliation.reconcile_account`` and ``lock_user``, and neither keeps its own
    comparison (``strategy_blocked``, ``execution_return.reconcile``, the other-strategies query)."""
    path = ROOT / "backend" / "ofo_app" / "routes" / route
    calls = _calls(path)
    assert "rr.reconcile_account" in calls
    assert "rr.lock_user" in calls
    source = path.read_text(encoding="utf-8")
    for gone in ("strategy_blocked", "er.reconcile(", "_OTHER_STRATEGIES", "exit_is_clean"):
        assert gone not in source, (route, gone)


def test_the_parallel_reconciliation_code_is_deleted():
    """#380-2 step 1: the old comparison exists nowhere the product could call it again."""
    from ofo_app import execute_plan, execution_return  # noqa: PLC0415
    for module, gone in ((execute_plan, "strategy_blocked"), (execution_return, "reconcile"),
                         (execution_return, "ContractCheck"), (execution_return, "exit_is_clean"),
                         (execution_return, "unsettled_orders")):
        assert not hasattr(module, gone), (module.__name__, gone)


# ---- #380-2 step 1: the guards of the deleted parallel code, each held by the one reconciler -------------------------
# ``execute_plan.strategy_blocked`` and ``execution_return.reconcile`` / ``ContractCheck`` / ``exit_is_clean`` /
# ``unsettled_orders`` were deleted (no product caller after e35ce5c). Every case their tests pinned is pinned here on
# the one reconciler, with strategy 9's real plan 1 (BUY 65) and Zerodha's real positions row at another quantity.

@pytest.mark.parametrize(("zerodha", "blocked", "kind", "outside"), [
    (65, False, None, {}),  # Zerodha agrees
    (130, False, None, {KEY: 65}),  # units beyond the strategy: outside, blocking nothing (REQ-060 AC-7)
    (0, True, MismatchKind.MISSING_PLATFORM_POSITION, {}),  # the real flat row against a filled entry
    (64, True, MismatchKind.QUANTITY_MISMATCH, {}),  # fewer units at Zerodha
    (-65, True, MismatchKind.SIDE_MISMATCH, {}),  # the opposite side
    (-130, True, MismatchKind.SIDE_MISMATCH, {}),  # the opposite side beyond the strategy is never outside
])
def test_old_strategy_blocked_cases_hold_on_the_one_reconciler(zerodha, blocked, kind, outside):
    """Was ``strategy_blocked`` / ``er.reconcile``'s table: fewer or the wrong side blocks, more blocks nothing."""
    positions = _positions(zerodha) if zerodha else _recorded("positions-2026-10-19-roundtrip")
    attribution = _run(_plans((1,)), positions)
    assert (attribution.blocked == frozenset({"9"})) is blocked
    assert dict(attribution.outside) == outside
    assert {m.kind for m in attribution.report.mismatches if "9" in m.strategy_ids} == ({kind} if kind else set())


def _other_plan(status: str, filled: int | None, sid: int = 10) -> StoredPlan:
    """Another strategy's plan BUY 65 on the same contract; its tag is in no book row (open: pending)."""
    order = PlanOrder(0, f"OFS{sid}V1L0", IID, "NIFTY26OCT24000CE", "BUY", 65, Decimal("7"), filled)
    closed = status == "closed"
    return StoredPlan(sid, 1, "ENTRY", status, (order,), AT, AT if closed else None, "filled" if closed else None)


def _exited(plans, positions, others=None) -> bool:
    """The return route's own EXIT test on the one verdict (``routes.execution_return._exit_clean``)."""
    from types import SimpleNamespace  # noqa: PLC0415

    from ofo_app.routes import execution_return as route  # noqa: PLC0415
    attribution, read = _attribute(plans, positions, others)
    world = route._World(_catalogue(), "NIFTY", rr.Verdict(attribution, read, (), ()))
    return route._exit_clean(SimpleNamespace(strategy_id=SID), plans, world)


def test_old_exit_is_clean_cases_hold_on_the_route():
    """Was ``exit_is_clean``'s table: an EXIT reads ``exited`` only when the strategy holds 0 and Zerodha agrees
    (nothing outside); units another strategy holds by its stored fills do not stop it."""
    flat = _recorded("positions-2026-10-19-roundtrip")
    assert _exited(_plans((1, 2)), flat) is True  # the real round trip
    assert _exited(_plans((1, 2)), _positions(65)) is False  # Zerodha still +65 (outside lots)
    assert _exited(_plans((1,)), _positions(65)) is False  # the strategy still holds 65
    assert _exited(_plans((1, 2)), _positions(65), {10: (_other_plan("closed", 65),)}) is True  # strategy 10's 65


def test_exit_is_never_clean_while_another_strategys_plan_is_unsettled_on_the_contract():
    """Was ``exit_is_clean(..., undecidable)`` + ``unsettled_orders`` (review MAJOR 1): another strategy's OPEN plan
    on the contract makes Zerodha's units there unknown, so strategy 9's EXIT never reads ``exited``."""
    flat = _recorded("positions-2026-10-19-roundtrip")
    assert _exited(_plans((1, 2)), flat, {10: (_other_plan("open", None),)}) is False


# ---- T6 / ADR-083: an expired held leg settles; it is never a missing position -----------------------------------
#: The real contract's expiry day (2026-10-27): after the expiry-day settle time (15:39, F-33), the day after, and
#: before the close (still a tradable leg).
EXPIRY_EVENING = datetime.datetime(2026, 10, 27, 15, 45, tzinfo=IST)
DAY_AFTER = datetime.datetime(2026, 10, 28, 9, 30, tzinfo=IST)
EXPIRY_AFTERNOON = datetime.datetime(2026, 10, 27, 15, 0, tzinfo=IST)


@pytest.mark.parametrize("at", [EXPIRY_EVENING, DAY_AFTER])
def test_t6_an_expired_held_leg_gone_at_zerodha_settles_and_blocks_nothing(at):
    """ADR-083 (1): "reconciliation expects that leg gone from Zerodha's positions and does not raise a
    missing-position mismatch for it". Strategy 9 holds 65 by plan 1; after the expiry close Zerodha's real row is
    flat -> awaiting settlement (shown, never blocking), nothing to store, nothing outside."""
    attribution, _ = _attribute(_plans((1,)), _recorded("positions-2026-10-19-roundtrip"), at=at)
    assert attribution.blocked == frozenset()
    assert {(m.kind, m.strategy_ids) for m in attribution.report.mismatches} == {
        (MismatchKind.AWAITING_SETTLEMENT, ())}
    assert rr.mismatch_rows(attribution, _catalogue()) == ()
    assert dict(attribution.outside) == {}


def test_t6_before_the_expiry_close_a_flat_zerodha_is_still_a_missing_position():
    """The same flat row at 15:00 on the expiry day: the leg can still trade, so it is a blocking mismatch."""
    attribution, _ = _attribute(_plans((1,)), _recorded("positions-2026-10-19-roundtrip"), at=EXPIRY_AFTERNOON)
    assert attribution.blocked == frozenset({"9"})
    assert {m.kind for m in attribution.report.mismatches} == {MismatchKind.MISSING_PLATFORM_POSITION}
