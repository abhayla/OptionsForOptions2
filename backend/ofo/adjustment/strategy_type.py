"""Which playbook type (REQ-158 AC-1, docs/design/playbook-body-v1.md "Strategy types") a tracked leg set is
(GC-ADJ2 step 1C). The template -> type map is data (``template_types.json``, REQ-158 AC-7), not code.

``type_of`` matches the legs through ``ofo.strategy.matching.match`` (the one matcher). Fail closed (B4 c): a Custom
match, a template the map does not name, a leg set the matcher refuses, or an ambiguous catalogue answer -> None
(the generic triggers and approaches, REQ-161 AC-4), never a guessed type.
"""
from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from decimal import Decimal
from functools import cache
from pathlib import Path
from types import MappingProxyType
from typing import Final

from ofo.adjustment.playbook_types import TYPE_KEYS
from ofo.engine.legs import Leg
from ofo.instruments.catalogue import Catalogue
from ofo.strategy.loader import load_templates
from ofo.strategy.matching import MatchResult, match
from ofo.strategy.model import Template, TemplateError

TEMPLATE_TYPES_PATH: Final = Path(__file__).with_name("template_types.json")


@cache
def template_types() -> Mapping[str, str]:
    """catalogue template id -> playbook type key; refused at load when a value is not one of the twelve keys."""
    data = json.loads(TEMPLATE_TYPES_PATH.read_text(encoding="utf-8"))  # float-ok: ids and keys only, no money
    bad = {k: v for k, v in data.items() if v not in TYPE_KEYS}
    if bad:
        raise ValueError(f"template_types.json maps to unknown playbook types: {bad}")
    return MappingProxyType(dict(data))


@cache
def _templates() -> tuple[Template, ...]:
    return load_templates()


def type_of(legs: Sequence[Leg], spot: Decimal | None, strike_gap: Decimal | None,
            templates: Iterable[Template] | None = None) -> str | None:
    """The playbook type key of ``legs``; None for a shape that is not one of the mapped templates (generic)."""
    if not legs or spot is None or strike_gap is None or spot <= 0 or strike_gap <= 0:
        return None
    try:
        found = match(legs, spot=spot, strike_gap=strike_gap,
                      templates=_templates() if templates is None else templates)
    except (TemplateError, ValueError, ArithmeticError):
        return None  # the matcher could not resolve the shape (or the catalogue is ambiguous): generic, never a guess
    if not isinstance(found, MatchResult):
        return None
    return template_types().get(found.template.id)


def strike_gap_of(listed: Iterable, underlying: str, expiries: Iterable[date]) -> Decimal | None:
    """The near-the-money strike gap by ``Catalogue.strike_gap`` (the one rule) over the listed contracts a market
    context holds: the smallest over the legs' expiries; None when it cannot be derived (no strikes, no expiry)."""
    cat = Catalogue()
    try:
        cat.load([lc for lc in listed if lc.contract.name == underlying])
        gaps = [cat.strike_gap(underlying, e) for e in set(expiries)]
    except ValueError:
        return None
    return min(gaps) if gaps else None
