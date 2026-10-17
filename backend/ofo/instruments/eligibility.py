"""Current eligibility: what Zerodha permits right now, for one contract.

REQ-053 AC-1/AC-2: Zerodha's response is the final authority on eligibility; this structure is
kept separate from the contract catalogue (`ofo.instruments.catalogue.Catalogue`) — the catalogue
never merges eligibility into a contract record, and eligibility never deletes a catalogue entry.

W-092 round 2 (Tier A review, MAJOR: forgeable eligibility; findings caller-supplied-verdict-trusted and
sealed-object-mutable-after-seal): the pre-execution gate accepts eligibility ONLY as a sealed ``ZerodhaEligibility``.
It is minted by ``registry_from_list`` (from list rows, the India date and the load time) and by
``apply_margin_refusals`` (a NEW sealed object with the basket-margin reply's refusals applied); nothing else makes
one. The per-contract input, ``ListState``, is sealed the same way and is minted only by reading a row
(``list_state_from_row``) or Zerodha's parsed list (``states_from_parsed_list``); a hand-made state is refused.

Sealed means: an immutable tuple with no attribute storage (``object.__setattr__`` has nothing to write, there is no
``record``), calling the class raises, subclasses are refused, ``copy``/``deepcopy``/``pickle``/``dataclasses.replace``
raise, and identities are stored as plain ``(segment, token)`` tuples so editing an ``InstrumentId`` object afterwards
changes nothing. This is not proof against deliberate tricks (``tuple.__new__``, ``copyreg``, a ``__class__`` swap,
a fabricated row object): those are out of scope as for the sealed basket (ADR-003 Q235); the door scan
(``tests/test_door_names_private.py``) allows ``tuple.__new__`` only in this file among the instruments package.
"""
from __future__ import annotations

from bisect import bisect_left
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from types import SimpleNamespace
from typing import Any, Optional

from ofo.instruments.models import INDEX_TYPE, ZERODHA, Contract, InstrumentId, ListedContract
from ofo.sealed import SealedTuple


@dataclass(frozen=True)
class EligibilityStatus:
    """A point-in-time eligibility read from Zerodha for one instrument. Information only: the gate never takes one;
    ``ZerodhaEligibility.get`` builds a new one on every call from its sealed entries."""

    instrument_id: InstrumentId
    tradable: bool
    checked_at: datetime
    reason: Optional[str] = None


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

#: The store columns a list row carries (``ofo_app.eligibility_from_zerodha`` selects exactly these).
ROW_COLUMNS = ("exchange_segment", "exchange_token", "instrument_type", "expiry", "currently_listed", "retired",
               "delisted", "has_zerodha_row")


def _strict_bool(value: object, name: str) -> bool:
    if type(value) is not bool:
        raise TypeError(f"list row column {name} must be a bool, got {value!r}")
    return value


class ListState(SealedTuple, made_by="list_state_from_row or states_from_parsed_list", again="read the row again"):
    """One catalogue contract as Zerodha's latest instrument-list load left it (ADR-104 (a)). Sealed: made only by
    ``list_state_from_row`` (a store row) or ``states_from_parsed_list`` (Zerodha's parsed list), never by hand."""

    __slots__ = ()

    @property
    def instrument_id(self) -> InstrumentId:
        return InstrumentId(self[0], self[1])

    @property
    def instrument_type(self) -> str:
        return self[2]

    @property
    def expiry(self) -> date | None:
        return self[3]

    @property
    def listed(self) -> bool:
        return self[4]

    @property
    def retired(self) -> bool:
        return self[5]

    @property
    def delisted(self) -> bool:
        return self[6]

    @property
    def has_zerodha_row(self) -> bool:
        return self[7]


def list_state_from_row(row: Any) -> ListState:
    """Read one list row (attributes named in ``ROW_COLUMNS``: the catalogue store's columns as the latest Zerodha load
    left them). Every flag must be a real bool and the expiry a date or None; anything else raises (fail closed)."""
    instrument_id = InstrumentId(row.exchange_segment, row.exchange_token)
    instrument_type = row.instrument_type
    if not isinstance(instrument_type, str):
        raise TypeError(f"list row column instrument_type must be a str, got {instrument_type!r}")
    expiry = row.expiry
    if expiry is not None and type(expiry) is not date:
        raise TypeError(f"list row column expiry must be a date or None, got {expiry!r}")
    flags = (_strict_bool(row.currently_listed, "currently_listed"), _strict_bool(row.retired, "retired"),
             _strict_bool(row.delisted, "delisted"), _strict_bool(row.has_zerodha_row, "has_zerodha_row"))
    return tuple.__new__(ListState, (instrument_id.exchange_segment, instrument_id.exchange_token, instrument_type,
                                     expiry, *flags))


def _check_today(today: object) -> date:
    if type(today) is not date:  # a datetime is a date subclass: refuse it, the India DATE is what is compared
        raise TypeError(f"today must be a datetime.date (the India date on the database clock), got {today!r}")
    return today


def _check_aware(at: object, name: str) -> datetime:
    if not isinstance(at, datetime) or at.tzinfo is None or at.utcoffset() is None:
        raise TypeError(f"{name} must be a timezone-aware datetime, got {at!r}")
    return at


def _check_state(state: object) -> ListState:
    if type(state) is not ListState:  # a hand-made state, a duck or a plain tuple is refused (A1c)
        raise TypeError(f"expected a ListState read from a list row, got {state!r}")
    return state


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
    """ADR-104 (a): one contract's eligibility from the latest list load. ``checked_at`` is that load's time. Takes only
    a ``ListState`` read from a row; the result is information for the add-time check and cannot reach the gate."""
    reason = _not_tradable_reason(_check_state(state), _check_today(today))
    return EligibilityStatus(instrument_id=state.instrument_id, tradable=reason is None,
                             checked_at=_check_aware(loaded_at, "loaded_at"), reason=reason)


def _entry_key(entry: tuple) -> tuple[str, int]:
    return entry[0], entry[1]


class ZerodhaEligibility(SealedTuple, made_by="registry_from_list or apply_margin_refusals",
                         again="build it again from the list"):
    """The eligibility the pre-execution gate trusts. Each entry is a plain ``(segment, token, tradable, checked_at,
    reason)`` tuple. Sealed (see the module docstring): made only by ``registry_from_list`` and
    ``apply_margin_refusals``; there is no way to record, overwrite or remove an entry afterwards."""

    __slots__ = ()

    def _entry(self, instrument_id: object) -> tuple | None:
        if not isinstance(instrument_id, InstrumentId):
            raise TypeError(f"eligibility is keyed by InstrumentId, got {instrument_id!r}")
        key = (instrument_id.exchange_segment, instrument_id.exchange_token)
        at = bisect_left(self, key, key=_entry_key)  # entries are sorted by identity at minting (one per identity)
        return self[at] if at < len(self) and _entry_key(self[at]) == key else None

    def get(self, instrument_id: InstrumentId) -> Optional[EligibilityStatus]:
        entry = self._entry(instrument_id)
        if entry is None:
            return None
        return EligibilityStatus(InstrumentId(entry[0], entry[1]), entry[2], entry[3], entry[4])

    def is_tradable(self, instrument_id: InstrumentId) -> bool:
        """Fail closed: an instrument with no recorded eligibility check is not tradable."""
        entry = self._entry(instrument_id)
        return entry is not None and entry[2] is True

    def __repr__(self) -> str:
        return f"ZerodhaEligibility({len(self)} contracts)"


#: The empty sealed eligibility (no list load ever, or an untrusted object at the gate): every leg is unconfirmed.
NO_ELIGIBILITY: ZerodhaEligibility = tuple.__new__(ZerodhaEligibility, ())


def registry_from_list(states: Iterable[ListState], *, today: date, loaded_at: datetime) -> ZerodhaEligibility:
    """A NEW sealed eligibility from the latest list load (ADR-104 (a)). A contract with no state stays unrecorded
    (the gate then refuses it as unconfirmed). Two states for one identity are refused (a live identity is unique;
    two answers for one contract is not data this function may choose between). An empty input is the empty object
    (no load ever: every leg unconfirmed)."""
    _check_today(today)
    _check_aware(loaded_at, "loaded_at")
    entries: dict[tuple[str, int], tuple] = {}
    for state in states:
        status = status_from_list(state, today=today, loaded_at=loaded_at)
        key = (state[0], state[1])
        if key in entries:
            raise ValueError(f"two list states for {status.instrument_id!r}")
        entries[key] = (*key, status.tradable, status.checked_at, status.reason)
    return tuple.__new__(ZerodhaEligibility, tuple(sorted(entries.values(), key=_entry_key)))


def apply_margin_refusals(eligibility: ZerodhaEligibility, refusals: Mapping[InstrumentId, str], *,
                          refused_at: datetime) -> ZerodhaEligibility:
    """ADR-104 (b): a NEW sealed eligibility with the basket-margin reply's per-leg refusals applied (instrument ->
    Zerodha's error text). A refusal can only make a contract NOT tradable, never tradable; the input is unchanged."""
    if type(eligibility) is not ZerodhaEligibility:
        raise TypeError(f"expected a ZerodhaEligibility, got {eligibility!r}")
    _check_aware(refused_at, "refused_at")
    entries = {(e[0], e[1]): e for e in eligibility}
    for instrument_id, text in dict(refusals).items():
        if not isinstance(instrument_id, InstrumentId):
            raise TypeError(f"a margin refusal is keyed by InstrumentId, got {instrument_id!r}")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"a margin refusal needs Zerodha's text, got {text!r} for {instrument_id!r}")
        key = (instrument_id.exchange_segment, instrument_id.exchange_token)
        entries[key] = (*key, False, refused_at, text.strip())
    return tuple.__new__(ZerodhaEligibility, tuple(sorted(entries.values(), key=_entry_key)))


def states_from_parsed_list(catalogue_contracts: Iterable[Contract],
                            current_list: Iterable[ListedContract]) -> list[ListState]:
    """The pure path (no database): every catalogue contract, marked listed when Zerodha's parsed list carries it with
    a Zerodha row. A list row the catalogue does not hold is not added: eligibility never adds a contract (AC-2)."""
    zerodha_ids = {row.id for row in current_list if any(ref.broker == ZERODHA for ref in row.broker_refs)}
    return [list_state_from_row(SimpleNamespace(
        exchange_segment=c.id.exchange_segment, exchange_token=c.id.exchange_token, instrument_type=c.instrument_type,
        expiry=c.expiry, currently_listed=c.id in zerodha_ids, retired=False, delisted=False,
        has_zerodha_row=c.id in zerodha_ids)) for c in catalogue_contracts]
