"""#380 step 2.1: the stored reconciliation mismatch, its recorded resolution, the standalone quantity, and the
``unresolved_from_positions`` close reason (migration 0018).

Spec basis (quoted): REQ-060 AC-6 "While a mismatch is unresolved, new execution and adjustment execution are blocked
(Q199)."; REQ-060 (Q222, owner-confirmed 2026-09-29) "an agreeing reconciliation run does not unblock a strategy by
itself; the block lifts only through a recorded manual resolution"; REQ-060 AC-5 "Manual reconciliation is allowed,
explicit and audited (Q198)."; REQ-060 AC-7 "Positions the user left standalone (REQ-061 AC-2) are recorded with their
quantity and are not mismatches."; ADR-109 (4) "close/reconcile through a prepared basket, mark as requiring
attention, and Kite flat -> mark exited".

Real rows: ``tests/fixtures/kite_positions/positions-2026-10-16-one-ce.json`` (the owner's real position of
2026-10-16: NFO NIFTY26O1923650CE, instrument_token 12080386 = exchange token 47189, net quantity 65). The strategy
expects 65 (plan OFS<id>V1L0 BUY 65); the mismatch case is DERIVED from it: Zerodha's net 0 after a hand close in Kite
(ADR-111) -> expected 65, Zerodha 0. The agreeing comparison is the real reply itself (65 = 65).

Database tests need TEST_DATABASE_URL / TEST_ADMIN_DATABASE_URL and skip locally without them. Every test runs in a
rolled-back transaction.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from ofo_app import execution_plan_store as plans
from ofo_app import reconciliation_store as rs
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_execution_plan_store import INSUFFICIENT_PRIVILEGE, _new_strategy, _refused_sql, _Tx, _user

POSITIONS = (Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "kite_positions"
             / "positions-2026-10-16-one-ce.json")
REAL = json.loads(POSITIONS.read_text(encoding="utf-8"))["data"]["net"][0]
REAL_KEY = f"NFO-OPT:{REAL['instrument_token'] >> 8}"  # the app's instrument id of the real contract
HELD = REAL["quantity"]  # 65
REPORT = {"tradingsymbol": REAL["tradingsymbol"], "expected": HELD, "zerodha": 0, "kind": "quantity"}
GUARD_SQLSTATE = "OF018"
REAL_TOKEN = 47189  # instrument_token 12080386 >> 8 (orders-122104.json, the 2026-10-16 real order)
REAL_HELD = 65  # the real net quantity (positions-2026-10-16-one-ce.json)
CHECK_VIOLATION = "23514"
UNIQUE_VIOLATION = "23505"


async def _refused(code: str, awaitable) -> None:
    with pytest.raises(rs.ReconciliationStoreError) as err:
        await awaitable
    assert err.value.code == code, err.value


async def _mismatch(tx, *, expected: int = HELD, zerodha: int = 0, key: str = REAL_KEY, strategy_id=None) -> int:
    return await rs.record_mismatch(tx.conn, tx.user, strategy_id or tx.strategy_id, contract_key=key,
                                    expected_units=expected, zerodha_units=zerodha, report=REPORT,
                                    source="next_day_resolution")


# ---------------------------------------------------------------------------------------------------------------
# Core proof
# ---------------------------------------------------------------------------------------------------------------


async def test_core_ac6_a_stored_mismatch_blocks_until_a_recorded_resolution(app_engine):
    """AC-6 / Q222: expected 65, Zerodha 0 on NIFTY26O1923650CE -> blocked; the agreeing comparison (the real 65 = 65
    reply) is refused as a mismatch and the strategy stays blocked; Kite flat -> mark exited lifts it; both rows are
    kept with the actor and the database clock (AC-5)."""
    async with _Tx(app_engine) as tx:
        assert REAL["instrument_token"] >> 8 == REAL_TOKEN and REAL["quantity"] == REAL_HELD
        assert await rs.is_blocked(tx.conn, tx.user, tx.strategy_id) is False
        mid = await _mismatch(tx)
        assert await rs.is_blocked(tx.conn, tx.user, tx.strategy_id) is True
        await _refused(rs.BAD_MISMATCH, _mismatch(tx, expected=HELD, zerodha=REAL["quantity"]))
        assert await rs.is_blocked(tx.conn, tx.user, tx.strategy_id) is True
        await rs.record_resolution(tx.conn, tx.user, tx.strategy_id, mid, action="kite_flat_marked_exited",
                                   note="closed by hand in Kite", zerodha_net_now=0)
        assert await rs.is_blocked(tx.conn, tx.user, tx.strategy_id) is False
        (stored,) = await rs.mismatches_for(tx.conn, tx.user, tx.strategy_id)
        assert (stored.id, stored.contract_key, stored.expected_units, stored.zerodha_units, stored.source) == (
            mid, "NFO-OPT:47189", 65, 0, "next_day_resolution")
        assert dict(stored.report) == REPORT
        assert stored.resolution is not None
        assert (stored.resolution.action, stored.resolution.actor, stored.resolution.note) == (
            "kite_flat_marked_exited", tx.user, "closed by hand in Kite")
        assert stored.resolution.resolved_at >= stored.detected_at


async def test_ac6_answer_states_none_unresolved_two_with_one_resolved(app_engine):
    """AC-6: two mismatches, one settled -> still blocked; the other only marked "requiring attention" -> still
    blocked (a mark settles nothing, ADR-018 Q198 / Q222); settled after the mark -> not blocked."""
    async with _Tx(app_engine) as tx:
        first = await _mismatch(tx)
        second = await _mismatch(tx, expected=HELD, zerodha=30)
        await rs.record_resolution(tx.conn, tx.user, tx.strategy_id, first, action="marked_requiring_attention")
        assert await rs.is_blocked(tx.conn, tx.user, tx.strategy_id) is True
        await rs.record_resolution(tx.conn, tx.user, tx.strategy_id, second, action="reconciled_by_basket")
        assert await rs.is_blocked(tx.conn, tx.user, tx.strategy_id) is True
        await rs.record_resolution(tx.conn, tx.user, tx.strategy_id, first, action="reconciled_by_basket")
        assert await rs.is_blocked(tx.conn, tx.user, tx.strategy_id) is False
        stored = await rs.mismatches_for(tx.conn, tx.user, tx.strategy_id)
        assert [[r.action for r in m.resolutions] for m in stored] == [
            ["marked_requiring_attention", "reconciled_by_basket"], ["reconciled_by_basket"]]
        assert [m.resolution.action for m in stored] == ["reconciled_by_basket", "reconciled_by_basket"]


async def test_ac6_requiring_attention_alone_never_lifts_the_block(app_engine):
    """Design 2026-10-19 (REQ-060, ADR-018 Q198 "no casual 'ignore'"): the real 2026-10-16 shape (expected 65,
    Zerodha 0) marked "requiring attention" stays blocked; the mark is kept for the audit; a second mark is
    already_resolved; the mismatch reads as unresolved (no settling resolution)."""
    async with _Tx(app_engine) as tx:
        mid = await _mismatch(tx)
        await rs.record_resolution(tx.conn, tx.user, tx.strategy_id, mid, action="marked_requiring_attention",
                                   note="will check in Kite")
        assert await rs.is_blocked(tx.conn, tx.user, tx.strategy_id) is True
        await _refused(rs.ALREADY_RESOLVED, rs.record_resolution(tx.conn, tx.user, tx.strategy_id, mid,
                                                                 action="marked_requiring_attention"))
        (stored,) = await rs.mismatches_for(tx.conn, tx.user, tx.strategy_id)
        assert stored.resolution is None
        assert [(r.action, r.actor, r.note) for r in stored.resolutions] == [
            ("marked_requiring_attention", tx.user, "will check in Kite")]
        assert await rs.is_blocked(tx.conn, tx.user, tx.strategy_id) is True


async def test_ac6_a_block_is_per_strategy(app_engine):
    """AC-7 "A mismatch blocks only the strategy whose contract quantity disagrees": a second strategy of the same user
    is not blocked by the first one's mismatch."""
    async with _Tx(app_engine) as tx:
        other = await _new_strategy(tx.conn, tx.user, catalogue=False)
        await _mismatch(tx)
        assert await rs.is_blocked(tx.conn, tx.user, other) is False


# ---------------------------------------------------------------------------------------------------------------
# Resolutions: closed list, ownership, once
# ---------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("action", [*rs.RESERVED_ACTIONS, "", "KITE_FLAT_MARKED_EXITED", "reconciled_by_basket ",
                                    "adopt", "resolved", None, 1, True])
async def test_ac5_an_action_outside_the_closed_list_is_refused(app_engine, action):
    """AC-5 / ADR-109 (4): only the three first actions are accepted; reserved, re-cased, padded, other words and
    non-text are refused, and the strategy stays blocked."""
    async with _Tx(app_engine) as tx:
        mid = await _mismatch(tx)
        await _refused(rs.BAD_RESOLUTION, rs.record_resolution(tx.conn, tx.user, tx.strategy_id, mid, action=action))
        assert await rs.is_blocked(tx.conn, tx.user, tx.strategy_id) is True


async def test_ac5_a_second_resolution_and_a_foreign_mismatch_are_refused(app_engine):
    """AC-5: a second resolution of one mismatch -> already_resolved; another user's strategy, a mismatch of another
    strategy, and an unknown id -> not_found."""
    async with _Tx(app_engine) as tx:
        mid = await _mismatch(tx)
        await rs.record_resolution(tx.conn, tx.user, tx.strategy_id, mid, action="reconciled_by_basket")
        for action, net in (("reconciled_by_basket", None), ("kite_flat_marked_exited", 0),
                            ("marked_requiring_attention", None)):
            await _refused(rs.ALREADY_RESOLVED, rs.record_resolution(tx.conn, tx.user, tx.strategy_id, mid,
                                                                     action=action, zerodha_net_now=net))
        other = await _new_strategy(tx.conn, tx.user, catalogue=False)
        foreign = await _mismatch(tx, strategy_id=other)
        await _refused(rs.NOT_FOUND, rs.record_resolution(tx.conn, tx.user, tx.strategy_id, foreign,
                                                          action="reconciled_by_basket"))
        await _refused(rs.NOT_FOUND, rs.record_resolution(tx.conn, _user(), other, foreign,
                                                          action="reconciled_by_basket"))
        await _refused(rs.NOT_FOUND, rs.is_blocked(tx.conn, _user(), other))
        await _refused(rs.NOT_FOUND, rs.record_resolution(tx.conn, tx.user, other, foreign + 1000,
                                                          action="reconciled_by_basket"))
        assert await rs.is_blocked(tx.conn, tx.user, other) is True


async def test_ac5_kite_flat_needs_zerodha_flat_now_not_the_stored_net(app_engine):
    """ADR-109 (4) "Kite flat -> mark exited" checks the CURRENT net the route read for this action, never the
    stored one. Real shape: the 2026-10-16 position (expected 65). Stored Zerodha 0 but Kite shows the 65 again now
    -> refused; no current net -> refused; a malformed one -> refused. Stored 30 (a partial hand close) and Kite
    now 0 -> accepted, block lifted."""
    async with _Tx(app_engine) as tx:
        stale = await _mismatch(tx, zerodha=0)
        for net in (REAL["quantity"], None, -65, True, 0.0, "0", 1_000_001):
            await _refused(rs.BAD_RESOLUTION, rs.record_resolution(tx.conn, tx.user, tx.strategy_id, stale,
                                                                   action="kite_flat_marked_exited",
                                                                   zerodha_net_now=net))
        assert await rs.is_blocked(tx.conn, tx.user, tx.strategy_id) is True
        await rs.record_resolution(tx.conn, tx.user, tx.strategy_id, stale, action="reconciled_by_basket")
        partial = await _mismatch(tx, zerodha=30)
        await rs.record_resolution(tx.conn, tx.user, tx.strategy_id, partial, action="kite_flat_marked_exited",
                                   zerodha_net_now=0)
        assert await rs.is_blocked(tx.conn, tx.user, tx.strategy_id) is False


async def test_q224_a_shared_contract_cannot_be_settled_for_one_holder(app_engine):
    """REQ-060 Q224 ("a contract held by more than one strategy that disagrees with Zerodha blocks every holder and
    refuses guess-based fixes"): two strategies of one user both mismatch on NFO-OPT:47189 (65 expected each, Zerodha
    65 in total -> each sees its own shortfall); a basket or Kite-flat settle on either is refused, both stay blocked;
    the attention mark is still recorded. A different contract of the other strategy is not shared; another user's
    mismatch on the same contract is not shared either."""
    async with _Tx(app_engine) as tx:
        other = await _new_strategy(tx.conn, tx.user, catalogue=False)
        mine = await _mismatch(tx, zerodha=0)
        theirs = await _mismatch(tx, zerodha=0, strategy_id=other)
        for sid, mid in ((tx.strategy_id, mine), (other, theirs)):
            await _refused(rs.BAD_RESOLUTION, rs.record_resolution(tx.conn, tx.user, sid, mid,
                                                                   action="reconciled_by_basket"))
            await _refused(rs.BAD_RESOLUTION, rs.record_resolution(tx.conn, tx.user, sid, mid,
                                                                   action="kite_flat_marked_exited",
                                                                   zerodha_net_now=0))
            await rs.record_resolution(tx.conn, tx.user, sid, mid, action="marked_requiring_attention")
            assert await rs.is_blocked(tx.conn, tx.user, sid) is True
        elsewhere = await _mismatch(tx, key="NFO-OPT:47190")
        await rs.record_resolution(tx.conn, tx.user, tx.strategy_id, elsewhere, action="reconciled_by_basket")
    async with _Tx(app_engine) as tx:
        stranger = _user()
        foreign = await _new_strategy(tx.conn, stranger, catalogue=False)
        await rs.record_mismatch(tx.conn, stranger, foreign, contract_key=REAL_KEY, expected_units=HELD,
                                 zerodha_units=0, report=REPORT, source="app_start")
        mid = await _mismatch(tx)
        await rs.record_resolution(tx.conn, tx.user, tx.strategy_id, mid, action="reconciled_by_basket")
        assert await rs.is_blocked(tx.conn, tx.user, tx.strategy_id) is False
        assert await rs.is_blocked(tx.conn, stranger, foreign) is True


async def test_ac6_the_same_unresolved_mismatch_seen_again_is_one_row(app_engine):
    """The same comparison (65 vs 0 on NFO-OPT:47189) from two trigger runs returns the stored id, not a second row;
    a different Zerodha net is a new row; once settled, the same comparison seen again is a new mismatch (blocked
    again)."""
    async with _Tx(app_engine) as tx:
        first = await _mismatch(tx)
        again = await rs.record_mismatch(tx.conn, tx.user, tx.strategy_id, contract_key=REAL_KEY, expected_units=HELD,
                                         zerodha_units=0, report={"run": 2}, source="periodic")
        assert again == first
        assert len(await rs.mismatches_for(tx.conn, tx.user, tx.strategy_id)) == 1
        partial = await _mismatch(tx, zerodha=30)
        assert partial != first
        await rs.record_resolution(tx.conn, tx.user, tx.strategy_id, first, action="marked_requiring_attention")
        assert await _mismatch(tx) == first  # a mark settles nothing: still the same unresolved mismatch
        await rs.record_resolution(tx.conn, tx.user, tx.strategy_id, first, action="kite_flat_marked_exited",
                                   zerodha_net_now=0)
        later = await _mismatch(tx)
        assert [m.id for m in await rs.mismatches_for(tx.conn, tx.user, tx.strategy_id)] == [first, partial, later]


async def test_ac6_a_report_over_the_cap_as_stored_is_bad_mismatch_not_a_database_error(app_engine):
    """The CHECK measures jsonb's own text (", " and ": " separators): 6,000 small keys are about 60 KB compact but
    about 72 KB as stored -> bad_mismatch, and the transaction stays usable (no aborted CHECK violation)."""
    report = {f"k{i:04d}": 0 for i in range(6000)}
    compact = len(json.dumps(report, separators=(",", ":")))
    assert compact < rs.MAX_REPORT_BYTES
    async with _Tx(app_engine) as tx:
        stored_size = (await tx.conn.execute(text("SELECT octet_length(CAST(:r AS jsonb)::text)"),
                                             {"r": json.dumps(report)})).scalar_one()
        assert stored_size > rs.MAX_REPORT_BYTES
        await _refused(rs.BAD_MISMATCH, rs.record_mismatch(tx.conn, tx.user, tx.strategy_id, contract_key=REAL_KEY,
                                                           expected_units=HELD, zerodha_units=0, report=report,
                                                           source="app_start"))
        assert await rs.is_blocked(tx.conn, tx.user, tx.strategy_id) is False


@pytest.mark.parametrize("note", ["", " padded", "x" * 501, 5])
async def test_ac5_a_bad_note_is_refused(app_engine, note):
    """AC-5: a note is None or trimmed text of 1..500 characters."""
    async with _Tx(app_engine) as tx:
        mid = await _mismatch(tx)
        await _refused(rs.BAD_RESOLUTION, rs.record_resolution(tx.conn, tx.user, tx.strategy_id, mid,
                                                               action="reconciled_by_basket", note=note))


# ---------------------------------------------------------------------------------------------------------------
# Mismatch input domain
# ---------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("field, value", [
    ("contract_key", "NIFTY26O1923650CE"), ("contract_key", ""), ("contract_key", "nfo-opt:47189"),
    ("contract_key", "NFO-OPT:047189"), ("contract_key", "NFO-OPT:47189 "), ("contract_key", 47189),
    ("expected_units", True), ("expected_units", 65.0), ("expected_units", 1_000_001), ("zerodha_units", -1_000_001),
    ("zerodha_units", "0"), ("source", "manual"), ("source", None), ("report", [1]), ("report", {"x": Decimal("1")}),
    ("report", {"x": float("nan")}), ("report", {"x": "y" * 65_536}),
])
async def test_ac6_a_malformed_mismatch_is_refused(app_engine, field, value):
    """AC-6: every field is checked; the block cannot be created from a malformed record either."""
    async with _Tx(app_engine) as tx:
        fields = {"contract_key": REAL_KEY, "expected_units": HELD, "zerodha_units": 0, "report": REPORT,
                      "source": "app_start"}
        fields[field] = value
        await _refused(rs.BAD_MISMATCH, rs.record_mismatch(tx.conn, tx.user, tx.strategy_id, **fields))
        assert await rs.is_blocked(tx.conn, tx.user, tx.strategy_id) is False


async def test_ac6_another_users_strategy_cannot_get_a_mismatch(app_engine):
    """AC-6: a mismatch is recorded only for the acting user's own strategy."""
    async with _Tx(app_engine) as tx:
        await _refused(rs.NOT_FOUND, rs.record_mismatch(tx.conn, _user(), tx.strategy_id, contract_key=REAL_KEY,
                                                        expected_units=HELD, zerodha_units=0, report=REPORT,
                                                        source="app_start"))


# ---------------------------------------------------------------------------------------------------------------
# The database itself
# ---------------------------------------------------------------------------------------------------------------


async def test_ac6_the_app_role_cannot_change_or_delete_a_mismatch_or_resolution(app_engine):
    """AC-6 / ADR-048: no UPDATE, DELETE or clock-column INSERT for the application role on the block's records."""
    async with _Tx(app_engine) as tx:
        mid = await _mismatch(tx)
        await rs.record_resolution(tx.conn, tx.user, tx.strategy_id, mid, action="marked_requiring_attention")
        for sql in ("UPDATE public.reconciliation_mismatches SET zerodha_units = 65 WHERE id = :m",
                    "DELETE FROM public.reconciliation_mismatches WHERE id = :m",
                    "DELETE FROM public.reconciliation_resolutions WHERE mismatch_id = :m",
                    "UPDATE public.reconciliation_resolutions SET action = 'reconciled_by_basket' "
                    "WHERE mismatch_id = :m",
                    "INSERT INTO public.reconciliation_mismatches (strategy_id, contract_key, expected_units, "
                    "zerodha_units, report, source, detected_at) SELECT strategy_id, contract_key, 1, 2, report, "
                    "source, now() - interval '1 day' FROM public.reconciliation_mismatches WHERE id = :m"):
            await _refused_sql(tx.conn, sql, INSUFFICIENT_PRIVILEGE, {"m": mid})


async def test_ac6_the_guards_refuse_even_the_owner_and_stamp_the_clock(admin_engine):
    """AC-6: the guard triggers (not only the grants) refuse UPDATE / DELETE for the owner; a forged detected_at is
    replaced by the database clock; an agreeing pair and a second resolution are refused by the database too."""
    async with _Tx(admin_engine) as tx:
        mid = await _mismatch(tx)
        await rs.record_resolution(tx.conn, tx.user, tx.strategy_id, mid, action="marked_requiring_attention")
        for sql in ("UPDATE public.reconciliation_mismatches SET zerodha_units = 65 WHERE id = :m",
                    "DELETE FROM public.reconciliation_mismatches WHERE id = :m",
                    "DELETE FROM public.reconciliation_resolutions WHERE mismatch_id = :m",
                    "UPDATE public.reconciliation_resolutions SET action = 'reconciled_by_basket' "
                    "WHERE mismatch_id = :m"):
            await _refused_sql(tx.conn, sql, GUARD_SQLSTATE, {"m": mid})
        await _refused_sql(tx.conn, "INSERT INTO public.reconciliation_resolutions (mismatch_id, action, actor) "
                                    "VALUES (:m, 'marked_requiring_attention', 'x')", UNIQUE_VIOLATION, {"m": mid})
        await tx.conn.execute(text("INSERT INTO public.reconciliation_resolutions (mismatch_id, action, actor) "
                                   "VALUES (:m, 'reconciled_by_basket', 'x')"), {"m": mid})
        for action in ("kite_flat_marked_exited", "attached_outside", "reconciled_by_basket"):
            await _refused_sql(tx.conn, "INSERT INTO public.reconciliation_resolutions (mismatch_id, action, actor) "
                                        "VALUES (:m, :a, 'x')", UNIQUE_VIOLATION, {"m": mid, "a": action})
        await _refused_sql(tx.conn, "INSERT INTO public.reconciliation_mismatches (strategy_id, contract_key, "
                                    "expected_units, zerodha_units, report, source) VALUES (:s, 'NFO-OPT:47189', 65, "
                                    "65, '{}', 'app_start')", CHECK_VIOLATION, {"s": tx.strategy_id})
        forged = (await tx.conn.execute(text(
            "INSERT INTO public.reconciliation_mismatches (strategy_id, contract_key, expected_units, zerodha_units, "
            "report, source, detected_at) VALUES (:s, 'NFO-OPT:47189', 65, 0, '{}', 'app_start', "
            "'2000-01-01T00:00:00Z') RETURNING detected_at > now() - interval '1 hour'"), {"s": tx.strategy_id}))
        assert forged.scalar_one() is True


async def test_ac7_standalone_absent_present_zero_and_per_user(app_engine, admin_engine):
    """AC-7: absent -> no key; recorded 25 -> 25 (the spec's "standalone x 25"); changed to 0 -> a stored 0, still
    present; another user's map is separate; a delete is refused for the app role and by the guard."""
    async with _Tx(app_engine) as tx:
        assert await rs.standalone_for(tx.conn, tx.user) == {}
        await rs.set_standalone(tx.conn, tx.user, REAL_KEY, 25)
        assert await rs.standalone_for(tx.conn, tx.user) == {"NFO-OPT:47189": 25}
        await rs.set_standalone(tx.conn, tx.user, REAL_KEY, 0)
        assert await rs.standalone_for(tx.conn, tx.user) == {"NFO-OPT:47189": 0}
        assert await rs.standalone_for(tx.conn, _user()) == {}
        await _refused(rs.BAD_STANDALONE, rs.set_standalone(tx.conn, tx.user, "NIFTY26O1923650CE", 1))
        for bad in (True, 1.5, 1_000_001, "25"):
            await _refused(rs.BAD_STANDALONE, rs.set_standalone(tx.conn, tx.user, REAL_KEY, bad))
        await _refused_sql(tx.conn, "DELETE FROM public.reconciliation_standalone WHERE user_ref = :u",
                           INSUFFICIENT_PRIVILEGE, {"u": tx.user})
        await _refused_sql(tx.conn, "UPDATE public.reconciliation_standalone SET user_ref = 'x' WHERE user_ref = :u",
                           INSUFFICIENT_PRIVILEGE, {"u": tx.user})
    async with _Tx(admin_engine) as owner:
        await rs.set_standalone(owner.conn, owner.user, REAL_KEY, 25)
        for sql in ("DELETE FROM public.reconciliation_standalone WHERE user_ref = :u",
                    "UPDATE public.reconciliation_standalone SET contract_key = 'NFO-OPT:1' WHERE user_ref = :u"):
            await _refused_sql(owner.conn, sql, GUARD_SQLSTATE, {"u": owner.user})


# ---------------------------------------------------------------------------------------------------------------
# The close reason
# ---------------------------------------------------------------------------------------------------------------


async def test_ac6_unresolved_from_positions_closes_the_plan_with_zero_and_frees_the_next_plan(app_engine):
    """AC-6 (#380 step 2.1): an open plan closes ``unresolved_from_positions`` with 0 stored per order, the next plan
    number is no longer refused (one-open-plan stops blocking) and the mismatch record carries the block; the reason
    takes no fills."""
    async with _Tx(app_engine) as tx:
        plan = await tx.enter("ENTRY", "BUY", "5.45")
        await _refused(rs.BAD_MISMATCH, _mismatch(tx, expected=0, zerodha=0))
        await _mismatch(tx, expected=0, zerodha=HELD)
        with pytest.raises(plans.PlanStoreError) as err:
            await plans.close_plan(tx.conn, tx.user, tx.strategy_id, plan.plan_number,
                                   reason="unresolved_from_positions", filled={plan.orders[0].tag: 0})
        assert err.value.code == plans.BAD_PLAN
        closed = await plans.close_plan(tx.conn, tx.user, tx.strategy_id, plan.plan_number,
                                        reason="unresolved_from_positions")
        assert (closed.status, closed.close_reason, [o.filled_quantity for o in closed.orders]) == (
            "closed", "unresolved_from_positions", [0])
        assert await plans.next_plan_number(tx.conn, tx.user, tx.strategy_id) == plan.plan_number + 1
        assert await rs.is_blocked(tx.conn, tx.user, tx.strategy_id) is True


async def test_ac6_unresolved_from_positions_needs_an_unresolved_mismatch_of_the_strategy(app_engine):
    """An ENTRY plan closed ``unresolved_from_positions`` with no mismatch would free the plan slot and leave the real
    lots unaccounted: refused (plan stays open) when the strategy has no mismatch, when its only mismatch is settled,
    and when only ANOTHER strategy has one; a mismatch marked "requiring attention" still counts (still blocked)."""
    async with _Tx(app_engine) as tx:
        plan = await tx.enter("ENTRY", "BUY", "5.45")

        async def refused() -> None:
            with pytest.raises(plans.PlanStoreError) as err:
                await plans.close_plan(tx.conn, tx.user, tx.strategy_id, plan.plan_number,
                                       reason="unresolved_from_positions")
            assert err.value.code == plans.BAD_PLAN
            assert [p.status for p in await plans.plans_for(tx.conn, tx.user, tx.strategy_id)] == ["open"]

        await refused()
        other = await _new_strategy(tx.conn, tx.user, catalogue=False)
        await _mismatch(tx, expected=0, zerodha=HELD, strategy_id=other, key="NFO-OPT:47190")
        await refused()
        settled = await _mismatch(tx, expected=0, zerodha=HELD)
        await rs.record_resolution(tx.conn, tx.user, tx.strategy_id, settled, action="reconciled_by_basket")
        await refused()
        marked = await _mismatch(tx, expected=0, zerodha=30)
        await rs.record_resolution(tx.conn, tx.user, tx.strategy_id, marked, action="marked_requiring_attention")
        closed = await plans.close_plan(tx.conn, tx.user, tx.strategy_id, plan.plan_number,
                                        reason="unresolved_from_positions")
        assert closed.close_reason == "unresolved_from_positions"
        assert await rs.is_blocked(tx.conn, tx.user, tx.strategy_id) is True


# ---------------------------------------------------------------------------------------------------------------
# Migration round trip
# ---------------------------------------------------------------------------------------------------------------

_LEFTOVERS = text(
    "SELECT (SELECT count(*) FROM pg_class WHERE relname LIKE 'reconciliation\\_%') + "
    "(SELECT count(*) FROM pg_proc WHERE proname LIKE 'reconciliation\\_%') + "
    "(SELECT count(*) FROM pg_trigger WHERE tgname LIKE 'reconciliation\\_%') + "
    "(SELECT count(*) FROM information_schema.role_table_grants WHERE table_name LIKE 'reconciliation\\_%')")


async def test_ac6_downgrade_leaves_nothing_and_upgrade_restores_the_store(admin_engine):
    """AC-6: 0018 down -> no table, function, trigger or grant of the store is left and the old close-reason CHECK
    refuses the new reason; up -> the allow-list post check passes (inside upgrade) and the store works. Rolled
    back."""
    from _migration_replay import round_trip_sql  # noqa: PLC0415

    own_down, own_up, down, up = round_trip_sql("0018_reconciliation_store.py")
    assert "'pre'" in own_up[0] and "'post'" in own_up[-1] and "'post'" in own_down[-1]
    async with admin_engine.connect() as conn:
        trans = await conn.begin()
        try:
            for sql in down:
                await conn.execute(text(sql))
            assert (await conn.execute(_LEFTOVERS)).scalar_one() == 0
            check = (await conn.execute(text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = "
                "'execution_plans_close_reason_check'"))).scalar_one()
            assert "unresolved_from_positions" not in check and "nothing_placed" in check
            for sql in up:
                await conn.execute(text(sql))
            assert (await conn.execute(_LEFTOVERS)).scalar_one() > 0
        finally:
            await trans.rollback()


async def test_ac6_downgrade_is_refused_while_a_mismatch_is_stored(admin_engine):
    """AC-5: mismatches are the audit of a block: the downgrade refuses once one is stored."""
    from _migration_replay import recorded  # noqa: PLC0415

    own_down = recorded("0018_reconciliation_store.py", "downgrade")
    async with _Tx(admin_engine) as tx:
        await _mismatch(tx)
        with pytest.raises(DBAPIError, match="reconciliation records are stored"):
            async with tx.conn.begin_nested():
                await tx.conn.execute(text(own_down[0]))


def test_every_stored_close_reason_is_a_plan_state_the_return_route_can_answer():
    """Class check (#380-1 review finding 4): the return route answers a closed plan with its stored close reason, so
    every reason the plan store accepts (``unresolved_from_positions`` included) must be in the route's PlanState."""
    from typing import get_args  # noqa: PLC0415

    from ofo_app.routes.execution_return import PlanState  # noqa: PLC0415

    assert set(plans.CLOSE_REASONS) <= set(get_args(PlanState))
