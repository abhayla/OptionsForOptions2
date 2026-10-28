"""GC-UI step 4 server round 3 (REQ-083 AC-5 / AC-6; D-B16, D-B17): the payoff chart's open-interest bars.

An outcome call with ``open_interest`` gets, for the strategy's expiry (a calendar: the NEAREST option-leg expiry, named
in ``expiry_note``), one row per listed strike inside the reply's own scenario range (``scenario.start`` ..
``scenario.end``) with its call OI and put OI and their compact display text, plus ``read_at``: the OLDEST time among
the quotes used, so the "OI data at" strip never claims fresher data than it shows.

The OI is read from the same feed the strike drawer reads (``provider.option_chain_snapshot``) under the drawer's own
rule (``oi_of``, which the drawer's cells use too): in hours an AVAILABLE quote's OI; after the close (ADR-200 (1)) the
last close the feed holds. A side with no usable OI is ``None`` with a dash, never 0; a real 0 is ``0`` / "0". When no
contract has usable OI the block is unavailable with ONE AC-6 reason and no rows, so the chart never draws zero-height
bars as if OI were zero.

Holding: a NIFTY default range of 21,500..23,500 is 41 strikes, so up to 82 contracts (two per strike) beyond the legs.
Only the live push holds them (``hold_ids``; ``live_push.StrategyPush`` keeps one handle, swapped new-first like the
forward strikes and released when the socket stops asking or ends). A REST read holds nothing: it uses the OI only of
contracts some socket already streams (issue #206's rule), else the not-streaming reason.

Today's OI change (D-B18) is Later: not built here. Framework-free; no order path is reachable from here.
"""
from __future__ import annotations

import datetime
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ofo.engine.legs import Instrument
from ofo.errors.explanations import render_explanation
from ofo.marketdata.quote import NormalizedQuote, is_live_price, planning_price_usable, priced
from ofo.outcome.snapshot import contract_id
from ofo.rules.inputs import DataHealth

_OPTION_TYPES = (Instrument.CE.value, Instrument.PE.value)


def price_counts(quote: NormalizedQuote | None, closed: bool = False) -> bool:
    """The one 'a quote's price counts' rule (``ofo.marketdata.quote.priced``: live and above 0); outside market hours
    (``closed``, the one market-state answer) also the last close the feed holds (ADR-200 (1): the strike drawer uses
    it; ``ofo.marketdata.quote.planning_price_usable``). Never an order rule."""
    if not closed:
        return priced(quote)
    return planning_price_usable(quote, market_closed=True) and quote is not None and is_live_price(quote.ltp)


def oi_of(quote: NormalizedQuote | None, closed: bool = False) -> int | None:
    """The strike drawer's OI rule, shared with the payoff chart: in hours any AVAILABLE quote's OI (even with LTP 0);
    after the close the last close held (ADR-200 (1)). None: no usable OI (never 0 in its place)."""
    if quote is None:
        return None
    if closed:
        return quote.oi if price_counts(quote, closed) else None
    return quote.oi if quote.health is DataHealth.AVAILABLE else None


@dataclass(frozen=True)
class _Strike:
    strike: Decimal
    ce: str | None
    pe: str | None


def oi_expiry(master: Iterable[Any], underlying: str, leg_ids: Iterable[str]) -> tuple[datetime.date | None, bool]:
    """The expiry the bars are for: the option legs' one expiry, or (a calendar) the nearest; and whether it was a
    choice among several (then the reply names it). A futures-only or unknown-leg strategy has none."""
    wanted = set(leg_ids)
    expiries = {lc.contract.expiry for lc in master
                if contract_id(lc) in wanted and lc.contract.name == underlying
                and lc.contract.instrument_type in _OPTION_TYPES and lc.contract.expiry is not None}
    if not expiries:
        return None, False
    return min(expiries), len(expiries) > 1


def strikes_in_range(master: Iterable[Any], underlying: str, expiry: datetime.date, start: Decimal,
                     end: Decimal) -> list[_Strike]:
    """Every listed strike of ``expiry`` inside ``start`` .. ``end`` (both included), with its CE and PE ids."""
    sides: dict[Decimal, dict[str, str]] = {}
    for lc in master:
        c = lc.contract
        if (c.name == underlying and c.expiry == expiry and c.instrument_type in _OPTION_TYPES
                and c.strike is not None and start <= c.strike <= end):
            sides.setdefault(c.strike, {})[c.instrument_type] = contract_id(lc)
    return [_Strike(k, v.get("CE"), v.get("PE")) for k, v in sorted(sides.items())]


def reply_range(body: Mapping[str, Any]) -> tuple[Decimal, Decimal] | None:
    """The reply's own level range: its scenario's start and end (present for a calendar too, where the at-expiry
    curve is unavailable); None when the reply has no scenario (not connected, waiting for the first price)."""
    scenario = body.get("scenario") or {}
    start, end = scenario.get("start"), scenario.get("end")
    if start is None or end is None:
        return None
    return Decimal(str(start)), Decimal(str(end))


def _plan(provider: Any, underlying: str, leg_ids: list[str], body: Mapping[str, Any]):
    rng = reply_range(body)
    if rng is None:
        return None, False, []
    master = provider.instrument_master()
    expiry, chosen = oi_expiry(master, underlying, leg_ids)
    if expiry is None:
        return None, False, []
    return expiry, chosen, strikes_in_range(master, underlying, expiry, *rng)


def hold_ids(provider: Any, underlying: str, leg_ids: list[str], body: Mapping[str, Any]) -> list[str]:
    """The contracts the live push holds for the bars of this reply (the legs themselves are held already)."""
    _expiry, _chosen, strikes = _plan(provider, underlying, leg_ids, body)
    legs = set(leg_ids)
    return [i for s in strikes for i in (s.ce, s.pe) if i is not None and i not in legs]


def _unavailable(template: str, expiry: datetime.date | None = None) -> dict[str, Any]:
    return {"available": False, "unavailable_reason": render_explanation(template), "expiry": expiry,
            "expiry_note": None, "read_at": None, "read_at_display": None, "contracts": 0, "rows": []}


def _side(count: int | None) -> tuple[int | None, Any]:
    if count is None:
        return None, render_explanation("cell_dash")
    return count, render_explanation("outcome_oi_count", count=count)


def oi_block(provider: Any | None, underlying: str, leg_ids: list[str], body: Mapping[str, Any], *,  # noqa: PLR0913
             closed: bool, live_blocked: bool, streams=None) -> dict[str, Any]:
    """The ``open_interest`` block of one reply. ``streams(ids)`` (REST only, issue #206): True when every id is held
    by a socket on the shared feed. Every answer state ends in rows or ONE AC-6 reason, never a 0 in a missing place."""
    if provider is None:
        return _unavailable("outcome_oi_not_connected")
    if live_blocked:
        return _unavailable("outcome_oi_not_streaming")
    expiry, chosen, strikes = _plan(provider, underlying, leg_ids, body)
    if not strikes:
        return _unavailable("outcome_oi_no_strikes", expiry)
    ids = [i for s in strikes for i in (s.ce, s.pe) if i is not None]
    if streams is not None and not streams(ids):
        return _unavailable("outcome_oi_not_streaming", expiry)
    wanted = set(ids)
    quotes = {q.instrument_id: q for q in provider.option_chain_snapshot(underlying, expiry)
              if q.instrument_id in wanted}  # only this expiry's contracts: never another expiry's OI
    counts = {i: oi_of(q, closed) for i, q in quotes.items()}
    used = [quotes[i] for i, n in counts.items() if n is not None]
    if not used:
        return _unavailable("outcome_oi_stale" if quotes else "outcome_oi_not_streaming", expiry)
    rows = []
    for s in strikes:
        call, call_text = _side(None if s.ce is None else counts.get(s.ce))
        put, put_text = _side(None if s.pe is None else counts.get(s.pe))
        rows.append({"strike": s.strike, "call_oi": call, "call_oi_display": call_text,
                     "put_oi": put, "put_oi_display": put_text})
    read_at = min(q.timestamp for q in used)
    return {"available": True, "unavailable_reason": None, "expiry": expiry,
            "expiry_note": render_explanation("outcome_oi_nearest_expiry", expiry=expiry) if chosen else None,
            "read_at": read_at, "read_at_display": render_explanation("outcome_oi_read_at", time=read_at),
            "contracts": len(ids), "rows": rows}
