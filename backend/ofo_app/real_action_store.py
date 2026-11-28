"""The record book of a REAL position (Lane R1; ADR-330 (73), ADR-281, ADR-016 to ADR-019). Schema: migration 0065.

What a user stores for a real position (open, add, exit, stop) and what the worker stores when a stop is reached
(stop_fired) is one append-only row here, NEVER a paper order: the position, its quantity and its P&L stay the
broker's figure (ADR-016 to ADR-019), so no reader of the paper book, the P&L or the adjustments ever sees a record.
Nothing here is sent to a broker; there is no broker column and no broker call in this module.

- record: one row per (request, action), legs as JSON with every price as Decimal text. A repeated request key stores
  nothing a second time (unique (user_ref, request_key, action)). A stop_fired is claimed once per trigger (unique).
- load / latest: read back, oldest first / the newest of a strategy.
Answer states of ``latest``: no record -> None; a read that fails PROPAGATES (the caller never reads it as "none").
"""
from __future__ import annotations

import dataclasses
import datetime
import json
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any, Final, Literal

from ofo.errors.explanations import ExplanationText, render_explanation
from ofo.outcome.price_text import price_text
from sqlalchemy import text

from ofo_app.api_models import ApiModel, CatalogueText, Money

ACTIONS: Final = ("open", "add", "exit", "stop", "stop_fired")
#: the order kinds a user door can store as a record (the others are the server's own kinds)
USER_ACTIONS: Final = frozenset({"open", "add", "exit"})

_INSERT = text(
    "INSERT INTO public.real_action_records (user_ref, strategy_id, action, legs, reason, trigger_id, request_key, "
    "stored_at) VALUES (:user_ref, :strategy_id, :action, CAST(:legs AS JSONB), :reason, :trigger_id, "
    "CAST(:request_key AS UUID), :stored_at)")
_SELECT = text(
    "SELECT id, strategy_id, action, legs, reason, trigger_id, stored_at FROM public.real_action_records "
    "WHERE strategy_id = :strategy_id ORDER BY id")
_SELECT_KEY = text(
    "SELECT id, strategy_id, action, legs, reason, trigger_id, stored_at FROM public.real_action_records "
    "WHERE user_ref = :user_ref AND request_key = CAST(:request_key AS UUID) ORDER BY id")


@dataclasses.dataclass(frozen=True)
class Leg:
    """One leg of a stored action: the contract, the side, the quantity in units and the price as the user's door gave
    it (the server's live exit price for an exit). Money exact: ``price`` is a Decimal."""

    contract_id: int
    side: str
    quantity: int
    price: Decimal


@dataclasses.dataclass(frozen=True)
class Draft:
    """One order of a real position's basket as the door read it (the size checks read these fields): NOT a paper
    order (``paper_store.NewOrder`` is built only at the paper door), and never stored as one."""

    contract_id: int
    side: str
    quantity: int
    price: Decimal
    kind: str
    placed_at: datetime.datetime


@dataclasses.dataclass(frozen=True)
class StoredRecord:
    id: int
    strategy_id: int
    action: str
    legs: tuple[Leg, ...]
    reason: str | None
    trigger_id: int | None
    stored_at: datetime.datetime

    @property
    def price(self) -> Decimal | None:
        """The one price the contract's ``record.price`` carries: the first leg's (a stop has one leg; a basket's
        record shows its first leg, the legs are in the list)."""
        return self.legs[0].price if self.legs else None


_CLOSING: Final = {"BUY": "SELL", "SELL": "BUY"}


def closing_side(side: str) -> str:
    """The side that closes a leg bought (BUY) or sold (SELL) at entry; an unknown side raises (never guessed)."""
    return _CLOSING[side]


def closing_side_of_net(net_quantity: int) -> str:
    """The side that closes a signed net quantity: a long (positive) is closed by a SELL, a short by a BUY."""
    if net_quantity > 0:
        return "SELL"
    return "BUY"


def _legs_json(legs: Sequence[Leg]) -> str:
    return json.dumps([{"contract_id": leg.contract_id, "side": leg.side, "quantity": leg.quantity,
                        "price": format(leg.price, "f")} for leg in legs])


def _row(r: Any) -> StoredRecord:
    raw = r.legs if isinstance(r.legs, list) else json.loads(r.legs)
    legs = tuple(Leg(int(x["contract_id"]), str(x["side"]), int(x["quantity"]), Decimal(str(x["price"]))) for x in raw)
    return StoredRecord(int(r.id), int(r.strategy_id), str(r.action), legs, r.reason,
                        None if r.trigger_id is None else int(r.trigger_id), r.stored_at)


async def record(conn: Any, *, user_ref: str, strategy_id: int, action: str, legs: Sequence[Leg],  # noqa: PLR0913
                 stored_at: datetime.datetime, reason: str | None = None, trigger_id: int | None = None,
                 request_key: str | None = None) -> None:
    """Stores one record in the caller's transaction (the caller commits or rolls back). A bad action or an empty leg
    list raises ValueError before any write (never a guessed default). A duplicate (request key + action, or a second
    ``stop_fired`` of one trigger) is refused by the table and raises the database's integrity error."""
    if action not in ACTIONS:
        raise ValueError(f"unknown record action {action!r}")
    if not legs:
        raise ValueError("a record needs at least one leg")
    if stored_at.tzinfo is None:
        raise ValueError("a record's time must be timezone-aware")
    for leg in legs:
        if type(leg.quantity) is not int or leg.quantity <= 0 or leg.side not in _CLOSING:
            raise ValueError("a record's leg has a whole positive quantity and the side BUY or SELL")
        if not isinstance(leg.price, Decimal) or not leg.price.is_finite() or leg.price <= 0:
            raise ValueError("a record's price is a positive Decimal")
    await conn.execute(_INSERT, {
        "user_ref": user_ref, "strategy_id": strategy_id, "action": action, "legs": _legs_json(legs),
        "reason": reason, "trigger_id": trigger_id, "request_key": request_key, "stored_at": stored_at})


async def load(conn: Any, strategy_id: int) -> tuple[StoredRecord, ...]:
    return tuple(_row(r) for r in (await conn.execute(_SELECT, {"strategy_id": strategy_id})).all())


async def latest(conn: Any, strategy_id: int) -> StoredRecord | None:
    rows = await load(conn, strategy_id)
    return rows[-1] if rows else None


async def for_key(conn: Any, user_ref: str, request_key: str) -> tuple[StoredRecord, ...]:
    """The records a request key stored (a repeat answers these, never stores again)."""
    return tuple(_row(r) for r in (await conn.execute(
        _SELECT_KEY, {"user_ref": user_ref, "request_key": request_key})).all())


def record_out(rec: StoredRecord | None) -> Mapping[str, Any] | None:
    """The frozen field contract's ``record`` object: {action, stored_at, price} (price as Decimal text)."""
    if rec is None:
        return None
    return {"action": rec.action, "stored_at": rec.stored_at, "price": rec.price, "text": record_text(rec)}


def record_text(rec: StoredRecord) -> ExplanationText:
    """The one line a record carries (pending owner read): what was stored, when, at what price; never a fill."""
    price = price_text(rec.price)  # type: ignore[arg-type] - a record always has a leg
    return render_explanation(f"real_record_{rec.action}", time=rec.stored_at, price=price)


#: every wording a stored real alert body can have (the store keeps the text only, a read tries each)
REAL_ALERT_BODY_TEMPLATES: Final = ("real_alert_body_one", "real_alert_body_one_named", "real_alert_body")


def alert_body(what: ExplanationText | str, exits: Sequence[tuple[ExplanationText | str, Decimal]], *,
               names_contract: bool) -> ExplanationText:
    """The reached-stop alert of a REAL position: the paper body's three shapes with "exit stored" and "Not sent to
    Zerodha. Place it in Kite." instead of "A paper exit only"."""
    legs = [render_explanation("paper_alert_leg", contract=c, price=price_text(price)) for c, price in exits]
    if len(legs) == 1:
        if names_contract:
            return render_explanation("real_alert_body_one", what=what, price=price_text(exits[0][1]))
        return render_explanation("real_alert_body_one_named", what=what, leg=legs[0])
    joined = legs[0]
    for leg in legs[1:]:
        joined = render_explanation("paper_alert_legs", rest=joined, leg=leg)
    return render_explanation("real_alert_body", what=what, count=len(legs), prices=joined)


_LATEST_MANY = text(
    "SELECT DISTINCT ON (strategy_id) id, strategy_id, action, legs, reason, trigger_id, stored_at "
    "FROM public.real_action_records WHERE strategy_id = ANY(:ids) ORDER BY strategy_id, id DESC")


async def latest_many(conn: Any, strategy_ids: Sequence[int]) -> dict[int, StoredRecord]:
    """strategy id -> its newest record, one read; a strategy with none is absent. A failed read PROPAGATES."""
    ids = sorted(set(strategy_ids))
    if not ids:
        return {}
    return {int(r.strategy_id): _row(r) for r in (await conn.execute(_LATEST_MANY, {"ids": ids})).all()}


class RecordOut(ApiModel):
    """Lane R1: the stored record of a real position's action (ADR-330 (73)): what was stored, when and at what price.
    Nothing was sent to the broker; the price is a reminder, never a fill."""
    action: Literal["open", "add", "exit", "stop", "stop_fired"]
    stored_at: datetime.datetime
    price: Money
    text: CatalogueText  # the record's one line, e.g. "Exit stored 10:05 at 39.15. Not sent to Zerodha. ..."
