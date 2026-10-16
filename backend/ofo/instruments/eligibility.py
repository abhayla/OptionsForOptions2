"""Current eligibility: what Zerodha permits right now, for one contract.

REQ-053 AC-1/AC-2: Zerodha's response is the final authority on eligibility; this structure is
kept separate from the contract catalogue (`ofo.instruments.catalogue.Catalogue`) — the catalogue
never merges eligibility into a contract record, and this registry never deletes a catalogue entry.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from ofo.instruments.models import INDEX_TYPE, ZERODHA, Contract, InstrumentId, ListedContract


@dataclass(frozen=True)
class EligibilityStatus:
    """A point-in-time eligibility read from Zerodha for one instrument."""

    instrument_id: InstrumentId
    tradable: bool
    checked_at: datetime
    reason: Optional[str] = None


class EligibilityRegistry:
    """Holds the latest known `EligibilityStatus` per contract identity (`InstrumentId`, ADR-050).

    Deliberately has no reference to `Catalogue` and no method that writes into one — eligibility
    and the contract catalogue are separate structures (AC-2).
    """

    def __init__(self) -> None:
        self._status: dict[InstrumentId, EligibilityStatus] = {}

    def record(self, status: EligibilityStatus) -> None:
        if not isinstance(status.instrument_id, InstrumentId):
            raise TypeError(f"eligibility is keyed by InstrumentId, got {status.instrument_id!r}")
        self._status[status.instrument_id] = status

    def get(self, instrument_id: InstrumentId) -> Optional[EligibilityStatus]:
        return self._status.get(instrument_id)

    def is_tradable(self, instrument_id: InstrumentId) -> bool:
        """Fail closed: an instrument with no recorded eligibility check is not tradable."""
        status = self._status.get(instrument_id)
        return status is not None and status.tradable


# ---------------------------------------------------------------------------------------------------------------
# ADR-104 (W-092, REQ-053 AC-3): eligibility filled from Zerodha's own data, and nothing else (AC-4: no platform rule).
# (a) the contract is in Zerodha's CURRENT instrument list as the latest load left it, and its expiry is on or after
#     today's India date -> tradable; (b) just before execution, a leg Zerodha's basket-margin reply refuses -> not
#     tradable with Zerodha's text. The reasons below are internal (audit/log); the user sees the gate's catalogue text.
# ---------------------------------------------------------------------------------------------------------------

# Reason CODES (not sentences: user wording comes only from the message catalogue, REQ-065 AC-2).
REASON_NOT_IN_LIST = "not_in_current_list"  # the latest Zerodha list load does not carry it
REASON_EXPIRED = "expired"  # its expiry date is before today's India date
REASON_DELISTED = "delisted"  # Zerodha's list stopped carrying it before its expiry (ADR-058)
REASON_RETIRED = "retired"  # retired after its expiry (ADR-057)
REASON_NO_ZERODHA_ROW = "no_zerodha_row"  # no live Zerodha row for this contract
REASON_INDEX = "index_row"  # an index row is not a tradable contract
REASON_NO_EXPIRY = "no_expiry"  # the list row has no expiry date


@dataclass(frozen=True)
class ListState:
    """One catalogue contract as Zerodha's latest instrument-list load left it (ADR-104 (a)).

    ``listed`` = the latest load carried it; ``has_zerodha_row`` = a live Zerodha row exists for it. The values come
    from the catalogue store (the product's own download), never from a caller's verdict.
    """

    instrument_id: InstrumentId
    instrument_type: str
    expiry: date | None
    listed: bool
    retired: bool = False
    delisted: bool = False
    has_zerodha_row: bool = True


def _check_today(today: object) -> date:
    if type(today) is not date:  # a datetime is a date subclass: refuse it, the India DATE is what is compared
        raise TypeError(f"today must be a datetime.date (the India date on the database clock), got {today!r}")
    return today


def _check_aware(at: object, name: str) -> datetime:
    if not isinstance(at, datetime) or at.tzinfo is None or at.utcoffset() is None:
        raise TypeError(f"{name} must be a timezone-aware datetime, got {at!r}")
    return at


def _not_tradable_reason(state: ListState, today: date) -> str | None:
    """The first reason ``state`` is not tradable, or None. Order: lifecycle, list, Zerodha row, type, expiry."""
    checks = (
        (state.retired, REASON_RETIRED),
        (state.delisted, REASON_DELISTED),
        (not state.listed, REASON_NOT_IN_LIST),
        (not state.has_zerodha_row, REASON_NO_ZERODHA_ROW),
        (state.instrument_type == INDEX_TYPE, REASON_INDEX),
        (state.expiry is None, REASON_NO_EXPIRY),
        # F-33: an expired row can still be in the list; the list carrying it is not enough
        (state.expiry is not None and state.expiry < today, REASON_EXPIRED),
    )
    return next((reason for failed, reason in checks if failed), None)


def status_from_list(state: ListState, *, today: date, loaded_at: datetime) -> EligibilityStatus:
    """ADR-104 (a): one contract's eligibility from the latest list load. ``checked_at`` is that load's time."""
    if not isinstance(state, ListState):
        raise TypeError(f"expected a ListState, got {state!r}")
    reason = _not_tradable_reason(state, _check_today(today))
    return EligibilityStatus(instrument_id=state.instrument_id, tradable=reason is None,
                             checked_at=_check_aware(loaded_at, "loaded_at"), reason=reason)


def registry_from_list(
    states: Iterable[ListState], *, today: date, loaded_at: datetime,
    refusals: Mapping[InstrumentId, str] | None = None, refused_at: datetime | None = None,
) -> EligibilityRegistry:
    """A NEW registry from the latest list load (ADR-104 (a)) and, optionally, the basket-margin reply's per-leg
    refusals (ADR-104 (b): instrument -> Zerodha's error text). A refusal can only make a contract NOT tradable,
    never tradable; a contract with no state stays unrecorded (the gate then refuses it as unconfirmed).

    Two states for one identity are refused (a live identity is unique; two answers for one contract is not data
    this function may choose between).
    """
    _check_today(today)
    _check_aware(loaded_at, "loaded_at")
    registry = EligibilityRegistry()
    seen: set[InstrumentId] = set()
    for state in states:
        status = status_from_list(state, today=today, loaded_at=loaded_at)
        if status.instrument_id in seen:
            raise ValueError(f"two list states for {status.instrument_id!r}")
        seen.add(status.instrument_id)
        registry.record(status)
    for instrument_id, text in (refusals or {}).items():
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"a margin refusal needs Zerodha's text, got {text!r} for {instrument_id!r}")
        registry.record(EligibilityStatus(instrument_id=instrument_id, tradable=False,
                                          checked_at=_check_aware(refused_at, "refused_at"), reason=text.strip()))
    return registry


def states_from_parsed_list(catalogue_contracts: Iterable[Contract],
                            current_list: Iterable[ListedContract]) -> list[ListState]:
    """The pure path (no database): every catalogue contract, marked listed when Zerodha's parsed list carries it with
    a Zerodha row. A list row the catalogue does not hold is not added: eligibility never adds a contract (AC-2)."""
    zerodha_ids = {row.id for row in current_list if any(ref.broker == ZERODHA for ref in row.broker_refs)}
    return [ListState(instrument_id=c.id, instrument_type=c.instrument_type, expiry=c.expiry,
                      listed=c.id in zerodha_ids, has_zerodha_row=c.id in zerodha_ids)
            for c in catalogue_contracts]
