"""PostgreSQL store for reconciliation mismatches, their resolutions and standalone quantities (#380 step 2.1).

Spec basis: REQ-060 AC-6 "While a mismatch is unresolved, new execution and adjustment execution are blocked (Q199).";
Q222 (REQ-060, owner-confirmed 2026-09-29) "an agreeing reconciliation run does not unblock a strategy by itself; the
block lifts only through a recorded manual resolution"; REQ-060 AC-5 "Manual reconciliation is allowed, explicit and
audited (Q198)."; REQ-060 AC-7 (standalone positions "are recorded with their quantity"); ADR-109 (4) (the first
reconcile screen's three actions). Schema: migration 0019_reconciliation_store.

Copy from: none - modelled on ``execution_plan_store`` (strategy row lock via ``strategy_store``, error style).

- record_mismatch: stores one mismatch of the user's strategy on one contract. An agreeing pair (expected = Zerodha)
  is refused: it is not a mismatch, and storing it can never lift a block. The same unresolved mismatch seen again
  (same strategy, contract, expected and Zerodha net) returns the stored id instead of a second row.
- record_resolution: the ONLY way a block lifts, and only a SETTLING action lifts it (``SETTLING``: a prepared basket
  that reconciled the position, or Zerodha flat NOW). ``marked_requiring_attention`` is recorded (audit) but settles
  nothing: ADR-018 Q198 "no casual 'ignore'", Q222 the block lifts only through a recorded resolution that settles it.
  ``kite_flat_marked_exited`` needs the caller's CURRENT Zerodha net for that contract (``zerodha_net_now``, read
  from the positions reply the route parses, #380 step 2.2) to be 0 - never the stored net, which is the past. A
  contract with an unresolved mismatch on another strategy of the same user is shared (Q224): both settling actions
  are refused and every holder stays blocked (the user trades in Kite and re-runs). The actor is the acting user
  (never a caller-supplied name). Both rows are insert-only and stamped by the database clock.
- is_blocked: reads the rows itself (no caller-supplied verdict): any mismatch of the strategy without a settling
  resolution.
- standalone_for / set_standalone: the user's standalone units per contract (absent = no row; 0 is a stored value).
Transaction control (commit) stays with the caller. Another user's strategy answers exactly like a missing one.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from ofo.strategy.definition import MAX_UNITS
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from ofo_app import strategy_store

NOT_FOUND = "not_found"
BAD_MISMATCH = "bad_mismatch"
BAD_RESOLUTION = "bad_resolution"
ALREADY_RESOLVED = "already_resolved"
BAD_STANDALONE = "bad_standalone"

#: Trigger sources (ofo.reconciliation.triggers.Trigger names, lower case) plus the next-day plan resolution.
SOURCES = ("after_execution", "after_reconnect", "app_start", "app_resume", "periodic", "broker_position_event",
           "order_event", "next_day_resolution")
#: ADR-109 (4): the first reconcile screen's three actions - the only ones accepted today.
ACTIONS = ("reconciled_by_basket", "marked_requiring_attention", "kite_flat_marked_exited")
#: ADR-109 (2) attach/detach outside lots: the database already accepts them; the store refuses them until that release.
RESERVED_ACTIONS = ("attached_outside", "detached_outside")
KITE_FLAT = "kite_flat_marked_exited"
BASKET = "reconciled_by_basket"
ATTENTION = "marked_requiring_attention"
#: The only actions that settle a mismatch and so lift its block (REQ-060 design 2026-10-19, ADR-018 Q198, Q222).
SETTLING = (BASKET, KITE_FLAT)
MAX_REPORT_BYTES = 65_536
MAX_TEXT = 500
_CONTRACT_KEY = re.compile(r"[A-Z][A-Z0-9_-]{0,15}:[1-9][0-9]{0,18}")
_UNIQUE_VIOLATION = "23505"
#: migration 0019: one row per (mismatch, action), and one settling row per mismatch.
_RESOLUTION_KEYS = ("reconciliation_resolutions_pkey", "reconciliation_resolutions_one_settling")


class ReconciliationStoreError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class StoredResolution:
    action: str
    actor: str
    note: str | None
    resolved_at: datetime


@dataclass(frozen=True)
class StoredMismatch:
    id: int
    strategy_id: int
    contract_key: str
    expected_units: int
    zerodha_units: int
    report: Mapping[str, Any]
    source: str
    detected_at: datetime
    resolutions: tuple[StoredResolution, ...]

    @property
    def resolution(self) -> StoredResolution | None:
        """The settling resolution (the one that lifted the block), or None while the mismatch is unresolved."""
        return next((r for r in self.resolutions if r.action in SETTLING), None)


def _contract_key(value: Any, code: str) -> str:
    if not isinstance(value, str) or _CONTRACT_KEY.fullmatch(value) is None:
        raise ReconciliationStoreError(code, f"contract key must be <segment>:<exchange token>, got {value!r}")
    return value


def _units(value: Any, what: str, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not -MAX_UNITS <= value <= MAX_UNITS:
        raise ReconciliationStoreError(code, f"{what} must be an integer from -{MAX_UNITS} to {MAX_UNITS}, "
                                             f"got {value!r}")
    return value


def _report(value: Any) -> str:
    """Plain-JSON check plus a first, cheap size bound; ``_report_fits`` then measures the database's own text."""
    if not isinstance(value, Mapping):
        raise ReconciliationStoreError(BAD_MISMATCH, f"report must be a mapping, got {type(value).__name__}")
    try:
        encoded = json.dumps(dict(value), sort_keys=True, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ReconciliationStoreError(BAD_MISMATCH, f"report is not plain JSON: {exc}") from exc
    if len(encoded.encode("utf-8")) > MAX_REPORT_BYTES:
        raise ReconciliationStoreError(BAD_MISMATCH, f"report is above {MAX_REPORT_BYTES} bytes")
    return encoded


async def _report_fits(conn: Any, encoded: str) -> None:
    """The CHECK measures ``octet_length(report::text)`` (jsonb's own text: ", " and ": " separators, numbers
    re-printed), which can exceed the compact encoding; measure that very text, so a near-cap report is
    ``bad_mismatch`` and never a raw CHECK violation that aborts the caller's transaction."""
    size = int((await conn.execute(_REPORT_SIZE, {"r": encoded})).scalar_one())
    if size > MAX_REPORT_BYTES:
        raise ReconciliationStoreError(BAD_MISMATCH, f"report is {size} bytes as stored, above {MAX_REPORT_BYTES}")


def _note(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or value != value.strip() or len(value) > MAX_TEXT:
        raise ReconciliationStoreError(BAD_RESOLUTION, f"note must be None or trimmed text of 1..{MAX_TEXT} "
                                                       f"characters, got {value!r}")
    return value


def _user_ref(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_TEXT:
        raise ReconciliationStoreError(NOT_FOUND, f"user {value!r}")
    return value


async def _lock(conn: Any, user_ref: str, strategy_id: Any) -> int:
    """Row-locks the user's strategy until the transaction ends (writes and the block read wait for each other);
    another user's or a missing strategy is not_found."""
    try:
        strategy_id = strategy_store.check_strategy_id(strategy_id)
        await strategy_store.lock_strategy(conn, _user_ref(user_ref), strategy_id)
    except strategy_store.StrategyStoreError as exc:
        raise ReconciliationStoreError(NOT_FOUND, f"strategy {strategy_id!r}") from exc
    return strategy_id


_INSERT_MISMATCH = text(
    "INSERT INTO public.reconciliation_mismatches (strategy_id, contract_key, expected_units, zerodha_units, report, "
    "source) VALUES (:s, :k, :e, :z, CAST(:r AS jsonb), :src) RETURNING id")
_SETTLING_SQL = ", ".join(f"'{a}'" for a in SETTLING)
#: A mismatch is unresolved while it has no settling resolution (a "requiring attention" mark settles nothing).
_NOT_SETTLED = ("NOT EXISTS (SELECT 1 FROM public.reconciliation_resolutions AS r WHERE r.mismatch_id = m.id "  # noqa: S608 constant action list
                f"AND r.action IN ({_SETTLING_SQL}))")
_REPORT_SIZE = text("SELECT octet_length(CAST(:r AS jsonb)::text)")
_SAME_UNRESOLVED = text(
    "SELECT m.id FROM public.reconciliation_mismatches AS m WHERE m.strategy_id = :s AND m.contract_key = :k "  # noqa: S608 constant action list
    f"AND m.expected_units = :e AND m.zerodha_units = :z AND {_NOT_SETTLED} ORDER BY m.id LIMIT 1")
_MISMATCH_OF = text(
    "SELECT m.contract_key, EXISTS (SELECT 1 FROM public.reconciliation_resolutions AS r WHERE r.mismatch_id = m.id "  # noqa: S608 constant action list
    f"AND r.action IN ({_SETTLING_SQL})) AS settled FROM public.reconciliation_mismatches AS m "
    "WHERE m.id = :m AND m.strategy_id = :s")
#: Q224: another strategy of the same user with an unresolved mismatch on the same contract (a shared contract).
_SHARED = text(
    "SELECT EXISTS (SELECT 1 FROM public.reconciliation_mismatches AS m JOIN public.strategies AS st "  # noqa: S608 constant action list
    "ON st.id = m.strategy_id WHERE st.user_ref = :u AND m.strategy_id <> :s AND m.contract_key = :k "
    f"AND {_NOT_SETTLED})")
_INSERT_RESOLUTION = text(
    "INSERT INTO public.reconciliation_resolutions (mismatch_id, action, actor, note) VALUES (:m, :a, :actor, :n)")
_UNRESOLVED = text(
    "SELECT EXISTS (SELECT 1 FROM public.reconciliation_mismatches AS m WHERE m.strategy_id = :s "  # noqa: S608 constant action list
    f"AND {_NOT_SETTLED})")
_MISMATCHES = text(
    "SELECT m.id, m.strategy_id, m.contract_key, m.expected_units, m.zerodha_units, m.report, m.source, "
    "m.detected_at, r.action, r.actor, r.note, r.resolved_at FROM public.reconciliation_mismatches AS m "
    "LEFT JOIN public.reconciliation_resolutions AS r ON r.mismatch_id = m.id WHERE m.strategy_id = :s "
    "ORDER BY m.id, r.resolved_at, r.action")
_STANDALONE = text("SELECT contract_key, units FROM public.reconciliation_standalone WHERE user_ref = :u "
                   "ORDER BY contract_key")
_SET_STANDALONE = text(
    "INSERT INTO public.reconciliation_standalone (user_ref, contract_key, units) VALUES (:u, :k, :n) "
    "ON CONFLICT (user_ref, contract_key) DO UPDATE SET units = EXCLUDED.units")


async def record_mismatch(conn: Any, user_ref: str, strategy_id: int, *, contract_key: str,  # noqa: PLR0913 fixed API
                          expected_units: int, zerodha_units: int, report: Mapping[str, Any],
                          source: str) -> int:
    """Stores one mismatch and returns its id; the same unresolved mismatch seen again returns the stored id. The
    strategy stays blocked until a settling ``record_resolution``."""
    strategy_id = await _lock(conn, user_ref, strategy_id)
    key = _contract_key(contract_key, BAD_MISMATCH)
    expected = _units(expected_units, "expected_units", BAD_MISMATCH)
    zerodha = _units(zerodha_units, "zerodha_units", BAD_MISMATCH)
    if expected == zerodha:
        raise ReconciliationStoreError(BAD_MISMATCH, f"expected and Zerodha agree at {expected}: not a mismatch")
    if not isinstance(source, str) or source not in SOURCES:
        raise ReconciliationStoreError(BAD_MISMATCH, f"source must be one of {SOURCES}, got {source!r}")
    params = {"s": strategy_id, "k": key, "e": expected, "z": zerodha, "r": _report(report), "src": source}
    same = (await conn.execute(_SAME_UNRESOLVED, params)).scalar_one_or_none()
    if same is not None:
        return int(same)
    await _report_fits(conn, params["r"])
    return int((await conn.execute(_INSERT_MISMATCH, params)).scalar_one())


async def record_resolution(conn: Any, user_ref: str, strategy_id: int, mismatch_id: int, *,  # noqa: PLR0913
                            action: str, note: str | None = None, zerodha_net_now: int | None = None) -> None:
    """Records a resolution of an unresolved mismatch of the user's strategy; the acting user is the actor.

    ``zerodha_net_now``: Zerodha's net quantity for the mismatch's contract in the positions reply read for THIS
    action (the route parses it, #380 step 2.2); required for ``kite_flat_marked_exited``, which is refused unless it
    is 0. Only ``SETTLING`` actions lift the block; a settled mismatch takes no further resolution
    (``already_resolved``), and "requiring attention" is accepted once per mismatch."""
    strategy_id = await _lock(conn, user_ref, strategy_id)
    if isinstance(mismatch_id, bool) or not isinstance(mismatch_id, int) or not 1 <= mismatch_id <= 2**63 - 1:
        raise ReconciliationStoreError(NOT_FOUND, f"mismatch {mismatch_id!r}")
    if not isinstance(action, str) or action not in ACTIONS:
        raise ReconciliationStoreError(BAD_RESOLUTION, f"action must be one of {ACTIONS}, got {action!r}")
    checked_note = _note(note)
    if zerodha_net_now is not None:
        _units(zerodha_net_now, "zerodha_net_now", BAD_RESOLUTION)
    row = (await conn.execute(_MISMATCH_OF, {"m": mismatch_id, "s": strategy_id})).first()
    if row is None:
        raise ReconciliationStoreError(NOT_FOUND, f"mismatch {mismatch_id} of strategy {strategy_id}")
    if row.settled:
        raise ReconciliationStoreError(ALREADY_RESOLVED, f"mismatch {mismatch_id} is already settled")
    if action == KITE_FLAT and zerodha_net_now != 0:
        raise ReconciliationStoreError(BAD_RESOLUTION, f"{KITE_FLAT} needs Zerodha's current net on "
                                                       f"{row.contract_key} to be 0, got {zerodha_net_now!r}")
    if action in SETTLING and bool((await conn.execute(_SHARED, {"u": user_ref, "s": strategy_id,
                                                                  "k": row.contract_key})).scalar_one()):
        raise ReconciliationStoreError(BAD_RESOLUTION, f"{row.contract_key} has an unresolved mismatch on another "
                                                       "strategy too (Q224): every holder stays blocked")
    # One settling row per mismatch is enforced by the database (unique index): no read-then-insert race.
    try:
        async with conn.begin_nested():
            await conn.execute(_INSERT_RESOLUTION, {"m": mismatch_id, "a": action, "actor": user_ref,
                                                    "n": checked_note})
    except DBAPIError as exc:
        if getattr(exc.orig, "sqlstate", None) == _UNIQUE_VIOLATION and any(
                k in str(exc.orig) for k in _RESOLUTION_KEYS):
            raise ReconciliationStoreError(ALREADY_RESOLVED, str(exc.orig)) from exc
        raise


async def is_blocked(conn: Any, user_ref: str, strategy_id: int) -> bool:
    """True while any mismatch of the strategy has no settling resolution (REQ-060 AC-6, Q222)."""
    strategy_id = await _lock(conn, user_ref, strategy_id)
    return await unresolved_locked(conn, strategy_id)


async def unresolved_locked(conn: Any, strategy_id: int) -> bool:
    """``is_blocked`` for a caller that already holds the strategy's row lock in this transaction (the plan store's
    ``unresolved_from_positions`` close): no lock, no ownership check - the caller did both."""
    return bool((await conn.execute(_UNRESOLVED, {"s": strategy_id})).scalar_one())


async def mismatches_for(conn: Any, user_ref: str, strategy_id: int) -> tuple[StoredMismatch, ...]:
    """Every stored mismatch of the strategy with its resolutions (oldest first), oldest mismatch first."""
    strategy_id = await _lock(conn, user_ref, strategy_id)
    found: dict[int, tuple[Any, list[StoredResolution]]] = {}
    for r in (await conn.execute(_MISMATCHES, {"s": strategy_id})).all():
        _, resolutions = found.setdefault(int(r.id), (r, []))
        if r.action is not None:
            resolutions.append(StoredResolution(action=r.action, actor=r.actor, note=r.note,
                                                resolved_at=r.resolved_at))
    return tuple(
        StoredMismatch(id=int(r.id), strategy_id=int(r.strategy_id), contract_key=r.contract_key,
                       expected_units=int(r.expected_units), zerodha_units=int(r.zerodha_units), report=r.report,
                       source=r.source, detected_at=r.detected_at, resolutions=tuple(resolutions))
        for r, resolutions in found.values())


async def standalone_for(conn: Any, user_ref: str) -> dict[str, int]:
    """The user's recorded standalone units per contract key; a contract with no row is absent (not 0)."""
    rows = (await conn.execute(_STANDALONE, {"u": _user_ref(user_ref)})).all()
    return {r.contract_key: int(r.units) for r in rows}


async def set_standalone(conn: Any, user_ref: str, contract_key: str, units: int) -> None:
    """Records (or changes) the user's standalone units on one contract; 0 is stored, never a delete."""
    key = _contract_key(contract_key, BAD_STANDALONE)
    await conn.execute(_SET_STANDALONE, {"u": _user_ref(user_ref), "k": key,
                                         "n": _units(units, "units", BAD_STANDALONE)})


__all__ = ["ACTIONS", "ALREADY_RESOLVED", "ATTENTION", "BAD_MISMATCH", "BAD_RESOLUTION", "BAD_STANDALONE", "BASKET",
           "KITE_FLAT", "NOT_FOUND", "RESERVED_ACTIONS", "SETTLING", "SOURCES", "ReconciliationStoreError",
           "StoredMismatch", "StoredResolution", "is_blocked", "mismatches_for", "record_mismatch",
           "record_resolution", "set_standalone", "standalone_for", "unresolved_locked"]
