"""#380-2 (T3, #423): the ONE reconciliation the Execute route and the return route both call.

Spec basis: REQ-060 AC-6/AC-7; ADR-109 (2); ADR-110; Q224 ("blocks every holder"); fix-380 draft T3 ("One function, two
callers: this removes today's disagreement between ``routes/execute.py:495-506`` and
``routes/execution_return.py:185-204``"); issue #423 (Zerodha's net derived from Kite by the route; the Q224 check
under a per-user lock).

What a route passes: the database connection, the user, the catalogue, and Zerodha's two raw replies the route just
read with the user's session (``fetch_positions`` data, ``fetch_orders`` rows). Zerodha's net and order book are parsed
HERE (``kite_replies.positions_from_reply`` / ``orders_from_reply``); no parameter takes a net, a held map, a verdict or
a "reconciled" flag (finding ``caller-supplied-verdict-trusted``). The standalone quantities are read HERE from
``reconciliation_store``; every strategy and plan is read by ``reconcile_attribution.attribute_and_compare`` itself.

Locking (Q224, #423 item 2): ``lock_user`` takes a per-user transaction advisory lock. A route takes it FIRST, before
any strategy row lock: ``attribute_and_compare`` row-locks every strategy of the user (``mismatches_for``), so two
requests of one user on two strategies would otherwise each hold one strategy lock and wait for the other's
(deadlock). Under the user lock, two reconciliations of one user (and the mismatch writes they make) never interleave.

Storing (REQ-060 AC-3/AC-6, Q222): with a ``source`` (one of ``reconciliation_store.SOURCES``; the return route is
``after_execution``), every blocking mismatch compare reports is stored once per (strategy, contract) through
``reconciliation_store.record_mismatch`` (the same unresolved mismatch seen again keeps its id), so the block is sticky.
``source=None`` (the Execute press, which is not one of Q196's triggers and rolls back on refusal) stores nothing; a
mismatch stored earlier still blocks it (``Attribution.stored``).
"""
from __future__ import annotations

import datetime
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from ofo.instruments.catalogue import Catalogue
from ofo.instruments.models import InstrumentId
from ofo.reconciliation.compare import MismatchKind
from sqlalchemy import text

from ofo_app import reconcile_attribution as ra
from ofo_app import reconciliation_store
from ofo_app.kite_replies import ContractIndex, PositionsRead, orders_from_reply, positions_from_reply

#: First key of the two-key advisory lock (second: ``hashtext(user_ref)``); only this module uses it (REQ-060).
RECONCILE_LOCK_CLASS = 52_060
_LOCK = text("SELECT pg_advisory_xact_lock(:cls, hashtext(:u))")

#: Each compare kind -> its catalogue template id (``ofo.errors``): the code a route shows (closed: one per kind).
MISMATCH_CODES: Mapping[MismatchKind, str] = {kind: f"recon_{kind.name.lower()}" for kind in MismatchKind}


async def lock_user(conn: Any, user_ref: str) -> None:
    """The per-user reconciliation lock, held until the transaction ends. Take it before any strategy row lock."""
    if not isinstance(user_ref, str) or not user_ref.strip():
        raise ra.AttributionError(f"a user is required for the reconciliation lock, got {user_ref!r}")
    await conn.execute(_LOCK, {"cls": RECONCILE_LOCK_CLASS, "u": user_ref})


@dataclass(frozen=True)
class StoredRow:
    """One mismatch row to store: whose strategy, which contract (stored key text), expected vs Zerodha, the kind."""

    strategy_id: int
    contract_key: str
    expected_units: int
    zerodha_units: int
    kind: MismatchKind


@dataclass(frozen=True)
class Verdict:
    """One reconciliation of the account: the attribution, Zerodha's parsed positions (the route reuses them, e.g.
    for the held products), the rows that were (or with ``source=None`` would be) stored, and their stored ids."""

    attribution: ra.Attribution
    positions: PositionsRead
    rows: tuple[StoredRow, ...]
    stored_ids: tuple[int, ...]

    def blocks(self, strategy_id: int) -> bool:
        return str(strategy_id) in self.attribution.blocked


def standalone_keys(stored: Mapping[str, int], catalogue: Catalogue) -> dict[ra.ContractKey, int]:
    """The stored standalone map (``segment:token`` -> units) keyed by contract; a key the catalogue cannot place is
    refused (``AttributionError``), never dropped (a dropped standalone would turn into outside lots)."""
    out: dict[ra.ContractKey, int] = {}
    for key_text, units in stored.items():
        segment, _, token = key_text.partition(":")
        entry = None
        if token.isascii() and token.isdigit():
            try:
                entry = catalogue.get(InstrumentId(segment, int(token)))
            except ValueError:
                entry = None
        if entry is None:
            raise ra.AttributionError(f"standalone contract {key_text!r} is not in the catalogue")
        key = ra.instrument_key(catalogue, key_text, entry.contract.name)
        out[key] = out.get(key, 0) + units
    return out


def mismatch_rows(attribution: ra.Attribution, catalogue: Catalogue) -> tuple[StoredRow, ...]:
    """Every blocking mismatch of compare's report, one row per (strategy, contract) whose expected and Zerodha units
    differ. A mismatch that blocks no strategy (outside lots, a standalone change) is never stored."""
    rows: dict[tuple[int, str], StoredRow] = {}
    for mismatch in attribution.report.mismatches:
        if not mismatch.strategy_ids:
            continue
        expected, broker = dict(mismatch.platform_state), dict(mismatch.broker_state)
        for contract, _ in mismatch.difference:
            exp, zer = expected.get(contract, 0), broker.get(contract, 0)
            if exp == zer:
                continue
            for sid in mismatch.strategy_ids:
                row = StoredRow(int(sid), ra.key_text(catalogue, contract), exp, zer, mismatch.kind)
                rows.setdefault((row.strategy_id, row.contract_key), row)
    return tuple(rows[k] for k in sorted(rows))


async def attribute(  # noqa: PLR0913 the account, Zerodha's two raw replies, the sources and the time
    conn: Any, user_ref: str, catalogue: Catalogue, positions_reply: object, order_rows: object, *,
    at: datetime.datetime, today: datetime.date, clock: Callable[[], datetime.datetime],
    reader: ra.StoreReader | None = None,
) -> tuple[ra.Attribution, PositionsRead]:
    """Parse Zerodha's two replies, read the standalone map, run the one attribution. Unreadable replies raise
    ``KiteReplyError``/``ValueError``; unreadable stored data ``AttributionError``. Never guessed. ``today``: the
    request's IST session date on the clock that stamps a plan's ``created_at`` (the database's); ``at`` stays the
    comparison time."""
    positions = positions_from_reply(positions_reply, ContractIndex.from_catalogue(catalogue))  # type: ignore[arg-type]
    book = orders_from_reply(order_rows)
    standalone = standalone_keys(await reconciliation_store.standalone_for(conn, user_ref), catalogue)
    sources = ra.Sources(catalogue, clock) if reader is None else ra.Sources(catalogue, clock, reader)
    attribution = await ra.attribute_and_compare(ra.Account(conn, user_ref), standalone, positions.net, book, sources,
                                                 at=at, today=today)
    return attribution, positions


async def reconcile_account(  # noqa: PLR0913 the account, Zerodha's two raw replies, time, the trigger source
    conn: Any, user_ref: str, catalogue: Catalogue, positions_reply: object, order_rows: object, *,
    at: datetime.datetime, today: datetime.date, clock: Callable[[], datetime.datetime], source: str | None,
) -> Verdict:
    """The routes' one call: per-user lock, the attribution (``attribute``), then the blocking mismatches stored under
    ``source`` (nothing stored when ``source`` is None). The caller must already hold no strategy row lock taken
    before ``lock_user`` (take ``lock_user`` first). ``today`` is the session date of the clock that stamped the
    plans (the database's India date): a request clock on another date must never make a plan stamped today read as
    "from the future" (#380-2 fix round, CI run 39427914444)."""
    if source is not None and source not in reconciliation_store.SOURCES:
        raise ra.AttributionError(f"source must be one of {reconciliation_store.SOURCES} or None, got {source!r}")
    await lock_user(conn, user_ref)
    attribution, positions = await attribute(conn, user_ref, catalogue, positions_reply, order_rows, at=at,
                                             today=today, clock=clock)
    rows = mismatch_rows(attribution, catalogue)
    ids = [] if source is None else [await _store(conn, user_ref, row, source, at) for row in rows]
    return Verdict(attribution, positions, rows, tuple(ids))


async def _store(conn: Any, user_ref: str, row: StoredRow, source: str, at: datetime.datetime) -> int:
    return await reconciliation_store.record_mismatch(
        conn, user_ref, row.strategy_id, contract_key=row.contract_key, expected_units=row.expected_units,
        zerodha_units=row.zerodha_units, source=source,
        report={"kind": row.kind.value, "at": at.isoformat(), "code": MISMATCH_CODES[row.kind]})


__all__ = ["MISMATCH_CODES", "RECONCILE_LOCK_CLASS", "StoredRow", "Verdict", "attribute", "lock_user",
           "mismatch_rows", "reconcile_account", "standalone_keys"]
