"""The one place `ofo_app.api_models` reads a class's own namespace (W-024 round 10 item 2).

Kept apart from api_models.py so it imports nothing from `ofo` or `ofo_app`: the engine pricing scan
(tests/engine/test_pricing_scan.py) exempts this file from its `.__dict__` rule on exactly that condition.
"""

from __future__ import annotations


def own_names(cls: type) -> tuple[str, ...]:
    """Every name defined in `cls`'s own class body (not inherited), sorted."""
    return tuple(sorted(cls.__dict__))
