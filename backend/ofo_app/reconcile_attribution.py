"""W-108: attribute before compare (ADR-109 (2) and its first consequence; ADR-110; REQ-060 AC-4, AC-6, AC-7; ADR-105;
Q224).

A strategy owns exactly the fills of orders this app placed (ADR-109 (2)); what it holds is ``execute_plan.held_units``
over ALL its stored plans (ADR-105). Per contract, the expected quantity is every strategy's held units plus the
recorded standalone quantity (AC-7). A same-direction surplus of Zerodha's net beyond that is reported as OUTSIDE lots
and removed before ``ofo.reconciliation.compare`` runs; compare itself is unchanged, and the result keeps Zerodha's raw
net beside the stripped one. Examples (ADR-109): strategy BUY 65 CE, Zerodha 130 -> not blocked, 65 outside; strategy
65 + standalone 25, Zerodha 90 -> no mismatch; Zerodha 0 -> blocked.

OPEN plans (ADR-110: "makes no own/outside split for it"; "The strategy is blocked until the plan closes."; the
waiting state ends when Zerodha's order book shows the plan's own orders "(by the app's tag) in a final state").
An open plan has no stored fill yet, so its stored ``filled_quantity`` is never read. Each of its orders is looked up
in Zerodha's order book (``kite_replies.orders_from_reply``, passed in as ``order_book``) by the app's tag:

- exactly one row, and its status word is in ``execute_plan.TERMINAL_ORDER_STATUSES`` (an allow-list: COMPLETE,
  CANCELLED, REJECTED, exact text; any other or unknown word, lowercase included, is not final): that row's
  ``filled_quantity`` is the order's fill, in memory only (never stored here);
- a row whose tag is the plan's but whose side, trading symbol or quantity is not the stored order's (e.g. the user
  modified it on Kite): PENDING (``book_row_differs``) for that plan only; ``AttributionError`` stays for unreadable
  input, so one modified order never fails the whole account;
- no row (never placed, or placed on an earlier day: Kite's order book holds today's orders only), two rows with one
  tag (never summed), or a row not final: the plan is PENDING.

EARLIER-DAY open plans (#352-1; ADR-109 (2), ADR-111, ADR-016): an open plan created before today's IST date whose
tags are all absent from today's book can never end ADR-110's wait, so it is never pending. ``decide_earlier_day``
settles it from Zerodha's net against the base (every other stored fill of every strategy plus the standalone,
this strategy's other plans included): never ``nothing_placed`` while a filled-then-hand-sold round trip cannot be ruled
out (the net equalling the base proves nothing); every earlier-day plan is unresolved (``unresolved``: out of compare,
strategy and holders blocked; ``next_day_resolution`` stores a mismatch for the plan's strategy AND every holder, so
``stored`` keeps them all blocked after the plan closes), never
``filled`` or ``exited``. Example (real plan OFS1V1L0 BUY 65): base 0, net 0 -> unresolved
(``roundtrip_not_ruled_out``: bought and sold by hand the same day also leaves net 0); net 65 -> unresolved (the 65
cannot be told from outside lots). ``next_day_resolution`` writes these decisions; a plan with a tag in
today's book stays on the order-book path below. No next-day reply field proves "nothing happened yesterday", so an
earlier-day plan is never closed ``nothing_placed`` by this decision (F-55).

CLOSED plans count their stored fills, unless today's book contradicts them (fix round 2 MAJOR): a closed plan
whose tag shows in today's book a status not final or a fill other than the one stored at close
(``execution_return.drifted``; real case: Check pressed before placing -> closed ``nothing_placed`` with fill 0, then
placed on Kite and COMPLETE 65) or a row unlike the stored order is PENDING (``closed_plan_drifted`` /
``book_row_differs``). A closed plan whose tags are absent today (an earlier day's orders) keeps its stored fill.
Two orders with one tag in one plan are refused.

When every order of an open plan is final, its fills count as the strategy's own and the normal comparison applies,
even though Check was never pressed ("so a plan the user never returns to cannot hide a shortfall or outside lots for
good"). A PENDING plan makes every contract its orders touch pending: the contract is left out of compare (its net,
every strategy's units on it and its standalone), nothing on it is split as outside or reported as agreeing, and its
strategy and every other strategy holding units there are blocked (their lots cannot be told apart while one plan is
unknown; Q224 already blocks two holders). Contracts no pending plan touches are attributed as below. ``blocked`` is
compare's blocked strategies plus those; compare's report is never changed.

Attribution rule, per contract ``c`` that is not pending (``b`` = Zerodha's net, signed units, BUY +, SELL -):

- ``e`` (expected) = every strategy's held units + the recorded standalone quantity (the standalone only ADDS to ``e``).
- No strategy and no standalone holds ``c``: all of ``b`` is outside (AC-7: "a broker position in no strategy and not
  recorded as standalone ... blocks no strategy").
- The direction ``s`` is decided by the STRATEGY holders only (fix round 1: a standalone on the other side must not turn
  a single-holder contract into a both-sides one; Q224 leaves single-holder contracts unchanged); with no strategy
  holder, by the standalone. When ``b - e`` lies on side ``s`` (Zerodha holds MORE in that direction than expected),
  ``b - e`` is outside and ``e`` is compared. Anything else (a shortfall, Zerodha flat, the opposite side) is compared
  as read, so compare blocks it (AC-6, Q199). Example: own +65, standalone -25 (``e`` = 40): Zerodha 40 agrees; 65 ->
  25 outside; 130 -> 90 outside; 0 -> blocked.
- The outside cap (review round 2 MINOR 2): when an opposite standalone equals or outweighs the strategies (``e`` 0
  or on the other side of ``s``; fix round 2 MINOR 3: 0 takes the same branch as -1), ``b - e`` would reach or
  exceed Zerodha's own holding; outside is then only what Zerodha holds beyond the strategies' units (``b`` - own,
  on side ``s``), so outside never exceeds ``|b|``. Example: own +65, standalone -100,
  Zerodha +65 -> 0 outside (not 100), and the standalone short Zerodha does not show is reported in
  ``standalone_unseen`` (-100); compare decides the block.
- Strategy holders on BOTH sides of ``c``: nothing is stripped. A surplus over the sum is then a shortfall against the
  opposite-side holder's own fills (Kite nets the contract to one number; ADR-109 (2): "sold app lots, or an opposite
  outside trade that nets them away, cannot be told apart"), so it reaches compare and Q224 blocks every holder.

Inputs (finding ``caller-supplied-verdict-trusted``, run-discipline B8): the caller passes only the account (database
connection + user), Zerodha's net, Zerodha's order book, the standalone map and ``at``. EVERY strategy of the account
and ALL of each one's stored plans are read HERE through the store reader (``strategy_store.list_strategies`` +
``execution_plan_store.plans_for``), so no plan or strategy can be left out by a caller; a reader whose calls are not
those two store functions is refused unless ``APP_ENV`` is exactly ``test`` (review round 2 MINOR 1). Held units are
computed HERE, never accepted; compare is called HERE. Zerodha's net and order book are what the reply adapter parsed
(``kite_replies.positions_from_reply(...).net``, ``kite_replies.orders_from_reply``), validated again here; this
module imports no Kite module (REQ-063 AC-1). A strategy that holds nothing (no fills, every fill closed, exited) has
no active position and is not passed to compare. No route is wired here (GC-3F).
"""
from __future__ import annotations

import dataclasses
import datetime
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Protocol

from ofo.engine import Action
from ofo.execution.basket import parse_tag
from ofo.instruments.catalogue import Catalogue
from ofo.instruments.models import InstrumentId
from ofo.reconciliation.compare import MAX_STRATEGIES, ReconciliationReport, compare, units_map
from ofo.strategy.definition import DefinitionLeg, StrategyDefinition
from ofo.strategy.versions import StrategyRecord
from ofo.timeutil import EXPIRY_CLOSE, IST

from ofo_app import execute_plan as ep
from ofo_app import execution_plan_store, reconciliation_store, strategy_store
from ofo_app import execution_return as er
from ofo_app.config import app_env
from ofo_app.execution_plan_store import PlanOrder, StoredPlan
from ofo_app.reconciliation_store import StoredMismatch
from ofo_app.strategy_store import StrategySummary

ContractKey = tuple  # (underlying, Instrument, strike | None, expiry): the reconcile key (execute_plan.contract_key)
ListStrategies = Callable[[object, str], Awaitable[Sequence[StrategySummary]]]
PlansFor = Callable[[object, str, int], Awaitable[Sequence[StoredPlan]]]
MismatchesFor = Callable[[object, str, int], Awaitable[Sequence[StoredMismatch]]]

#: The actor recorded on the in-memory record compare reads (never stored; the record lives for one comparison).
_ACTOR = "reconcile_attribution"
#: The only APP_ENV under which a non-default store reader (a test fake) is accepted.
_TEST_ENV = "test"

#: Why a contract is pending (a closed set): an order of an open plan is not final at Zerodha, is not in today's
#: order book, or two order-book rows carry its tag.
PENDING_NOT_FINAL = "order not final at Zerodha"
PENDING_ABSENT = "order not in Zerodha's order book"
PENDING_DUPLICATE_TAG = "two order-book rows carry the tag"
#: A row with the plan's tag whose side, trading symbol or quantity is not the stored order's (e.g. modified on Kite).
PENDING_ROW_DIFFERS = "book_row_differs"
#: A CLOSED plan whose tags show, in today's book, a status not final or a fill other than the one stored at close
#: (``execution_return.drifted``: e.g. Check pressed before placing -> closed "nothing_placed", then placed on Kite).
PENDING_CLOSED_DRIFTED = "closed_plan_drifted"

#: #352-1: why an EARLIER-DAY open plan cannot be settled on one contract (a closed set; ``EarlierDayContract.reason``).
#: Zerodha's net is not what the strategies' stored fills and the standalone say without this plan (more, less,
#: opposite, flat): the plan's orders may have filled, or an outside trade moved it; never guessed (ADR-109 (2)).
UNSETTLED_NET_CHANGED = "net_changed"
#: The contract's expiry close has passed: Zerodha's net no longer shows what the plan did (settled, ADR-083).
UNSETTLED_EXPIRED = "contract_expired"
#: Another plan (an open or drifted plan of any strategy, or another earlier-day plan) touches the contract: its units
#: are unknown, so "nothing changed" cannot be read (two opposite fills net to nothing).
UNSETTLED_SHARED = "another_plan_unsettled"
#: Another strategy holds units on the contract by its stored fills (Q224 shared contract, #352-1 round 2 MINOR 3):
#: S1's plan filled and S2's lots sold by hand the same day leave the net at the base, so "nothing changed" is unread.
UNSETTLED_HELD_ELSEWHERE = "another_strategy_holds"
#: The plan buys AND sells the contract: a net that did not move cannot show that nothing filled.
UNSETTLED_MIXED_SIDES = "plan_sides_mixed"
#: The net equals the base, but a next-day positions reply carries nothing that shows yesterday's activity (a flat
#: contract's row is gone; ``day_*`` quantities restart; ``overnight_quantity`` is the carried net itself), so a plan
#: filled and sold by hand the same day cannot be ruled out (registry net-only-read-misses-roundtrip, F-55).
UNSETTLED_ROUNDTRIP_UNREAD = "roundtrip_not_ruled_out"
#: The earlier-day outcome (``EarlierDay.outcome``): always this close reason of ``execution_plan_store`` (F-55).
EARLIER_UNRESOLVED = execution_plan_store.UNRESOLVED


class AttributionError(ValueError):
    """An input the attribution cannot read exactly; nothing is guessed (fail closed)."""


class OrderRow(Protocol):
    """One row of Zerodha's order book as ``kite_replies.orders_from_reply`` parsed it (``BrokerOrderRow``); named by
    shape so this module imports no Kite module (REQ-063 AC-1)."""

    tag: str | None
    tradingsymbol: str
    side: Action
    quantity: int
    filled_quantity: int
    status: str


@dataclass(frozen=True)
class StoreReader:
    """The read seam: every strategy of a user, every stored plan of one strategy and every stored mismatch of one
    strategy. The defaults are the stores the routes use; a test injects a fake with the same three calls (accepted
    only under ``APP_ENV=test``)."""

    list_strategies: ListStrategies = strategy_store.list_strategies
    plans_for: PlansFor = execution_plan_store.plans_for
    mismatches_for: MismatchesFor = reconciliation_store.mismatches_for


@dataclass(frozen=True)
class Account:
    """Whose strategies are read: the database connection and the user."""

    conn: object
    user_ref: str


@dataclass(frozen=True)
class Sources:
    """Where keys, time and the stored plans come from: the catalogue (stored instrument ids -> contract keys), the
    platform clock compare checks ``at`` against, and the store reader."""

    catalogue: Catalogue
    clock: Callable[[], datetime.datetime]
    reader: StoreReader = field(default_factory=StoreReader)


@dataclass(frozen=True)
class Pending:
    """Why one contract is pending: whose plan (open, or closed and contradicted by today's book), which order (tag)
    and the reason (a ``PENDING_*`` value)."""

    strategy_id: str
    plan_number: int
    tag: str
    reason: str


@dataclass(frozen=True)
class Attribution:
    """The comparison and what was set apart before it.

    ``raw_net``: Zerodha's net units per contract, as read (flat rows dropped; pending contracts kept: Zerodha's
    quantity "not yet confirmed"). ``compared_net``: what compare was given (``raw_net`` minus ``outside``, without
    pending contracts). ``outside``: the outside lots per contract, signed (never on a pending contract).
    ``held``: each holding strategy's own units per contract (``held_units``, open plans' final fills included), by
    strategy id (text, compare's id), without pending contracts. ``standalone_unseen``: the part of a recorded
    standalone quantity Zerodha does not show, per contract (not on a pending contract). ``pending``: contract ->
    every reason it is pending. ``blocked``: compare's blocked strategies plus every strategy with a pending plan or
    with units on a pending contract. ``report``: compare's report on ``compared_net`` (unchanged)."""

    report: ReconciliationReport
    raw_net: Mapping[ContractKey, int]
    compared_net: Mapping[ContractKey, int]
    outside: Mapping[ContractKey, int]
    held: Mapping[str, Mapping[ContractKey, int]]
    standalone_unseen: Mapping[ContractKey, int]
    pending: Mapping[ContractKey, tuple[Pending, ...]]
    blocked: frozenset[str]
    #: #352-1: contract -> each earlier-day open plan that cannot be settled there (``Pending.reason`` is an
    #: ``UNSETTLED_*`` value). Never pending (its tags are not in today's book, so it would wait forever): left out
    #: of compare like a pending contract, its strategy and every holder there blocked (a recorded mismatch once
    #: ``next_day_resolution`` writes it).
    unresolved: Mapping[ContractKey, tuple[Pending, ...]] = MappingProxyType({})
    #: #352-1 round 2: contract -> the strategies with an unresolved STORED mismatch there (``mismatches_for``, no
    #: settling resolution). Left out of compare like a pending contract, nothing on it is outside, and those
    #: strategies plus every holder there are blocked (Q224) until a settling resolution is recorded.
    stored: Mapping[ContractKey, tuple[str, ...]] = MappingProxyType({})


@dataclass(frozen=True)
class EarlierDayContract:
    """One contract an earlier-day open plan touches. ``expected_units``: what every strategy's stored fills plus the
    standalone say Zerodha holds WITHOUT this plan (the base: this strategy's other plans included). ``zerodha_units``:
    Zerodha's net as read. ``planned_units``: the plan's orders, signed, had they filled in full; ``gross_units``:
    their quantities, unsigned. ``reason``: the ``UNSETTLED_*`` value (``decide_earlier_day`` sets one on every
    contract, F-55). ``instrument_ids``: the plan's stored ids on this contract, sorted."""

    key: ContractKey
    instrument_ids: tuple[str, ...]
    tags: tuple[str, ...]
    expected_units: int
    zerodha_units: int
    planned_units: int
    gross_units: int
    reason: str | None


@dataclass(frozen=True)
class EarlierDay:
    """The decision for one earlier-day open plan: ``outcome`` is always ``EARLIER_UNRESOLVED`` (F-55: the next-day
    net cannot rule out a fill sold by hand the same day), and every contract carries an ``UNSETTLED_*`` reason."""

    strategy_id: int
    plan_number: int
    action: str
    outcome: str
    contracts: tuple[EarlierDayContract, ...]


def earlier_day_open(plan: StoredPlan, book: Mapping[str, Sequence[OrderRow]], today: datetime.date) -> bool:
    """An OPEN plan created before today's IST date whose tags are ALL absent from today's book (Kite's book holds
    today's orders only, so it can never end ADR-110's wait). A tag present today (e.g. an order placed late the
    evening before, shown in today's book) keeps the plan on the order-book path. A stamp without a time zone is
    refused: the day cannot be told, and a same-day plan must never be decided from the net."""
    if plan.status != "open":
        return False
    created = plan.created_at
    if not isinstance(created, datetime.datetime) or created.tzinfo is None or created.utcoffset() is None:
        raise AttributionError(f"strategy {plan.strategy_id} plan {plan.plan_number}: created_at must be a "
                               f"time-zone-aware datetime, got {created!r}")
    session = er.created_session(plan, today)
    if session == er.SESSION_FUTURE:
        raise AttributionError(f"strategy {plan.strategy_id} plan {plan.plan_number}: created_at {created!r} is after "
                               f"today's IST session {today}: refused, nothing is decided from a future stamp")
    if session != er.SESSION_EARLIER:
        return False
    return not any(order.tag in book for order in plan.orders)


def _expired(key: ContractKey, at: datetime.datetime) -> bool:
    expiry = key[3]
    if not isinstance(expiry, datetime.date):
        raise AttributionError(f"contract {key!r} has no expiry date")
    return at >= datetime.datetime.combine(expiry, EXPIRY_CLOSE)


def _signed(order: PlanOrder) -> int:
    return order.quantity if order.transaction_type == Action.BUY.value else -order.quantity


def decide_earlier_day(  # noqa: PLR0913 every input is a separately read fact
    plan: StoredPlan, underlying: str, expected: Mapping[ContractKey, int], raw_net: Mapping[ContractKey, int],
    shared: frozenset, catalogue: Catalogue, at: datetime.datetime, *, held_elsewhere: frozenset = frozenset(),
) -> EarlierDay:
    """#352-1, ADR-109 (2), ADR-111, F-55: Zerodha's next-day reply shows only the net, and a net equal to
    ``expected`` (the base without this plan) cannot rule out a fill sold by hand the same day, so the plan is
    ``unresolved_from_positions`` on every path (a contract expired at ``at``, shared, held elsewhere, mixed sides,
    changed net, or net equal to the base), never ``nothing_placed``. Never ``filled`` or ``exited`` either (the
    next-day net cannot tell the plan's fills from outside lots or a hand close on Kite)."""
    by_key: dict[ContractKey, list[PlanOrder]] = {}
    for order in plan.orders:
        by_key.setdefault(instrument_key(catalogue, order.instrument_id, underlying), []).append(order)
    contracts = []
    for key, orders in sorted(by_key.items(), key=lambda item: repr(item[0])):
        base, net = expected.get(key, 0), raw_net.get(key, 0)
        if _expired(key, at):
            reason: str | None = UNSETTLED_EXPIRED
        elif key in shared:
            reason = UNSETTLED_SHARED
        elif key in held_elsewhere:
            reason = UNSETTLED_HELD_ELSEWHERE
        elif len({order.transaction_type for order in orders}) != 1:
            reason = UNSETTLED_MIXED_SIDES
        elif net != base:
            reason = UNSETTLED_NET_CHANGED
        else:
            reason = UNSETTLED_ROUNDTRIP_UNREAD  # net == base cannot rule out a fill sold by hand (F-55)
        contracts.append(EarlierDayContract(
            key, tuple(sorted({o.instrument_id for o in orders})), tuple(o.tag for o in orders), base, net,
            sum(_signed(o) for o in orders), sum(o.quantity for o in orders), reason))
    outcome = EARLIER_UNRESOLVED
    return EarlierDay(plan.strategy_id, plan.plan_number, plan.action, outcome, tuple(contracts))


def instrument_key(catalogue: Catalogue, instrument_id: str, underlying: str) -> ContractKey:
    """A stored plan order's ``instrument_id`` text ("NSE_FO:47189") -> the reconcile key, through the catalogue.

    Refused: text that is not exactly ``segment:token`` with a plain positive token, an id the catalogue does not
    hold, and a contract of another underlying than the strategy's."""
    segment, colon, token = instrument_id.partition(":") if isinstance(instrument_id, str) else ("", "", "")
    if not colon or not token.isascii() or not token.isdigit() or token.startswith("0"):
        raise AttributionError(f"instrument_id must be 'segment:token', got {instrument_id!r}")
    try:
        iid = InstrumentId(segment, int(token))
    except ValueError as exc:
        raise AttributionError(f"instrument_id {instrument_id!r}: {exc}") from None
    entry = catalogue.get(iid)
    if entry is None:
        raise AttributionError(f"instrument_id {instrument_id!r} is not in the catalogue")
    if entry.contract.name != underlying:
        raise AttributionError(f"instrument_id {instrument_id!r} is {entry.contract.name}, not {underlying}")
    return ep.contract_key(catalogue, iid, underlying)


def key_text(catalogue: Catalogue, key: ContractKey) -> str:
    """The one stored text of a contract (``reconciliation_store`` contract_key): the smallest ``segment:token`` of
    every catalogue id whose reconcile key is ``key``, so two stored ids of one contract are one key (#352-1 round 2
    MINOR 4). Refused: a key no catalogue id has."""
    underlying, kind, _, expiry = key
    ids = sorted((c.id.exchange_segment, c.id.exchange_token) for c in catalogue.contracts_for(underlying, expiry,
                                                                             frozenset({kind.value}))
                 if ep.contract_key(catalogue, c.id, underlying) == key)
    if not ids:
        raise AttributionError(f"contract {key!r} has no instrument in the catalogue")
    return f"{ids[0][0]}:{ids[0][1]}"


async def _stored_unresolved(reader: StoreReader, account: Account, summary: StrategySummary, catalogue: Catalogue,
                             into: tuple[dict[ContractKey, set[str]], set[str]]) -> None:
    """Adds the strategy to ``into[0]`` on the contract of each of its unresolved stored mismatches, and to ``into[1]``
    when one names no catalogue contract (its strategy is blocked all the same; Zerodha's net cannot carry an id the
    catalogue lacks)."""
    strategy_id, underlying = summary.id, summary.underlying
    rows = await reader.mismatches_for(account.conn, account.user_ref, strategy_id)
    if not isinstance(rows, (list, tuple)):
        raise AttributionError(f"the store gave {rows!r} for strategy {strategy_id}'s mismatches, not a sequence")
    keys: set[ContractKey] = set()
    unmapped = False
    for row in rows:
        if type(row) is not StoredMismatch or row.strategy_id != strategy_id:
            raise AttributionError(f"strategy {strategy_id}: {row!r} is not one of its stored mismatches")
        if row.resolution is not None:
            continue
        try:
            keys.add(instrument_key(catalogue, row.contract_key, underlying))
        except AttributionError:
            unmapped = True
    for key in keys:
        into[0].setdefault(key, set()).add(str(strategy_id))
    if unmapped:
        into[1].add(str(strategy_id))


def _check_plans(strategy_id: int, plans: object) -> None:
    """Every plan is this strategy's, numbered once, and every order's tag decodes to this strategy and plan."""
    if not isinstance(plans, (tuple, list)):
        raise AttributionError(f"strategy {strategy_id}: the store must return a sequence of plans, got {plans!r}")
    numbers: set[int] = set()
    for plan in plans:
        if not isinstance(plan, StoredPlan):
            raise AttributionError(f"strategy {strategy_id}: a plan must be a StoredPlan, got {plan!r}")
        if plan.strategy_id != strategy_id:
            raise AttributionError(f"plan {plan.plan_number} belongs to strategy {plan.strategy_id}, not {strategy_id}")
        if plan.plan_number in numbers:
            raise AttributionError(f"strategy {strategy_id}: plan {plan.plan_number} appears twice")
        numbers.add(plan.plan_number)
        tags = [order.tag for order in plan.orders]
        if len(set(tags)) != len(tags):
            raise AttributionError(f"strategy {strategy_id} plan {plan.plan_number}: two orders carry one tag {tags!r}")
        for order in plan.orders:
            try:
                tag = parse_tag(order.tag)
            except ValueError:
                raise AttributionError(f"strategy {strategy_id} plan {plan.plan_number}: {order.tag!r} is not an "
                                       "order tag of this app") from None
            if (tag.strategy_id, tag.plan_version) != (strategy_id, plan.plan_number):
                raise AttributionError(f"strategy {strategy_id} plan {plan.plan_number}: tag {order.tag!r} is another "
                                       "strategy's or plan's order")


def _whole(value: object, name: str, low: int) -> int:
    if type(value) is not int or value < low:
        raise AttributionError(f"order-book {name} must be an int >= {low}, got {value!r}")
    return value


def rows_by_tag(order_book: object) -> dict[str, list[OrderRow]]:
    """Zerodha's parsed order book -> its rows by tag (rows without a tag are not this app's). Every row is checked
    again (the shape ``orders_from_reply`` gives); anything else is refused, never skipped."""
    if not isinstance(order_book, (tuple, list)):
        raise AttributionError(f"the order book must be a sequence of parsed rows, got {order_book!r}")
    by_tag: dict[str, list[OrderRow]] = {}
    for row in order_book:
        tag = getattr(row, "tag", None)
        if tag is not None and (type(tag) is not str or not tag):
            raise AttributionError(f"an order-book tag must be non-empty text or None, got {tag!r}")
        if type(getattr(row, "tradingsymbol", None)) is not str or type(getattr(row, "status", None)) is not str:
            raise AttributionError(f"an order-book row needs a trading symbol and a status, got {row!r}")
        if not isinstance(getattr(row, "side", None), Action):
            raise AttributionError(f"an order-book side must be an Action, got {row!r}")
        quantity = _whole(getattr(row, "quantity", None), "quantity", 1)
        if _whole(getattr(row, "filled_quantity", None), "filled_quantity", 0) > quantity:
            raise AttributionError(f"an order-book row filled more than its quantity: {row!r}")
        if tag is not None:
            by_tag.setdefault(tag, []).append(row)
    return by_tag


def _row_differs(order: PlanOrder, rows: Sequence[OrderRow]) -> bool:
    """A row carries the order's tag but not its side, trading symbol or quantity: not the order we stored."""
    return any((row.side.value, row.tradingsymbol, row.quantity)
               != (order.transaction_type, order.tradingsymbol, order.quantity) for row in rows)


def _read_closed_plan(plan: StoredPlan, book: Mapping[str, Sequence[OrderRow]]) -> list[tuple[str, str]]:
    """One CLOSED plan against today's book: the (tag, reason) of every order the book contradicts. A tag absent
    today (an earlier day's order) says nothing: the stored fill stands. The drift rule is
    ``execution_return.drifted`` (status not final, or a fill other than the one stored at close), asked per order."""
    today = er.TodaysBook({tag: tuple(rows) for tag, rows in book.items()}, (), {}, (), frozenset())
    reasons: list[tuple[str, str]] = []
    for order in plan.orders:
        if _row_differs(order, book.get(order.tag, ())):
            reasons.append((order.tag, PENDING_ROW_DIFFERS))
        elif er.drifted((dataclasses.replace(plan, orders=(order,)),), today):
            reasons.append((order.tag, PENDING_CLOSED_DRIFTED))
    return reasons


def _read_open_plan(plan: StoredPlan,
                    book: Mapping[str, Sequence[OrderRow]]) -> tuple[StoredPlan, list[tuple[str, str]]]:
    """One OPEN plan against Zerodha's order book (module docstring): the plan with each order's fill from its final
    row (in memory), and the (tag, reason) of every order that keeps it pending (empty: every order is final)."""
    reasons: list[tuple[str, str]] = []
    orders = []
    for order in plan.orders:
        rows = book.get(order.tag, ())
        if _row_differs(order, rows):
            reasons.append((order.tag, PENDING_ROW_DIFFERS))
        elif not rows:
            reasons.append((order.tag, PENDING_ABSENT))
        elif len(rows) > 1:
            reasons.append((order.tag, PENDING_DUPLICATE_TAG))
        elif rows[0].status not in ep.TERMINAL_ORDER_STATUSES:
            reasons.append((order.tag, PENDING_NOT_FINAL))
        else:
            orders.append(dataclasses.replace(order, filled_quantity=rows[0].filled_quantity))
    if reasons:
        return plan, reasons
    return dataclasses.replace(plan, orders=tuple(orders)), []


def _strategy_units(  # noqa: PLR0913 the strategy's facts plus today's date
        strategy_id: int, underlying: str, plans: object, book: Mapping[str, Sequence[OrderRow]],
        catalogue: Catalogue, today: datetime.date,
                    ) -> tuple[dict[ContractKey, int], dict[ContractKey, list[Pending]], list[StoredPlan]]:
    """The strategy's held units per contract (closed plans' stored fills, open plans' final fills), the contracts
    its pending plans (open or drifted closed) touch, and its earlier-day open plans (``earlier_day_open``: counted
    as 0 here, decided by ``decide_earlier_day``, never pending)."""
    _check_plans(strategy_id, plans)
    counted: list[StoredPlan] = []
    pending: dict[ContractKey, list[Pending]] = {}
    earlier: list[StoredPlan] = []
    for plan in plans:  # type: ignore[attr-defined]  # a checked sequence of StoredPlan
        if plan.status not in ("open", "closed"):
            raise AttributionError(f"strategy {strategy_id} plan {plan.plan_number}: status {plan.status!r}")
        if earlier_day_open(plan, book, today):
            earlier.append(plan)
            continue
        if plan.status == "closed":
            read, reasons = plan, _read_closed_plan(plan, book)
        else:
            read, reasons = _read_open_plan(plan, book)
        if not reasons:
            counted.append(read)
            continue
        entries = [Pending(str(strategy_id), plan.plan_number, tag, reason) for tag, reason in reasons]
        for key in {instrument_key(catalogue, order.instrument_id, underlying) for order in plan.orders}:
            pending.setdefault(key, []).extend(entries)  # every contract the plan touches, final orders' included
    held: dict[ContractKey, int] = {}
    for instrument_id, units in ep.held_units(counted).items():
        key = instrument_key(catalogue, instrument_id, underlying)
        held[key] = held.get(key, 0) + units  # two stored ids of ONE contract add up: Zerodha nets them as one
    return {key: units for key, units in held.items() if units}, pending, earlier


def _record(underlying: str, held: Mapping[ContractKey, int], at: datetime.datetime,
            clock: Callable[[], datetime.datetime]) -> StrategyRecord:
    """An in-memory record whose ACTIVE version's intended position IS the held units (versions.py:156-157)."""
    legs = tuple(DefinitionLeg(Action.BUY if units > 0 else Action.SELL, kind, strike, expiry, abs(units))
                 for (_, kind, strike, expiry), units in held.items())
    return StrategyRecord.from_held(StrategyDefinition(underlying, legs), at=at, actor=_ACTOR, clock=clock)


def split_outside(raw_net: Mapping[ContractKey, int], held: Mapping[str, Mapping[ContractKey, int]],
                  standalone: Mapping[ContractKey, int]) -> dict[ContractKey, int]:
    """The outside lots per contract (module docstring rule, outside cap included). Pure; every input is signed
    units."""
    outside: dict[ContractKey, int] = {}
    for contract, broker in raw_net.items():
        own = [units.get(contract, 0) for units in held.values()]
        alone = standalone.get(contract, 0)
        expected = sum(own) + alone
        sides = {units > 0 for units in own if units} or ({alone > 0} if alone else set())
        excess = broker - expected
        if not sides:
            surplus = broker  # in no strategy and not standalone: all of it is outside
        elif sides == {True, False}:
            surplus = 0  # strategies on both sides: a surplus is a shortfall for one of them (Q224 blocks all)
        elif excess and (excess > 0) in sides:
            if not expected or (expected > 0) not in sides:
                # The outside cap: an opposite standalone outweighs the strategies; only Zerodha's units beyond the
                # strategies' own can be outside (never more than Zerodha holds).
                beyond = broker - sum(own)
                surplus = beyond if beyond and (beyond > 0) in sides else 0
            else:
                surplus = excess  # more than expected, in the holders' direction: outside lots
        else:
            surplus = 0  # shortfall, flat or opposite side: compare decides (AC-6)
        if surplus:
            outside[contract] = surplus
    return outside


def standalone_unseen(raw_net: Mapping[ContractKey, int], held: Mapping[str, Mapping[ContractKey, int]],
                      standalone: Mapping[ContractKey, int],
                      outside: Mapping[ContractKey, int]) -> dict[ContractKey, int]:
    """The part of each recorded standalone quantity Zerodha does not show: what is left of Zerodha's net after the
    strategies' units and the outside lots, on the standalone's side, covers at most the standalone; the rest is
    unseen. Pure; signed units. Example: own +65, standalone -100, Zerodha +65, 0 outside -> 0 left -> -100 unseen."""
    unseen: dict[ContractKey, int] = {}
    for contract, alone in standalone.items():
        if not alone:
            continue
        left = (raw_net.get(contract, 0) - sum(units.get(contract, 0) for units in held.values())
                - outside.get(contract, 0))
        sign = 1 if alone > 0 else -1
        seen = sign * min(abs(alone), max(0, sign * left))
        if alone - seen:
            unseen[contract] = alone - seen
    return unseen


def _check_reader(reader: object) -> StoreReader:
    """Only the stores the routes use read the plans, except a test fake under ``APP_ENV`` exactly ``test``."""
    if type(reader) is not StoreReader:
        raise AttributionError(f"sources must carry a StoreReader, got {reader!r}")
    is_default = (reader.list_strategies is strategy_store.list_strategies
                  and reader.plans_for is execution_plan_store.plans_for
                  and reader.mismatches_for is reconciliation_store.mismatches_for)
    if not is_default and app_env() != _TEST_ENV:
        raise AttributionError("a store reader other than the plan and strategy stores is accepted only under "
                               "APP_ENV=test")
    return reader


async def attribute_and_compare(  # noqa: PLR0913 the account, Zerodha's two replies, standalone, sources
    account: Account,
    standalone: Mapping[ContractKey, int],
    broker_net: Mapping[ContractKey, int],
    order_book: Sequence[OrderRow],
    sources: Sources,
    *,
    at: datetime.datetime,
    today: datetime.date | None = None,
) -> Attribution:
    """Read every strategy of the account and all its plans, compute held units (open plans from Zerodha's order
    book), set the pending contracts and the outside lots of Zerodha's net apart, then run compare. ``today``: the
    IST session date an open plan's ``created_at`` is judged against (``survey_account``).

    ``standalone``: the recorded standalone units per contract. ``broker_net``: Zerodha's net units per contract from
    ``kite_replies.positions_from_reply`` (a flat row is absent: Zerodha holds 0; an unreadable reply raises there,
    before this runs). ``order_book``: today's order book from ``kite_replies.orders_from_reply``. Any malformed
    input raises ``ValueError`` (``AttributionError``, ``ReconciliationError``); a guessed zero never reaches
    compare."""
    survey = await survey_account(account, standalone, broker_net, order_book, sources, at=at, today=today)
    clock, alone, raw_net, known, pending = sources.clock, survey.alone, survey.raw_net, survey.known, survey.pending
    unresolved: dict[ContractKey, list[Pending]] = {}
    for decision in survey.earlier:
        for contract in decision.contracts:
            if contract.reason:
                unresolved.setdefault(contract.key, []).extend(
                    Pending(str(decision.strategy_id), decision.plan_number, tag, contract.reason)
                    for tag in contract.tags)
    stored = survey.stored
    excluded = set(pending) | set(unresolved) | set(stored)
    blocked_by_pending = {entry.strategy_id for entries in (*pending.values(), *unresolved.values())
                          for entry in entries}
    blocked_by_pending |= {sid for sids in stored.values() for sid in sids} | set(survey.stored_unmapped)
    blocked_by_pending |= {sid for sid, units in known.items() if any(units.get(key) for key in excluded)}
    held = {sid: {k: u for k, u in units.items() if k not in excluded} for sid, units in known.items()}
    held = {sid: units for sid, units in held.items() if units}
    records = {sid: _record(survey.underlyings[sid], units, at, clock) for sid, units in held.items()}
    net = {c: u for c, u in raw_net.items() if c not in excluded}
    alone_cmp = {c: u for c, u in alone.items() if c not in excluded}
    outside = split_outside(net, held, alone_cmp)
    unseen = standalone_unseen(net, held, alone_cmp, outside)
    compared = {c: units - outside.get(c, 0) for c, units in net.items() if units - outside.get(c, 0)}
    report = compare(compared, records, alone_cmp, at=at, clock=clock)
    return Attribution(
        report, MappingProxyType(raw_net), MappingProxyType(compared), MappingProxyType(outside),
        MappingProxyType({sid: MappingProxyType(u) for sid, u in held.items()}), MappingProxyType(unseen),
        MappingProxyType({key: tuple(entries) for key, entries in pending.items()}),
        frozenset(report.blocked_strategy_ids) | frozenset(blocked_by_pending),
        MappingProxyType({key: tuple(entries) for key, entries in unresolved.items()}), stored)


@dataclass(frozen=True)
class Survey:
    """What one read of the account gives (``survey_account``): the checked standalone and net maps, each strategy's
    held units WITHOUT its earlier-day open plans, the pending contracts, and the decision for every earlier-day
    open plan."""

    alone: Mapping[ContractKey, int]
    raw_net: Mapping[ContractKey, int]
    known: Mapping[str, Mapping[ContractKey, int]]
    underlyings: Mapping[str, str]
    pending: Mapping[ContractKey, tuple[Pending, ...]]
    earlier: tuple[EarlierDay, ...]
    #: contract -> strategies with an unresolved stored mismatch there; strategies whose unresolved mismatch names
    #: no catalogue contract (blocked, nothing to exclude).
    stored: Mapping[ContractKey, tuple[str, ...]] = MappingProxyType({})
    stored_unmapped: frozenset[str] = frozenset()


def _session_date(at: datetime.datetime, today: object) -> datetime.date:
    """The IST session date plans are judged against: ``today`` when given (a plain date; a datetime is refused,
    never truncated), else ``at``'s IST date."""
    if today is None:
        return at.astimezone(IST).date()
    if isinstance(today, datetime.datetime) or not isinstance(today, datetime.date):
        raise AttributionError(f"today must be a date, got {today!r}")
    return today


async def survey_account(  # noqa: PLR0913 the attribution's own inputs
    account: Account,
    standalone: Mapping[ContractKey, int],
    broker_net: Mapping[ContractKey, int],
    order_book: Sequence[OrderRow],
    sources: Sources,
    *,
    at: datetime.datetime,
    today: datetime.date | None = None,
) -> Survey:
    """Read every strategy and all its plans (the store reader), compute held units and pending contracts, and decide
    every earlier-day open plan (``decide_earlier_day``) against the base of every OTHER stored fill plus the
    standalone. ``at`` must be time-zone aware. ``today`` is the IST session date a plan's ``created_at`` is judged
    against; the routes pass the date of the clock that stamped ``created_at`` (the database's, #380-2), because a
    request clock on another date would call a plan stamped today "from the future" and refuse the whole account.
    Without it, today's session is ``at``'s IST date. A ``today`` that is not a plain date is refused."""
    if not isinstance(account, Account) or not isinstance(account.user_ref, str) or not account.user_ref.strip():
        raise AttributionError(f"account must be an Account with a user, got {account!r}")
    if not isinstance(sources, Sources):
        raise AttributionError(f"sources must be a Sources with a StoreReader, got {sources!r}")
    if not isinstance(at, datetime.datetime) or at.tzinfo is None or at.utcoffset() is None:
        raise AttributionError(f"at must be a time-zone-aware datetime, got {at!r}")
    today = _session_date(at, today)
    catalogue, reader = sources.catalogue, _check_reader(sources.reader)
    alone = units_map(standalone, "standalone quantities")
    raw_net = units_map(broker_net, "broker net positions")
    book = rows_by_tag(order_book)
    summaries = await reader.list_strategies(account.conn, account.user_ref)
    if not isinstance(summaries, (list, tuple)) or len(summaries) > MAX_STRATEGIES:
        raise AttributionError(f"the store must list at most {MAX_STRATEGIES} strategies, got {summaries!r}")
    known: dict[str, dict[ContractKey, int]] = {}
    underlyings: dict[str, str] = {}
    pending: dict[ContractKey, list[Pending]] = {}
    earlier: list[tuple[StoredPlan, str]] = []
    stored: dict[ContractKey, set[str]] = {}
    unmapped: set[str] = set()
    seen: set[int] = set()
    for summary in summaries:
        if not isinstance(summary, StrategySummary):
            raise AttributionError(f"the store listed {summary!r}, not a StrategySummary")
        strategy_id = summary.id
        if isinstance(strategy_id, bool) or not isinstance(strategy_id, int) or strategy_id <= 0:
            raise AttributionError(f"a strategy id must be a positive int, got {strategy_id!r}")
        if strategy_id in seen:
            raise AttributionError(f"the store listed strategy {strategy_id} twice")
        seen.add(strategy_id)
        plans = await reader.plans_for(account.conn, account.user_ref, strategy_id)
        units, waiting, old = _strategy_units(strategy_id, summary.underlying, plans, book, catalogue, today)
        known[str(strategy_id)], underlyings[str(strategy_id)] = units, summary.underlying
        earlier.extend((plan, summary.underlying) for plan in old)
        for key, entries in waiting.items():
            pending.setdefault(key, []).extend(entries)
        await _stored_unresolved(reader, account, summary, catalogue, (stored, unmapped))
    decisions = _decide_all(earlier, alone, raw_net, known, frozenset(pending) | frozenset(stored), catalogue, at)
    return Survey(MappingProxyType(alone), MappingProxyType(raw_net),
                  MappingProxyType({sid: MappingProxyType(u) for sid, u in known.items()}),
                  MappingProxyType(underlyings),
                  MappingProxyType({key: tuple(entries) for key, entries in pending.items()}), tuple(decisions),
                  MappingProxyType({key: tuple(sorted(sids)) for key, sids in stored.items()}), frozenset(unmapped))


def _decide_all(  # noqa: PLR0913 every input is a separately read fact
    earlier: Sequence[tuple[StoredPlan, str]], alone: Mapping[ContractKey, int], raw_net: Mapping[ContractKey, int],
    known: Mapping[str, Mapping[ContractKey, int]], pending: frozenset, catalogue: Catalogue, at: datetime.datetime,
) -> tuple[EarlierDay, ...]:
    """Every earlier-day plan's decision. The base per contract is the standalone plus every strategy's counted
    units. A contract is shared when it is pending or carries an unresolved stored mismatch (``pending`` here), two
    earlier-day plans touch it, or ANOTHER strategy holds units on it (Q224, #352-1 round 2 MINOR 3: S1's plan
    filled and S2's lots sold by hand leave the net at the base, so "nothing changed" cannot be read)."""
    expected: dict[ContractKey, int] = dict(alone)
    for units in known.values():
        for key, value in units.items():
            expected[key] = expected.get(key, 0) + value
    touches: dict[ContractKey, int] = {}  # how many earlier-day plans touch each contract
    for plan, underlying in earlier:
        for key in {instrument_key(catalogue, o.instrument_id, underlying) for o in plan.orders}:
            touches[key] = touches.get(key, 0) + 1
    shared = pending | frozenset(k for k, count in touches.items() if count > 1)
    return tuple(decide_earlier_day(plan, underlying, expected, raw_net, shared, catalogue, at,
                                    held_elsewhere=other_holders(known, str(plan.strategy_id)))
                 for plan, underlying in earlier)


def other_holders(known: Mapping[str, Mapping[ContractKey, int]], strategy_id: str) -> frozenset:
    """The contracts on which a strategy other than ``strategy_id`` holds units (its counted stored fills)."""
    return frozenset(key for sid, units in known.items() if sid != strategy_id for key, value in units.items()
                     if value)


def holders(known: Mapping[str, Mapping[ContractKey, int]], key: ContractKey) -> tuple[int, ...]:
    """Every strategy holding units on ``key`` by its counted stored fills (read from the stores, never a caller's)."""
    return tuple(sorted(int(sid) for sid, units in known.items() if units.get(key)))


__all__ = ["EARLIER_UNRESOLVED", "PENDING_ABSENT", "PENDING_CLOSED_DRIFTED",
           "PENDING_DUPLICATE_TAG", "PENDING_NOT_FINAL", "PENDING_ROW_DIFFERS", "UNSETTLED_EXPIRED",
           "UNSETTLED_HELD_ELSEWHERE", "UNSETTLED_MIXED_SIDES", "UNSETTLED_NET_CHANGED", "UNSETTLED_SHARED", "Account",
           "Attribution", "AttributionError", "EarlierDay", "EarlierDayContract", "OrderRow", "Pending", "Sources",
           "StoreReader", "Survey", "attribute_and_compare", "decide_earlier_day", "earlier_day_open", "holders",
           "instrument_key", "key_text", "other_holders", "rows_by_tag", "split_outside", "standalone_unseen",
           "survey_account"]
