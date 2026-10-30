"""Adjustment approach builder (REQ-155 AC-1, AC-8; ADR-214; goal contract GC-ADJ1 "Design decisions").

For a tracked iron condor and one picked approach this module builds the EXACT trades, the After legs and the legs the
approach closes (with entry and planned exit, so the caller can book their P&L, F-74). It computes no money figure of
the trade (ADR-008): pricing the After is the one engine's job. Suggest-only (ADR-003): nothing here places an order.

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
  is ``roll_points_without_delta`` of the underlying (200 NIFTY / 500 SENSEX), labelled in ``step_basis``.
- Landing: through the REQ-078 landing rule ``leg_edit._land`` (a strike not listed is refused naming the leg).
- A-01 that would put the put short above the call short (or the call short below the put short) is refused: the
  condor would be inverted. Equal shorts are allowed.
- A-29: closes ``lots // reduce_divisor`` lots of the tested short and its wing; under 2 lots it is refused (half of
  one lot is not a whole lot).
- A-11: both shorts to the ATM strike (the listed strike nearest spot, a tie goes to the higher strike), each wing
  keeps its distance from its short; refused with fewer than ``iron_fly_min_days_left`` days left.
- Planned price of every trade = the planned-entry rule of ADR-068 (1) (``ofo.outcome.planned_entry``): the row's LTP
  if positive, else the mid of a positive bid and ask, half-up to 0.01; otherwise there is no price and the approach
  is refused naming the leg ("No price for ...: this approach trades it").
- Answer states of the chain row a NEW leg lands on: listed + tradable + low-OI stated not blocked -> build; not listed
  -> refused (landing rule); not tradable -> refused; low-OI stated blocked -> refused; low-OI unknown -> a warning on
  the leg (AC-8), not a refusal; no price -> refused. A CLOSING trade needs only a price (exits are always allowed).
- Trade order: BUY trades first, then SELL (the playbook guard "buy legs first"), each group in leg order.
- The builder does not apply the playbook's adjustment limit (S-11) or the data-state hold: those are filters of the
  caller (REQ-157), so every approach is built whenever its own legs allow it.
"""
from __future__ import annotations

import datetime
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from ofo.engine.legs import Action, Instrument, Leg
from ofo.instruments.catalogue import SUPPORTED_UNDERLYINGS, Catalogue
from ofo.instruments.models import Contract
from ofo.money import PAISE
from ofo.strategy import leg_edit
from ofo.strategy.leg_edit import EditLeg, LegEditRefused, Listing

CONFIG_FILE = Path(__file__).with_name("approach_config.json")
APPROACH_IDS = ("A-36", "A-01", "A-05", "A-29", "A-28", "A-11", "A-31")
NAMES = {"A-36": "No change", "A-01": "Roll the untested spread toward spot",
         "A-05": "Roll the tested spread out (same width)", "A-29": "Reduce the tested side",
         "A-28": "Close the tested spread", "A-11": "Re-centre as an iron butterfly", "A-31": "Exit the whole strategy"}
KINDS = {"A-36": "none", "A-01": "roll", "A-05": "roll", "A-29": "reduce", "A-28": "close part", "A-11": "convert",
         "A-31": "exit"}
CALL, PUT = "call", "put"
_SIDE_TYPE = {CALL: "CE", PUT: "PE"}
_OPPOSITE = {"BUY": "SELL", "SELL": "BUY"}


@dataclass(frozen=True)
class Config:
    target_short_delta: Mapping[str, Decimal]
    roll_points_without_delta: Mapping[str, Decimal]
    iron_fly_min_days_left: int
    reduce_divisor: int


def load_config(path: Path = CONFIG_FILE) -> Config:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return Config({k: Decimal(v) for k, v in raw["target_short_delta"].items()},
                  {k: Decimal(v) for k, v in raw["roll_points_without_delta"].items()},
                  int(raw["iron_fly_min_days_left"]), int(raw["reduce_divisor"]))


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


@dataclass(frozen=True)
class Trade:
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
    step_basis: str | None = None


class _Refused(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class _Condor:
    index: dict[tuple[str, str], int] = field(default_factory=dict)  # (side, "short"/"wing") -> leg index


def leg_label(underlying: str, expiry: datetime.date, strike: Decimal, kind: str) -> str:
    """'NIFTY 3 Nov 22,400 PE': how a refusal or warning names the leg."""
    return f"{underlying} {expiry.day} {expiry.strftime('%b')} {strike:,} {kind}"


def planned_price(row: ChainRow | None) -> Decimal | None:
    """ADR-068 (1), as ``ofo.outcome.planned_entry.planned_entry_of``: a positive LTP, else the mid of a positive bid
    and ask, half-up to 0.01; else None (no fake price, ADR-020 Q185)."""
    if row is None:
        return None
    if row.ltp is not None and row.ltp > 0:
        return row.ltp.quantize(PAISE, rounding=ROUND_HALF_UP)
    if row.bid is not None and row.ask is not None and row.bid > 0 and row.ask > 0:
        return ((row.bid + row.ask) / 2).quantize(PAISE, rounding=ROUND_HALF_UP)
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
    found = _Condor()
    for i, x in enumerate(legs):
        side = CALL if x.type == "CE" else PUT
        found.index[(side, "short" if x.side == "SELL" else "wing")] = i
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
    def __init__(self, position: Position, chain: Sequence[ChainRow], spot: Decimal, config: Config,
                 listing: Listing | None) -> None:
        self.p, self.spot, self.cfg = position, spot, config
        self.rows = {(r.expiry, r.type, r.strike): r for r in chain}
        self.chain = chain
        self.listing = listing or listing_from_chain(position.underlying, position.lot, chain, position.today)
        self.warnings: list[str] = []
        self.basis: str | None = None

    def label(self, leg: PositionLeg) -> str:
        return leg_label(self.p.underlying, leg.expiry, leg.strike, leg.type)

    def price_of(self, leg: PositionLeg) -> Decimal:
        price = planned_price(self.rows.get((leg.expiry, leg.type, leg.strike)))
        if price is None:
            raise _Refused(f"No price for {self.label(leg)}: this approach trades it")
        return price

    def close(self, leg: PositionLeg, lots: int) -> tuple[Trade, ClosedLeg]:
        price = self.price_of(leg)
        qty = lots * self.p.lot
        return (Trade(_OPPOSITE[leg.side], leg.type, leg.strike, leg.expiry, lots, qty, price, leg.tradingsymbol),
                ClosedLeg(leg.side, leg.type, leg.strike, leg.expiry, lots, qty, leg.entry, price, leg.tradingsymbol))

    def open(self, leg: PositionLeg) -> tuple[Trade, PositionLeg]:
        """A new contract: every answer state of its chain row (module docstring)."""
        row = self.rows.get((leg.expiry, leg.type, leg.strike))
        name = self.label(leg)
        if row is None or not row.listed:  # the landing rule already refused a strike the listing lacks
            raise _Refused(f"No {leg.strike:,} {leg.type} is listed for {leg.expiry.day} {leg.expiry.strftime('%b')}: "
                           f"{name} cannot be opened")
        if not row.tradable:
            raise _Refused(f"{name} is listed but not tradable: this approach opens it")
        if row.low_oi_state == "stated" and row.low_oi_blocked:
            raise _Refused(f"Zerodha blocks fresh orders in {name} (low OI, M-15): this approach opens it")
        if row.low_oi_state != "stated":
            self.warnings.append(f"Low-OI state unknown for {name}: Zerodha may refuse fresh orders in low-OI "
                                 "contracts")
        price = self.price_of(leg)
        new = replace(leg, entry=price, tradingsymbol=row.tradingsymbol)
        return Trade(leg.side, leg.type, leg.strike, leg.expiry, leg.lots, leg.lots * self.p.lot, price,
                     row.tradingsymbol), new

    def land(self, targets: Mapping[int, Decimal]) -> dict[int, Decimal]:
        """REQ-078's one landing rule: refuses (naming the leg) any target strike the listing does not hold."""
        edit = [EditLeg(Leg(Action(x.side), Instrument(x.type), x.strike, x.expiry, x.lots * self.p.lot, x.entry),
                        x.lots, x.lots) for x in self.p.legs]
        try:
            moved = leg_edit._land(self.listing, self.p.underlying, edit, targets)
        except LegEditRefused as refused:
            raise _Refused(refused.message.what_happened) from refused
        return {i: moved.legs[i].leg.strike for i in targets}

    def roll_distance(self, leg: PositionLeg, outward: bool) -> tuple[Decimal, str]:
        """How far the short moves (signed points) and the label of the basis used."""
        up = (leg.type == "CE") == outward  # a call rolls out upwards, a put rolls out downwards
        rows = [r for r in self.chain if r.type == leg.type and r.expiry == leg.expiry
                and (r.strike > leg.strike if up else r.strike < leg.strike)]
        with_delta = [r for r in rows if r.delta is not None]
        target = self.cfg.target_short_delta[self.p.expiry_kind]
        if not with_delta:
            points = self.cfg.roll_points_without_delta[self.p.underlying]
            return (points if up else -points), f"points {points} (delta not available)"
        fit = [r for r in with_delta if abs(r.delta) <= target]  # type: ignore[arg-type]
        if not fit:
            raise _Refused(f"No strike {'beyond' if outward else 'inside'} {self.label(leg)} has delta "
                           f"{target} or less")
        # outward: the first strike beyond the short; inward: the strike nearest spot (the last one going in)
        pick = min(fit, key=lambda r: abs(r.strike - leg.strike)) if outward else \
            min(fit, key=lambda r: abs(r.strike - self.spot))
        return pick.strike - leg.strike, f"delta {target}"

    def roll(self, found: _Condor, side: str, outward: bool) -> tuple[list[Trade], list[PositionLeg],
                                                                        list[ClosedLeg], str]:
        si, wi = found.index[(side, "short")], found.index[(side, "wing")]
        short = self.p.legs[si]
        distance, basis = self.roll_distance(short, outward)
        self.basis = basis  # kept on a refusal too: the reader sees which step the refused roll used
        landed = self.land({si: short.strike + distance, wi: self.p.legs[wi].strike + distance})
        if not outward:
            other = self.p.legs[found.index[(CALL if side == PUT else PUT, "short")]].strike
            new = landed[si]
            if (side == PUT and new > other) or (side == CALL and new < other):
                raise _Refused(f"Rolling the {side} spread to {new:,} would cross the other short at {other:,}")
        return (*self._replace(landed), basis)

    def _replace(self, landed: Mapping[int, Decimal]) -> tuple[list[Trade], list[PositionLeg], list[ClosedLeg]]:
        trades, after, closed = [], [], []
        for i, leg in enumerate(self.p.legs):
            if i in landed and landed[i] != leg.strike:
                close_trade, booked = self.close(leg, leg.lots)
                open_trade, new = self.open(replace(leg, strike=landed[i]))
                trades += [close_trade, open_trade]
                closed.append(booked)
                after.append(new)
            else:
                after.append(leg)
        return trades, after, closed


def _ordered(trades: Sequence[Trade]) -> tuple[Trade, ...]:
    return tuple(t for t in trades if t.action == "BUY") + tuple(t for t in trades if t.action == "SELL")


def build_approach(position: Position, chain: Sequence[ChainRow], spot: Decimal, approach_id: str,  # noqa: C901, PLR0912, PLR0913, PLR0915 - one branch per approach
                   config: Config, listing: Listing | None = None) -> ApproachLegs:
    """The exact trades, After legs and closed legs of one approach, or its refusal naming the leg (AC-1, AC-8)."""
    if approach_id not in NAMES:
        raise ValueError(f"unknown approach {approach_id!r}")
    b = _Builder(position, chain, spot, config, listing)
    legs = list(position.legs)
    found = _condor(legs)
    tested = tested_side(position, spot)
    base = {"id": approach_id, "name": NAMES[approach_id], "kind": KINDS[approach_id]}
    side = {"A-36": "none", "A-31": "both", "A-11": "both"}.get(approach_id) or \
        ((PUT if tested == CALL else CALL) if approach_id == "A-01" else (tested or "none"))
    trades: list[Trade] = []
    closed: list[ClosedLeg] = []
    after = legs
    basis = None
    try:
        if approach_id == "A-36":
            pass
        elif approach_id == "A-31":
            pairs = [b.close(x, x.lots) for x in legs]
            trades, closed, after = [t for t, _ in pairs], [c for _, c in pairs], []
        elif found is None or tested is None:
            raise _Refused(f"{NAMES[approach_id]} needs an iron condor (the first delivery)")
        elif approach_id == "A-05":
            trades, after, closed, basis = b.roll(found, tested, outward=True)
        elif approach_id == "A-01":
            trades, after, closed, basis = b.roll(found, PUT if tested == CALL else CALL, outward=False)
        elif approach_id == "A-28":
            gone = {found.index[(tested, "short")], found.index[(tested, "wing")]}
            pairs = [b.close(legs[i], legs[i].lots) for i in sorted(gone)]
            trades, closed = [t for t, _ in pairs], [c for _, c in pairs]
            after = [x for i, x in enumerate(legs) if i not in gone]
        elif approach_id == "A-29":
            cut = {found.index[(tested, "short")], found.index[(tested, "wing")]}
            if min(legs[i].lots for i in cut) < 2:  # noqa: PLR2004 - half of one lot is not a whole lot
                raise _Refused(f"Reduce needs at least 2 lots on the {tested} side (it holds 1)")
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
                raise _Refused(f"Only with {config.iron_fly_min_days_left}+ days left ({days} left)")
            grid = set(b.listing.strikes(position.underlying, legs[0].expiry, Instrument.CE)) & \
                set(b.listing.strikes(position.underlying, legs[0].expiry, Instrument.PE))
            if not grid:
                raise _Refused("No strike is listed for both a call and a put")
            atm = min(grid, key=lambda k: (abs(k - spot), -k))
            targets = {}
            for s in (CALL, PUT):
                si, wi = found.index[(s, "short")], found.index[(s, "wing")]
                targets[si] = atm
                targets[wi] = atm + (legs[wi].strike - legs[si].strike)
            trades, after, closed = b._replace(b.land(targets))
    except _Refused as refused:
        return ApproachLegs(**base, side=side, refusal=refused.reason, step_basis=b.basis)
    return ApproachLegs(**base, side=side, trades=_ordered(trades), after=tuple(after), closed=tuple(closed),
                        warnings=tuple(b.warnings), step_basis=basis)


def applicable_approaches(position: Position, chain: Sequence[ChainRow], spot: Decimal, config: Config,
                          listing: Listing | None = None) -> list[ApproachLegs]:
    """The 7 approaches of the iron condor, in the contract's order; A-11 under 3 days left and A-29 under 2 lots come
    back refused with their reason (never dropped silently), every other approach still builds (AC-8)."""
    return [build_approach(position, chain, spot, a, config, listing) for a in APPROACH_IDS]
