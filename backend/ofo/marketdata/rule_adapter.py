"""Adapter from quote health to the rule engine's input-health map (REQ-049 AC-3).

``ofo.rules.inputs.Snapshot`` already carries an ``input_health`` map keyed by ``InputName`` and already treats any
input whose health is not ``available`` as unusable (never live). This adapter is therefore a direct translation:
which quote backs which named input, so the health this module derived (:mod:`ofo.marketdata.health`) reaches the
rule engine without re-deriving or weakening it. A stale (or delayed/unhealthy/unavailable) quote can never make a
rule TRIGGER, because the deciding comparison becomes ``Truth.UNKNOWN`` (``ofo.rules.conditions.decide``) the
moment its input's health is not ``available``.

The snapshot's OVERALL ``data_health`` is never typed by a caller: :func:`build_snapshot` derives it as the worst
of the healths of the quotes actually backing the snapshot's inputs (unavailable > unhealthy > stale > delayed >
available), so the trigger record (``Evaluation.data_health``) always reflects what the rule actually read.
"""
from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Mapping

from ofo.marketdata.quote import NormalizedQuote
from ofo.rules.inputs import DataHealth, InputName, Snapshot

# Worst first: the first of these present among a set of quote healths wins.
_SEVERITY_ORDER = (
    DataHealth.UNAVAILABLE,
    DataHealth.UNHEALTHY,
    DataHealth.STALE,
    DataHealth.DELAYED,
    DataHealth.AVAILABLE,
)


def input_health_from_quotes(quote_by_input: Mapping[InputName, NormalizedQuote]) -> dict[InputName, DataHealth]:
    """Map each named rule input to the health of the quote that supplies it.

    ``quote_by_input`` names, for one snapshot, which quote backs each ``InputName`` a rule might read (e.g.
    ``UNDERLYING_LEVEL`` from the index quote, ``IV``/``DELTA`` from an option leg's quote). The result is exactly
    the ``input_health`` a :class:`ofo.rules.inputs.Snapshot` accepts.
    """
    result: dict[InputName, DataHealth] = {}
    for name, quote in dict(quote_by_input).items():
        if not isinstance(name, InputName):
            raise ValueError(f"quote_by_input keys must be InputName, got {name!r}")
        if name is InputName.TIME_OF_DAY:
            raise ValueError("TIME_OF_DAY has no backing quote; it is always available")
        if not isinstance(quote, NormalizedQuote):
            raise ValueError(f"quote_by_input[{name!r}] must be a NormalizedQuote, got {quote!r}")
        result[name] = quote.health
    return result


def worst_health(quote_by_input: Mapping[InputName, NormalizedQuote]) -> DataHealth:
    """The worst-of health across the quotes backing a rule's inputs (AC-3).

    Order, worst first: unavailable > unhealthy > stale > delayed > available. Raises if ``quote_by_input`` is
    empty - a snapshot with no inputs at all has no health to derive.
    """
    healths = set(input_health_from_quotes(quote_by_input).values())
    if not healths:
        raise ValueError("quote_by_input must not be empty; there is no health to derive from zero quotes")
    for candidate in _SEVERITY_ORDER:
        if candidate in healths:
            return candidate
    raise AssertionError(f"unreachable: DataHealth is exhaustive, got {healths!r}")  # pragma: no cover


def build_snapshot(
    quote_by_input: Mapping[InputName, NormalizedQuote],
    values: Mapping[InputName, Decimal],
    as_of: datetime.datetime,
    *,
    source: str = "marketdata",
) -> Snapshot:
    """Build a :class:`Snapshot` whose overall ``data_health`` is DERIVED from ``quote_by_input`` (AC-3) - a
    caller never types the snapshot's health by hand. ``input_health`` is filled the same way.
    """
    return Snapshot(
        values=dict(values),
        as_of=as_of,
        data_health=worst_health(quote_by_input),
        source=source,
        input_health=input_health_from_quotes(quote_by_input),
    )
