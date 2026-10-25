"""REQ-078 AC-2: the shape families a Width or Hedge control applies to, read from the catalogue's data.

The not-applicable texts name the shapes ("Width applies to straddles, strangles, iron butterflies and iron condors.").
No template id or name is typed in code: a family is a template's ``family_plural`` label, picked by the same data the
controls use (``width_adjustable`` for Width, a ``protective`` leg for Hedge). Order: fewest legs first, then
alphabetical, so the list reads the same on every run and is the AC's own order.
"""
from __future__ import annotations

import functools

from ofo.strategy.loader import load_templates
from ofo.strategy.model import Template

WIDTH, HEDGE = "width", "hedge"


def _applies(template: Template, control: str) -> bool:
    if control == WIDTH:
        return template.width_adjustable
    if control == HEDGE:
        return any(leg.protective for leg in template.legs)
    raise ValueError(f"no shape families for control {control!r}")


@functools.lru_cache(maxsize=1)
def reviewed_family_labels() -> frozenset[str]:
    return frozenset(t.family_plural for t in load_templates() if t.family_plural)


def control_families(control: str) -> tuple[str, ...]:
    """The family labels of every template the ``control`` applies to, deduplicated, fewest legs first."""
    found: dict[str, int] = {}
    for template in load_templates():
        if _applies(template, control):
            if not template.family_plural:
                raise ValueError(f"template {template.id!r} takes {control} but has no family_plural label")
            found[template.family_plural] = min(found.get(template.family_plural, 99), len(template.legs))
    return tuple(sorted(found, key=lambda label: (found[label], label)))
