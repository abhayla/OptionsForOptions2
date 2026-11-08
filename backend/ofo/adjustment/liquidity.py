"""Playbook liquidity limits (ADR-230 (1); REQ-159 AC-6; finding F-78; class setting-saved-but-never-applied).

Three saved playbook guards are READ here and applied to a candidate set:

- ``hide_oi_below``: a strike whose open interest is below it stays visible and is flagged "Below your liquidity limit".
- ``hide_spread_pct_of_mid_above``: the same flag when (ask - bid) / mid x 100 is above it.
- ``roll_debit_limit``: a roll whose net debit is above it is refused with the reason. Stored as TEXT
  (``Rs 500 or 10% of max profit``); ``parse_debit_limit`` is the one parser.

Nothing is removed silently (ADR-230). Decimal only (ADR-008); the max profit used for the "% of max profit" part is the
caller's engine figure, this module computes no payoff.

Answer states per limit (each tested): stated and passes; stated and breaks (flag / refuse); open interest absent
(``OI not known``, never passing, F-78: no live source gives it); limit not set on the playbook (no flag, no refusal);
limit stated but unreadable (fail closed: a strike is flagged, a roll is refused); no bid or ask while a spread limit
is set (fail closed: flagged); empty candidate list (empty answer).

Debit limit reading, decided here: "Rs A or P% of max profit" allows the HIGHER of the two (either bound permits the
roll). With no readable max profit the percent part cannot be computed, so only Rs A is available and a debit above it
is refused as "cannot confirm", never passed.

Known bypasses: (1) the caller must pass the playbook's guards; ``limits_from_guards({})`` sets nothing, so a route that
does not pass them flags nothing (the approaches route does not read a playbook yet); (2) a user editing the saved JSON
by hand to a readable but absurd value (out of scope); (3) limits GC-SET owns (admin settings) are not read here;
(4) the OI flag uses the row's ``oi`` only; the live chain rows carry the feed's OI through the strike drawer's one rule
(``ofo_app.outcome_oi.oi_of``), so a strike with no usable OI (no quote, market closed without a close) reads
"OI not known".
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from ofo.engine import adjust_money

OI_KEY = "hide_oi_below"
SPREAD_KEY = "hide_spread_pct_of_mid_above"
DEBIT_KEY = "roll_debit_limit"

#: The texts of the two flags (catalogue labels ``adjust_flag_*`` in ofo.errors.explanations).
FLAG_BELOW = "adjust_flag_below_liquidity"
FLAG_OI_UNKNOWN = "adjust_flag_oi_unknown"

SET, UNSET, UNREADABLE = "set", "unset", "unreadable"
HUNDRED = Decimal(100)
_DEBIT_TEXT = re.compile(r"^\s*Rs\.?\s*(\d+(?:\.\d+)?)(?:\s+or\s+(\d+(?:\.\d+)?)\s*%\s+of\s+max\s+profit)?\s*$",
                         re.IGNORECASE)


@dataclass(frozen=True)
class DebitLimit:
    rupees: Decimal
    pct_of_max_profit: Decimal | None = None


@dataclass(frozen=True)
class Limits:
    """The three saved limits. ``*_state`` is set / unset / unreadable (a stated value the parser cannot read)."""

    oi_state: str = UNSET
    oi_below: Decimal | None = None
    spread_state: str = UNSET
    spread_pct_above: Decimal | None = None
    debit_state: str = UNSET
    debit: DebitLimit | None = None


def _number(raw: object) -> Decimal | None:
    if isinstance(raw, bool) or raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    try:
        value = Decimal(str(raw).strip())
    except InvalidOperation:
        return None
    return value if value.is_finite() and value >= 0 else None


def parse_debit_limit(raw: object) -> DebitLimit | None:
    """``Rs 500`` or ``Rs 500 or 10% of max profit``; anything else is None (the caller fails closed)."""
    match = _DEBIT_TEXT.match(raw) if isinstance(raw, str) else None
    if match is None:
        return None
    return DebitLimit(Decimal(match.group(1)), None if match.group(2) is None else Decimal(match.group(2)))


def limits_from_guards(guards: Mapping[str, object] | None) -> Limits:
    """Read the three keys of a playbook body's ``guards``. A key that is absent or null is not set."""
    g = guards or {}
    states: dict[str, object] = {}
    for key, read in ((OI_KEY, _number), (SPREAD_KEY, _number), (DEBIT_KEY, parse_debit_limit)):
        raw = g.get(key)
        if raw is None:
            states[key] = (UNSET, None)
        else:
            value = read(raw)
            states[key] = (UNREADABLE, None) if value is None else (SET, value)
    return Limits(states[OI_KEY][0], states[OI_KEY][1], states[SPREAD_KEY][0], states[SPREAD_KEY][1],  # type: ignore[index,arg-type]
                  states[DEBIT_KEY][0], states[DEBIT_KEY][1])  # type: ignore[index,arg-type]


# ---- strikes ------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class StrikeLiquidity:
    """One strike's state per limit: oi in {ok, below, unknown, unset, unreadable}; spread in the same shape with
    ``above`` for a spread over the limit."""

    oi: str
    spread: str

    @property
    def flags(self) -> tuple[str, ...]:
        """Catalogue ids of the flags to show beside the strike; empty when it passes (or no limit is set)."""
        out = []
        if self.oi in ("below", "unreadable") or self.spread in ("above", "unknown", "unreadable"):
            out.append(FLAG_BELOW)
        if self.oi == "unknown":
            out.append(FLAG_OI_UNKNOWN)
        return tuple(out)


def evaluate_strike(limits: Limits, oi: Decimal | int | None, bid: Decimal | None,
                    ask: Decimal | None) -> StrikeLiquidity:
    """One strike against the playbook's limits. ``oi`` None = no source gave it."""
    if limits.oi_state != SET:
        oi_state = limits.oi_state
    elif oi is None:
        oi_state = "unknown"
    else:
        oi_state = "below" if Decimal(oi) < (limits.oi_below or Decimal(0)) else "ok"
    if limits.spread_state != SET:
        spread_state = limits.spread_state
    elif bid is None or ask is None or bid <= 0 or ask < bid:
        spread_state = "unknown"
    else:
        pct = (ask - bid) / ((bid + ask) / 2) * HUNDRED
        spread_state = "above" if pct > (limits.spread_pct_above or Decimal(0)) else "ok"
    return StrikeLiquidity(oi_state, spread_state)


def evaluate_rows(limits: Limits, rows: Sequence[object]) -> dict[object, StrikeLiquidity]:
    """Every candidate row (objects with ``oi``-less chain fields: ``bid``/``ask`` and optional ``oi``) -> its state.
    Every row is returned: none is dropped (ADR-230). An empty list gives an empty dict."""
    return {r: evaluate_strike(limits, getattr(r, "oi", None), getattr(r, "bid", None), getattr(r, "ask", None))
            for r in rows}


# ---- roll debit ---------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class DebitVerdict:
    allowed: bool
    reason: str  # "ok" / "no_limit" / "over" / "unreadable" / "cannot_confirm"
    debit: Decimal
    limit: Decimal | None = None


def check_roll_debit(limits: Limits, debit: Decimal, max_profit: Decimal | None) -> DebitVerdict:
    """``debit`` is the roll's net cash paid (positive = debit, <= 0 = credit/flat, always allowed)."""
    if debit <= 0 or limits.debit_state == UNSET:
        return DebitVerdict(True, "no_limit" if limits.debit_state == UNSET else "ok", debit)
    if limits.debit_state == UNREADABLE or limits.debit is None:
        return DebitVerdict(False, "unreadable", debit)
    allowed = limits.debit.rupees
    pct = limits.debit.pct_of_max_profit
    if pct is not None and max_profit is not None and max_profit > 0:
        allowed = max(allowed, adjust_money.pct_of(max_profit, pct))
    if debit <= allowed:
        return DebitVerdict(True, "ok", debit, allowed)
    if pct is not None and (max_profit is None or max_profit <= 0):
        return DebitVerdict(False, "cannot_confirm", debit, allowed)
    return DebitVerdict(False, "over", debit, allowed)


# ---- the class guard: every playbook guard key has a reader --------------------------------------------------------

_READERS = json.loads(Path(__file__).with_name("guard_readers.json").read_text(encoding="utf-8"))
#: guard key -> repo path whose source reads it (guard_readers.json; the test opens the file and finds the key there).
GUARD_READERS: Mapping[str, str] = _READERS["readers"]
#: guard key -> why nothing reads it today (found by the class guard, 2026-11-01; reported, not fixed here).
KNOWN_UNREAD: Mapping[str, str] = _READERS["known_unread"]

