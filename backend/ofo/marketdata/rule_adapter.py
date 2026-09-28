"""Adapter from quote health to the rule engine's input-health map (REQ-049 AC-3).

``ofo.rules.inputs.Snapshot`` already carries an ``input_health`` map keyed by ``InputName`` and already treats any
input whose health is not ``available`` as unusable (never live). This adapter is therefore a direct translation:
which quote backs which named input, so the health this module derived (:mod:`ofo.marketdata.health`) reaches the
rule engine without re-deriving or weakening it. A stale (or delayed/unhealthy/unavailable) quote can never make a
rule TRIGGER, because the deciding comparison becomes ``Truth.UNKNOWN`` (``ofo.rules.conditions.decide``) the
moment its input's health is not ``available``.
"""
from __future__ import annotations

from typing import Mapping

from ofo.marketdata.quote import NormalizedQuote
from ofo.rules.inputs import DataHealth, InputName


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
