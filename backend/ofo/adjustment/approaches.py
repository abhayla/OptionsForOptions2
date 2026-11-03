"""Adjustment approach builder (REQ-155 AC-1, AC-8; ADR-214; goal contract GC-ADJ1 "Design decisions").

For a tracked iron condor and one picked approach this module builds the EXACT trades, the After legs and the legs the
approach closes (with entry and planned exit, so the caller can book their P&L, F-74). It computes no money figure of
the trade (ADR-008): pricing the After is the one engine's job. Suggest-only (ADR-003): nothing here places an order.
Every text a user can see comes from the reviewed catalogue (``render`` templates ``adjust_*`` and the
``adjustment_approach`` label table); this module holds no sentence of its own.

Rules (each one decided here and stated, catalogue Part 2 followed where the contract is silent):

- Shape: an iron condor = one short CE, one long CE above it, one short PE, one long PE below it, one expiry. Any other
  shape: A-36 and A-31 still build (they work for every legs list); the side approaches are refused with a reason.
- Tested side (contract): the side whose short is nearer spot in percent. Both distances are divided by the same spot,
  so this is the nearer one in points. Equal distances: the CALL side is tested (the same tie rule as
  ``leg_edit.width``).
- Roll distance (contract): the move that brings the moved short to the playbook's Early delta (config
  ``target_short_delta`` by expiry kind). A-05 rolls the tested short OUT to the first strike beyond it whose |delta| is
  at most the target; A-01 rolls the untested short IN to the strike nearest spot whose |delta| is at most the target.
  The wing moves the same distance (width kept). When no chain row of that type and expiry carries a delta, the move
  is ``roll_points_without_delta`` of the underlying (200 NIFTY / 500 SENSEX). ``step_basis`` says which ("delta" or
  "points") and ``step_value`` the number used. A strike of the search with no delta (unquoted: nobody held it) that
  lies between the short and the strike picked, or (rolling in) the next strike past it, is a GAP: the roll is refused
  naming that strike (``adjust_no_price``), never a strike picked past it (GC-IC1 round 3); with no fitting strike and
  a gap, the gap is named too. Every contract the builder could not price is listed in ``unpriced`` so the caller can
  hold it once and build again.
- Landing: through the REQ-078 landing rule ``leg_edit.land`` (a strike not listed is refused naming the leg).
- A-01 that would put the put short above the call short (or the call short below the put short) is refused: the
  condor would be inverted. Equal shorts are allowed.
- A-29: closes ``lots // reduce_divisor`` lots of the tested short and its wing; under 2 lots it is refused (half of
  one lot is not a whole lot).
- A-11: both shorts to the ATM strike (the listed strike nearest spot, a tie goes to the higher strike), each wing
  keeps its distance from its short; refused with fewer than ``iron_fly_min_days_left`` days left.
- Planned price of every trade (ADR-241, SPEC CHANGE to ADR-068 (1) for approach trades only): the bid-ask mid when
  the row's book is live (the engine's one ADR-172 rule ``ofo.engine.model.live_book``: both sides above 0, ask at or
  above bid, health AVAILABLE), half-up to 0.01; else the row's LTP if positive, half-up to 0.01; otherwise there is
  no price and the approach is refused naming the leg (``adjust_no_price``). A stale book (after hours) keeps its
  closing LTP. A draft leg's planned entry in the builder (``ofo.outcome.planned_entry``) is NOT this rule.
- Answer states of the chain row a NEW leg lands on: listed + tradable + low-OI stated not blocked -> build; not listed
  -> refused (landing rule); not tradable -> refused; low-OI stated blocked -> refused; low-OI unknown -> a warning on
  the leg (AC-8), not a refusal; no price -> refused. A CLOSING trade needs only a price (exits are always allowed).
- Trade order: BUY trades first, then SELL (the playbook guard "buy legs first"), each group in leg order.
- The builder does not apply the playbook's adjustment limit (S-11) or the data-state hold: those are filters of the
  caller (REQ-157), so every approach is built whenever its own legs allow it.
- Exit and reduce (ADR-238): A-24 (take profit) and A-35 (time exit) close every open leg through the SAME code path as
  A-31 (``_close_all``). A-25 closes ``partial_close_percent`` % of EVERY leg's lots; refused naming the first leg
  (position order) whose share is not a whole number of lots (never rounded). A-26 buys back the untested short only
  when (entry - price) x 100 >= ``untested_decay_percent`` x entry (exact; entry <= 0 is refused, no division); its wing
  stays. A-27 buys back every short whose planned price passes T-09's own comparison against T-09's threshold of the
  current stage; A-35 is built on expiry day from the playbook's ``time_exit``. Their playbook inputs come from the
  CALLER as :class:`ExitInputs` (never a clock or a global): no T-09 -> A-27 refused ("no limit"); no ``time_exit``
  -> A-35 refused; no check time -> A-35 refused as before the time (fail closed). A short with no price: refused
  naming the leg, as every approach.
- Rolls (ADR-239): A-02 moves ONLY the tested short out by the roll distance above (``roll_distance``, the one rule);
  its wing stays, so the spread narrows; a new short at or beyond its wing is refused naming both strikes. A-04 closes
  the tested spread and opens it in the NEXT expiry the chain carries (the first later expiry of the rows passed in):
  the short by the same ``roll_distance`` read on THAT expiry's rows only, the wing at the old width; no later expiry
  in the chain -> refused naming the position's expiry; a later expiry with no priced row -> refused naming it. A-06
  steps the tested short and wing ``shift_strikes`` LISTED strikes away from spot through ``leg_edit.step_strike`` (the
  REQ-078 step rule; a gap in the listing is stepped over by the listing, never by arithmetic); no further strike or a
  strike not listed is the step rule's own refusal. Every roll passes ``guard_debit`` (ADR-230).
- Take profit (ADR-238 (6)): A-24 and A-25 are refused when the whole trade (``Position.booked`` plus every open leg
  at its planned exit price, ``adjust_money.pnl_now``) is not in profit (``adjust_money.in_profit``: above zero);
  booked P&L not known -> refused (fail closed). A-24 prices (and names an unpriced leg) first, as A-31; A-25 checks
  the profit before its whole-lots rule.
"""
from __future__ import annotations

import datetime
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Decimal
from typing import cast

from ofo.adjustment import liquidity
from ofo.engine import adjust_money
from ofo.engine.legs import Action, Instrument, Leg
from ofo.engine.model import live_book
from ofo.errors import LegValue, UserFacingError, render
from ofo.errors.explanations import (
    ADJUSTMENT_APPROACH_LABEL_TEXT,
    EXIT_REDUCE_BUILT,
    PLAYBOOK_APPROACH_LABEL_TEXT,
    ROLL_BUILT,
)
from ofo.instruments.catalogue import SUPPORTED_UNDERLYINGS, Catalogue
from ofo.instruments.models import Contract
from ofo.money import PAISE
from ofo.rules.inputs import DataHealth
from ofo.strategy import leg_edit
from ofo.strategy.leg_edit import EditLeg, LegEditRefused, Listing

APPROACH_IDS = ("A-36", "A-01", "A-05", "A-29", "A-28", "A-11", "A-31", *EXIT_REDUCE_BUILT, *ROLL_BUILT)
NO_CHANGE = APPROACH_IDS[0]  # A-36 "No change": always compared, always the first column (REQ-156 AC-1, AC-4)
NAMES = {**ADJUSTMENT_APPROACH_LABEL_TEXT,
         **{a: PLAYBOOK_APPROACH_LABEL_TEXT[a] for a in (*EXIT_REDUCE_BUILT, *ROLL_BUILT)}}
KINDS = {"A-36": "none", "A-01": "roll", "A-05": "roll", "A-29": "reduce", "A-28": "close_part", "A-11": "convert",
         "A-31": "exit", "A-24": "exit", "A-25": "reduce", "A-26": "close_part", "A-27": "close_part", "A-35": "exit",
         "A-02": "roll", "A-04": "roll", "A-06": "roll"}
_CLOSE_ALL = frozenset({"A-31", "A-24", "A-35"})  # ADR-238 (1), (5): one builder for every close-all
_HUNDRED = Decimal(100)
CALL, PUT = "call", "put"
_OPPOSITE = {"BUY": "SELL", "SELL": "BUY"}


@dataclass(frozen=True)
class Config:
    """A user's approach preferences (REQ-168 AC-1), built by ``ofo.adjustment.preferences.from_values``."""

    target_short_delta: Mapping[str, Decimal]
    roll_points_without_delta: Mapping[str, Decimal]
    iron_fly_min_days_left: int
    reduce_divisor: int
    partial_close_percent: int  # ADR-238 (2): A-25 closes this % of every leg's lots
    untested_decay_percent: int  # ADR-238 (3): A-26 needs the untested short this % below its entry
    shift_strikes: int = 1  # ADR-239 (3): A-06 steps the tested spread this many listed strikes


@dataclass(frozen=True)
class ExitInputs:
    """The playbook inputs of A-27 and A-35 (ADR-238 (4), (5)), passed in by the caller (``playbook_eval.exit_inputs``).

    ``t09`` = T-09's threshold of the current stage and its comparison ("le" / "ge"); None = T-09 off, absent or with
    no value this stage. ``time_exit`` = the playbook guard "HH:MM"; None = not set. ``hhmm`` = the check's IST clock
    "HH:MM"; None = not known."""

    t09: tuple[Decimal, str] | None = None
    time_exit: str | None = None
    hhmm: str | None = None


@dataclass(frozen=True)
class ChainRow:
    strike: Decimal
    type: str  # CE / PE
    expiry: datetime.date
    tradingsymbol: str
    ltp: Decimal | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    delta: Decimal | None = None
    listed: bool = True
    tradable: bool = True
    low_oi_state: str = "stated"  # stated / unknown
    low_oi_blocked: bool | None = False
    oi: int | None = None  # open interest; None = no source gave it (F-78), read by liquidity.evaluate_strike
    health: DataHealth | None = None  # the quote's health (ADR-241: the mid only on an AVAILABLE book); None = not known


@dataclass(frozen=True)
class PositionLeg:
    side: str  # BUY / SELL
    type: str  # CE / PE
    strike: Decimal
    expiry: datetime.date
    lots: int
    entry: Decimal
    tradingsymbol: str


@dataclass(frozen=True)
class Position:
    underlying: str
    lot: int
    expiry_kind: str  # weekly / monthly
    today: datetime.date
    legs: tuple[PositionLeg, ...]
    booked: Decimal | None = None  # the P&L already booked (ADR-238 (6)); None = not known


@dataclass(frozen=True)
class Trade:
    """A planned trade of an approach, shown for decision support; never sent from here (ADR-003)."""

    action: str
    type: str
    strike: Decimal
    expiry: datetime.date
    lots: int
    quantity: int
    price: Decimal
    tradingsymbol: str


@dataclass(frozen=True)
class ClosedLeg:
    side: str
    type: str
    strike: Decimal
    expiry: datetime.date
    lots: int
    quantity: int
    entry: Decimal
    exit: Decimal
    tradingsymbol: str


@dataclass(frozen=True)
class ApproachLegs:
    id: str
    name: str
    kind: str
    side: str  # call / put / both / none
    trades: tuple[Trade, ...] = ()
    after: tuple[PositionLeg, ...] = ()
    closed: tuple[ClosedLeg, ...] = ()
    refusal: str | None = None
    warnings: tuple[str, ...] = ()
    step_basis: str | None = None  # "delta" / "points" (rolls only)
    step_value: Decimal | None = None  # the target delta or the points moved
    #: the refusal and warnings as catalogue messages, for the API door (``refusal`` / ``warnings`` hold their text)
    refusal_message: UserFacingError | None = None
    warning_messages: tuple[UserFacingError, ...] = ()
    #: (expiry, type, strike) of every contract this build needed and found no price / no delta for (the caller's ONE
    #: second pass holds them, GC-IC1 round 3); empty when none
    unpriced: tuple[tuple[datetime.date, str, Decimal], ...] = ()


class _Refused(Exception):
    def __init__(self, message: UserFacingError) -> None:
        super().__init__(message.what_happened)
        self.reason = message.what_happened
        self.message = message


def _refusal(template: str, **slots: object) -> _Refused:
    """A refusal whose text is the catalogue template's (``render``), never a sentence of this module."""
    return _Refused(render(template, **slots))


@dataclass(frozen=True)
class _Condor:
    index: Mapping[tuple[str, str], int]  # (side, "short"/"wing") -> leg index


def is_no_change(built: ApproachLegs) -> bool:
    """The "No change" approach (A-36), whose After is the current legs."""
    return built.id == NO_CHANGE


def planned_price(row: ChainRow | None) -> Decimal | None:
    """ADR-241: the bid-ask mid when the row's book is live (``live_book``, the ADR-172 rule ``iv_price`` uses, health
    gate included), else a positive LTP, half-up to 0.01; else None (no fake price, no model price, ADR-020 Q185)."""
    if row is None:
        return None
    if live_book(row.bid, row.ask, row.health):
        return ((row.bid + row.ask) / 2).quantize(PAISE, rounding=ROUND_HALF_UP)  # type: ignore[operator]
    if row.ltp is not None and row.ltp > 0:
        return row.ltp.quantize(PAISE, rounding=ROUND_HALF_UP)
    return None


def listing_from_chain(underlying: str, lot: int, chain: Sequence[ChainRow], today: datetime.date,
                       tick: Decimal = Decimal("0.05")) -> Listing:
    """The leg_edit Listing of the strikes the chain marks listed (the route passes the instrument file's own)."""
    cat = Catalogue()
    seg = SUPPORTED_UNDERLYINGS[underlying]
    cat.load([Contract(seg, n + 1, underlying, r.expiry, r.strike, tick, lot, r.type)
              for n, r in enumerate(chain) if r.listed])
    return Listing(cat, today)


def _condor(legs: Sequence[PositionLeg]) -> _Condor | None:
    if len(legs) != 4 or len({x.expiry for x in legs}) != 1:  # noqa: PLR2004 - an iron condor has 4 legs
        return None
    found = _Condor({(CALL if x.type == "CE" else PUT, "short" if x.side == "SELL" else "wing"): i
                     for i, x in enumerate(legs)})
    if len(found.index) != 4:  # noqa: PLR2004
        return None
    cs, cw = legs[found.index[(CALL, "short")]], legs[found.index[(CALL, "wing")]]
    ps, pw = legs[found.index[(PUT, "short")]], legs[found.index[(PUT, "wing")]]
    if not (cw.strike > cs.strike and pw.strike < ps.strike and ps.strike <= cs.strike):
        return None
    return found


def tested_side(position: Position, spot: Decimal) -> str | None:
    """The side whose short is nearer spot in percent; a tie is the call side. None when not an iron condor."""
    found = _condor(position.legs)
    if found is None:
        return None
    call = position.legs[found.index[(CALL, "short")]].strike
    put = position.legs[found.index[(PUT, "short")]].strike
    return CALL if abs(call - spot) / spot <= abs(spot - put) / spot else PUT


class _Builder:
    def __init__(self, position: Position, chain: Sequence[ChainRow], spot: Decimal, config: Config,  # noqa: PLR0913
                 listing: Listing | None, limits: liquidity.Limits | None = None,
                 max_profit: Decimal | None = None) -> None:
        self.p, self.spot, self.cfg = position, spot, config
        self.rows = {(r.expiry, r.type, r.strike): r for r in chain}
        self.chain = chain
        self.listing = listing or listing_from_chain(position.underlying, position.lot, chain, position.today)
        self.warnings: list[str] = []
        self.warning_messages: list[UserFacingError] = []  # the same warnings as catalogue messages (API door)
        self.basis: tuple[str, Decimal] | None = None
        self.limits, self.max_profit = limits, max_profit  # the playbook's saved liquidity limits (ADR-230 (1))
        self.unpriced: list[tuple[datetime.date, str, Decimal]] = []

    def guard_debit(self, trades: Sequence[Trade]) -> None:
        """ADR-230 (1): a roll whose net debit is above the playbook's limit is refused, with the reason."""
        if self.limits is None:
            return
        debit = -adjust_money.trade_credit((t.action, t.price, t.quantity) for t in trades)  # ADR-008: the engine's sum
        verdict = liquidity.check_roll_debit(self.limits, debit, self.max_profit)
        if verdict.reason == "unreadable":
            raise _refusal("adjust_roll_limit_unreadable", debit=debit.quantize(PAISE, rounding=ROUND_HALF_UP))
        if not verdict.allowed:  # the verdict used the exact figures; the message's Money slots take whole paise
            raise _refusal("adjust_roll_debit_over_limit", debit=debit.quantize(PAISE, rounding=ROUND_HALF_UP),
                           limit=verdict.limit.quantize(PAISE, rounding=ROUND_HALF_UP))

    def ref(self, leg: PositionLeg) -> LegValue:
        """The leg as a message names it: its number in the position, side, contract and expiry."""
        number = next(i for i, x in enumerate(self.p.legs)  # a moved leg keeps its old symbol (A-04: a new expiry)
                      if (x.side, x.type) == (leg.side, leg.type)
                      and ((x.expiry == leg.expiry and x.strike == leg.strike) or x.tradingsymbol == leg.tradingsymbol)
                      ) + 1
        engine = Leg(Action(leg.side), Instrument(leg.type), leg.strike, leg.expiry, leg.lots * self.p.lot,
                     self.p.legs[number - 1].entry)
        return LegValue(number, engine, self.p.underlying)

    def price_of(self, leg: PositionLeg) -> Decimal:
        price = planned_price(self.rows.get((leg.expiry, leg.type, leg.strike)))
        if price is None:
            self.unpriced.append((leg.expiry, leg.type, leg.strike))
            raise _refusal("adjust_no_price", leg=self.ref(leg))
        return price

    def _gap(self, short: PositionLeg, row: ChainRow) -> _Refused:
        """A strike of the roll search with no delta: named (as the short moved there), listed for the second pass."""
        self.unpriced.append((row.expiry, row.type, row.strike))
        return _refusal("adjust_no_price", leg=self.ref(replace(short, strike=row.strike)))

    def close(self, leg: PositionLeg, lots: int) -> tuple[Trade, ClosedLeg]:
        price = self.price_of(leg)
        qty = lots * self.p.lot
        return (Trade(_OPPOSITE[leg.side], leg.type, leg.strike, leg.expiry, lots, qty, price, leg.tradingsymbol),
                ClosedLeg(leg.side, leg.type, leg.strike, leg.expiry, lots, qty, leg.entry, price, leg.tradingsymbol))

    def open(self, leg: PositionLeg) -> tuple[Trade, PositionLeg]:
        """A new contract: every answer state of its chain row (module docstring). ``leg`` keeps the old leg's
        trading symbol until it lands, so the message can number it."""
        row = self.rows.get((leg.expiry, leg.type, leg.strike))
        if row is None or not row.listed or not row.tradable:  # the landing rule already refused an unlisted strike
            raise _refusal("leg_edit_landing_not_tradable", leg=self.ref(leg))
        if row.low_oi_state == "stated" and row.low_oi_blocked:
            raise _refusal("adjust_low_oi_blocked", leg=self.ref(leg))
        if row.low_oi_state != "stated":
            warning = render("adjust_low_oi_unknown", leg=self.ref(leg))
            self.warnings.append(warning.what_happened)
            self.warning_messages.append(warning)
        price = self.price_of(leg)
        new = replace(leg, entry=price, tradingsymbol=row.tradingsymbol)
        return Trade(leg.side, leg.type, leg.strike, leg.expiry, leg.lots, leg.lots * self.p.lot, price,
                     row.tradingsymbol), new

    def edit_legs(self, moved: Mapping[int, datetime.date] | None = None) -> list[EditLeg]:
        """The position as leg_edit reads it; ``moved`` puts a leg on another expiry (A-04) before it lands."""
        moved = moved or {}
        return [EditLeg(Leg(Action(x.side), Instrument(x.type), x.strike, moved.get(i, x.expiry), x.lots * self.p.lot,
                            x.entry), x.lots, x.lots) for i, x in enumerate(self.p.legs)]

    def land(self, targets: Mapping[int, Decimal], expiry: datetime.date | None = None) -> dict[int, Decimal]:
        """REQ-078's one landing rule: refuses (naming the leg) any target strike the listing does not hold.
        ``expiry``: the moved legs land on that expiry's listing (A-04), never the position's."""
        edit = self.edit_legs(dict.fromkeys(targets, expiry) if expiry is not None else None)
        try:
            moved = leg_edit.land(self.listing, self.p.underlying, edit, targets)
        except LegEditRefused as refused:
            # the message is the catalogue's rendered error (leg_edit annotates it as str)
            raise _Refused(cast(UserFacingError, refused.message)) from refused
        return {i: strike for i in targets if (strike := moved.legs[i].leg.strike) is not None}

    def roll_distance(self, leg: PositionLeg, outward: bool) -> Decimal:
        """How far the short moves (signed points); records the basis used in ``self.basis``. The search reads the
        rows of ``leg.expiry`` only (A-04 passes the leg on the next expiry)."""
        up = (leg.type == "CE") == outward  # a call rolls out upwards, a put rolls out downwards
        rows = sorted((r for r in self.chain if r.type == leg.type and r.expiry == leg.expiry
                       and (r.strike > leg.strike if up else r.strike < leg.strike)),
                      key=lambda r: abs(r.strike - leg.strike))  # the walk away from the short
        with_delta = [(r, r.delta) for r in rows if r.delta is not None]
        target = self.cfg.target_short_delta[self.p.expiry_kind]
        if not with_delta:
            points = self.cfg.roll_points_without_delta[self.p.underlying]
            self.basis = ("points", points)
            return points if up else -points
        self.basis = ("delta", target)
        fit = [r for r, delta in with_delta if abs(delta) <= target]
        if not fit:
            gap = next((r for r in rows if r.delta is None), None)
            if gap is not None:  # an unquoted strike might have fitted: named, never "no strike"
                raise self._gap(leg, gap)
            raise _refusal("adjust_no_strike_at_delta", leg=self.ref(leg))
        # outward: the first strike beyond the short; inward: the strike nearest spot (the last one going in)
        pick = min(fit, key=lambda r: abs(r.strike - leg.strike)) if outward else \
            min(fit, key=lambda r: abs(r.strike - self.spot))
        at = rows.index(pick)
        between = rows[:at + (1 if outward else 2)]  # rolling in, the next strike past the pick could fit too
        gap = next((r for r in between if r.delta is None), None)
        if gap is not None:
            raise self._gap(leg, gap)
        return pick.strike - leg.strike

    def roll(self, found: _Condor, side: str, outward: bool) -> tuple[list[Trade], list[PositionLeg],
                                                                        list[ClosedLeg]]:
        si, wi = found.index[(side, "short")], found.index[(side, "wing")]
        short = self.p.legs[si]
        distance = self.roll_distance(short, outward)
        landed = self.land({si: short.strike + distance, wi: self.p.legs[wi].strike + distance})
        if not outward:
            other = self.p.legs[found.index[(CALL if side == PUT else PUT, "short")]].strike
            new = landed[si]
            if (side == PUT and new > other) or (side == CALL and new < other):
                raise _refusal("adjust_roll_would_cross", leg=self.ref(short), strikes=(new,), other=(other,))
        rolled = self.replace(landed)
        self.guard_debit(rolled[0])
        return rolled

    def roll_short(self, found: _Condor, side: str) -> tuple[list[Trade], list[PositionLeg], list[ClosedLeg]]:
        """A-02 (ADR-239 (1)): only the tested short moves out; its wing stays; at or beyond the wing is refused."""
        si, wi = found.index[(side, "short")], found.index[(side, "wing")]
        short, wing = self.p.legs[si], self.p.legs[wi]
        new = short.strike + self.roll_distance(short, outward=True)
        if (new >= wing.strike) if short.type == "CE" else (new <= wing.strike):
            raise _refusal("adjust_roll_short_past_wing", leg=self.ref(short), strikes=(new,), wing=(wing.strike,))
        rolled = self.replace(self.land({si: new}))
        self.guard_debit(rolled[0])
        return rolled

    def roll_out(self, found: _Condor, side: str) -> tuple[list[Trade], list[PositionLeg], list[ClosedLeg]]:
        """A-04 (ADR-239 (2)): the tested spread closed and opened on the NEXT expiry the chain carries, the short by
        ``roll_distance`` read on that expiry's rows, the wing at the old width."""
        si, wi = found.index[(side, "short")], found.index[(side, "wing")]
        short, wing = self.p.legs[si], self.p.legs[wi]
        later = sorted({r.expiry for r in self.chain if r.expiry > short.expiry})
        if not later:
            raise _refusal("adjust_roll_out_no_next_expiry", expiry=short.expiry)
        nxt = later[0]
        if not any(planned_price(r) is not None for r in self.chain if r.expiry == nxt):
            raise _refusal("adjust_roll_out_no_prices", expiry=nxt)
        distance = self.roll_distance(replace(short, expiry=nxt), outward=True)
        landed = self.land({si: short.strike + distance, wi: wing.strike + distance}, nxt)
        rolled = self.replace(landed, nxt)
        self.guard_debit(rolled[0])
        return rolled

    def shift(self, found: _Condor, side: str, steps: int) -> tuple[list[Trade], list[PositionLeg], list[ClosedLeg]]:
        """A-06 (ADR-239 (3)): the tested short and wing each ``steps`` LISTED strikes away from spot, one REQ-078
        step at a time (``leg_edit.step_strike``), so a gap in the listing is stepped by the listing."""
        si, wi = found.index[(side, "short")], found.index[(side, "wing")]
        direction = 1 if side == CALL else -1
        edit = self.edit_legs()
        try:
            for _ in range(steps):
                for i in (si, wi):
                    edit = leg_edit.step_strike(self.listing, self.p.underlying, edit, i, direction).legs
        except LegEditRefused as refused:
            raise _Refused(cast(UserFacingError, refused.message)) from refused
        rolled = self.replace({i: cast(Decimal, edit[i].leg.strike) for i in (si, wi)})
        self.guard_debit(rolled[0])
        return rolled

    def replace(self, landed: Mapping[int, Decimal], expiry: datetime.date | None = None) -> tuple[
            list[Trade], list[PositionLeg], list[ClosedLeg]]:
        """Close each landed leg and open it at its new strike (and ``expiry``, A-04; None: the same expiry)."""
        trades, after, closed = [], [], []
        for i, leg in enumerate(self.p.legs):
            if i in landed and (landed[i] != leg.strike or (expiry is not None and expiry != leg.expiry)):
                close_trade, booked = self.close(leg, leg.lots)
                open_trade, new = self.open(replace(leg, strike=landed[i], expiry=expiry or leg.expiry))
                trades += [close_trade, open_trade]
                closed.append(booked)
                after.append(new)
            else:
                after.append(leg)
        return trades, after, closed


def _close_all(b: _Builder, legs: Sequence[PositionLeg]) -> tuple[list[Trade], list[ClosedLeg], list[PositionLeg]]:
    """A-31, A-24 and A-35 (ADR-238 (1), (5)): every open leg closed at its planned price; nothing stays open."""
    pairs = [b.close(x, x.lots) for x in legs]
    return [t for t, _ in pairs], [c for _, c in pairs], []


def _take_profit_guard(b: _Builder, legs: Sequence[PositionLeg]) -> None:
    """ADR-238 (6): A-24 / A-25 only when the whole trade is in profit at the planned exit prices (the engine sums
    and compares, ADR-008); booked unknown -> refused."""
    if b.p.booked is None:
        raise _refusal("adjust_take_profit_booked_unknown")
    pnl = adjust_money.pnl_now(b.p.booked, [(x.side, x.entry, b.price_of(x), x.lots * b.p.lot) for x in legs])
    if not adjust_money.in_profit(pnl):
        raise _refusal("adjust_take_profit_not_in_profit")


def _partial(b: _Builder, legs: Sequence[PositionLeg], percent: int) -> tuple[list[Trade], list[ClosedLeg],
                                                                               list[PositionLeg]]:
    """A-25 (ADR-238 (2)): ``percent`` % of every leg's lots, refused naming the first leg whose share is fractional."""
    trades, closed, after = [], [], []
    for x in legs:
        share = Decimal(x.lots) * percent / _HUNDRED
        if share != share.to_integral_value() or share <= 0:
            raise _refusal("adjust_partial_not_whole_lots", leg=b.ref(x), lots=x.lots, percent=percent)
        n = int(share)
        t, c = b.close(x, n)
        trades.append(t)
        closed.append(c)
        if x.lots > n:
            after.append(replace(x, lots=x.lots - n))
    return trades, closed, after


def _untested_decayed(b: _Builder, legs: Sequence[PositionLeg], short_at: int, percent: int) -> tuple[
        list[Trade], list[ClosedLeg], list[PositionLeg]]:
    """A-26 (ADR-238 (3)): buy back the untested short (wing stays) when (entry - price) x 100 >= percent x entry."""
    short = legs[short_at]
    price = b.price_of(short)
    if short.entry <= 0:
        raise _refusal("adjust_untested_no_entry", leg=b.ref(short))
    if not adjust_money.fell_at_least_pct(short.entry, price, percent):
        raise _refusal("adjust_untested_not_decayed", leg=b.ref(short), entry=short.entry, now=price, percent=percent)
    t, c = b.close(short, short.lots)
    return [t], [c], [x for i, x in enumerate(legs) if i != short_at]


def _cheap_shorts(b: _Builder, legs: Sequence[PositionLeg], t09: tuple[Decimal, str] | None) -> tuple[
        list[Trade], list[ClosedLeg], list[PositionLeg]]:
    """A-27 (ADR-238 (4)): buy back every short whose planned price passes T-09's comparison against its threshold."""
    if t09 is None:
        raise _refusal("adjust_buyback_no_limit")
    limit, cmp = t09
    picked = []
    for i, x in enumerate(legs):
        if x.side != "SELL":
            continue
        price = b.price_of(x)
        if (price <= limit) if cmp == "le" else (price >= limit):
            picked.append(i)
    if not picked:
        raise _refusal("adjust_buyback_none_at_limit", limit=limit.quantize(PAISE, rounding=ROUND_HALF_UP))
    pairs = [b.close(legs[i], legs[i].lots) for i in picked]
    return [t for t, _ in pairs], [c for _, c in pairs], [x for i, x in enumerate(legs) if i not in picked]


def _time_exit_due(position: Position, exits: ExitInputs) -> None:
    """A-35 (ADR-238 (5)): built on expiry day from the playbook's time exit; otherwise refused naming the time."""
    if exits.time_exit is None:
        raise _refusal("adjust_time_exit_not_set")
    expiry_day = bool(position.legs) and position.today == min(x.expiry for x in position.legs)
    if not expiry_day or exits.hhmm is None or exits.hhmm < exits.time_exit:
        raise _refusal("adjust_time_exit_not_yet", time=exits.time_exit)


def _ordered(trades: Sequence[Trade]) -> tuple[Trade, ...]:
    return tuple(t for t in trades if t.action == "BUY") + tuple(t for t in trades if t.action == "SELL")


def build_approach(position: Position, chain: Sequence[ChainRow], spot: Decimal, approach_id: str,  # noqa: C901, PLR0912, PLR0913, PLR0915 - one branch per approach
                   config: Config, listing: Listing | None = None, limits: liquidity.Limits | None = None,
                   max_profit: Decimal | None = None, exits: ExitInputs | None = None) -> ApproachLegs:
    """The exact trades, After legs and closed legs of one approach, or its refusal naming the leg (AC-1, AC-8).
    ``limits`` = the playbook's saved liquidity limits (None: not applied); ``max_profit`` = the engine's, for the
    "% of max profit" part of the roll debit limit; ``exits`` = A-27's and A-35's playbook inputs (None: none known,
    so both are refused with the reason)."""
    if approach_id not in NAMES:
        raise ValueError(f"unknown approach {approach_id!r}")
    b = _Builder(position, chain, spot, config, listing, limits, max_profit)
    legs = list(position.legs)
    found = _condor(legs)
    tested = tested_side(position, spot)
    exits = exits or ExitInputs()
    untested = None if tested is None else (PUT if tested == CALL else CALL)
    side = {"A-36": "none", "A-31": "both", "A-11": "both", "A-24": "both", "A-25": "both", "A-27": "both",
            "A-35": "both"}.get(approach_id) or \
        ((untested or "none") if approach_id in ("A-01", "A-26") else (tested or "none"))
    trades: list[Trade] = []
    closed: list[ClosedLeg] = []
    after = legs
    try:
        if approach_id == "A-36":
            pass
        elif approach_id in _CLOSE_ALL:
            if approach_id == "A-35":
                _time_exit_due(position, exits)
            trades, closed, after = _close_all(b, legs)
            if approach_id == "A-24":
                _take_profit_guard(b, legs)
        elif approach_id == "A-25":
            _take_profit_guard(b, legs)
            trades, closed, after = _partial(b, legs, config.partial_close_percent)
        elif approach_id == "A-27":
            trades, closed, after = _cheap_shorts(b, legs, exits.t09)
        elif found is None or tested is None or untested is None:
            raise _refusal("adjust_needs_two_spreads")
        elif approach_id == "A-26":
            trades, closed, after = _untested_decayed(b, legs, found.index[(untested, "short")],
                                                      config.untested_decay_percent)
        elif approach_id == "A-05":
            trades, after, closed = b.roll(found, tested, outward=True)
        elif approach_id == "A-02":
            trades, after, closed = b.roll_short(found, tested)
        elif approach_id == "A-04":
            trades, after, closed = b.roll_out(found, tested)
        elif approach_id == "A-06":
            trades, after, closed = b.shift(found, tested, config.shift_strikes)
        elif approach_id == "A-01":
            trades, after, closed = b.roll(found, PUT if tested == CALL else CALL, outward=False)
        elif approach_id == "A-28":
            gone = {found.index[(tested, "short")], found.index[(tested, "wing")]}
            pairs = [b.close(legs[i], legs[i].lots) for i in sorted(gone)]
            trades, closed = [t for t, _ in pairs], [c for _, c in pairs]
            after = [x for i, x in enumerate(legs) if i not in gone]
        elif approach_id == "A-29":
            cut = {found.index[(tested, "short")], found.index[(tested, "wing")]}
            short = legs[found.index[(tested, "short")]]
            if min(legs[i].lots for i in cut) < 2:  # noqa: PLR2004 - half of one lot is not a whole lot
                raise _refusal("adjust_reduce_needs_two_lots", leg=b.ref(short))
            after = []
            for i, x in enumerate(legs):
                if i in cut:
                    n = x.lots // config.reduce_divisor
                    t, c = b.close(x, n)
                    trades.append(t)
                    closed.append(c)
                    after.append(replace(x, lots=x.lots - n))
                else:
                    after.append(x)
        elif approach_id == "A-11":
            days = (legs[0].expiry - position.today).days
            if days < config.iron_fly_min_days_left:
                raise _refusal("adjust_recentre_days_left", need=config.iron_fly_min_days_left, days=max(days, 0))
            grid = set(b.listing.strikes(position.underlying, legs[0].expiry, Instrument.CE)) & \
                set(b.listing.strikes(position.underlying, legs[0].expiry, Instrument.PE))
            if not grid:
                raise _refusal("adjust_no_strike_both_types", expiry=legs[0].expiry)
            atm = min(grid, key=lambda k: (abs(k - spot), -k))
            targets = {}
            for s in (CALL, PUT):
                si, wi = found.index[(s, "short")], found.index[(s, "wing")]
                targets[si] = atm
                targets[wi] = atm + (legs[wi].strike - legs[si].strike)
            trades, after, closed = b.replace(b.land(targets))
    except _Refused as refused:
        refusal: str | None = refused.reason
        refusal_message: UserFacingError | None = refused.message
    else:
        refusal = refusal_message = None
    basis, value = b.basis if b.basis is not None else (None, None)
    base = ApproachLegs(approach_id, NAMES[approach_id], KINDS[approach_id], side, step_basis=basis, step_value=value)
    base = replace(base, unpriced=tuple(dict.fromkeys(b.unpriced)))
    if refusal is not None:
        return replace(base, refusal=refusal, refusal_message=refusal_message)
    return replace(base, trades=_ordered(trades), after=tuple(after), closed=tuple(closed), warnings=tuple(b.warnings),
                   warning_messages=tuple(b.warning_messages))


def applicable_approaches(position: Position, chain: Sequence[ChainRow], spot: Decimal, config: Config,  # noqa: PLR0913
                          listing: Listing | None = None, exits: ExitInputs | None = None) -> list[ApproachLegs]:
    """Every built approach of the iron condor, in ``APPROACH_IDS`` order; a refused one comes back with its reason
    (never dropped silently), every other approach still builds (AC-8)."""
    return [build_approach(position, chain, spot, a, config, listing, exits=exits) for a in APPROACH_IDS]
