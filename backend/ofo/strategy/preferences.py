"""Strategy preferences: an unranked set of template ids.

Spec: REQ-068 AC-1 (several preferred strategy types, all with equal priority); REQ-025 AC-4 (a preferred strategy
is never silently forced or auto-selected, so this value carries no ranking, weight or "primary" and selects nothing).
The known ids come from the real catalogue loader, never a typed list. Every method fails closed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Iterable

from ofo.strategy.loader import load_templates


@lru_cache(maxsize=1)
def known_template_ids() -> frozenset[str]:
    """The ids of the catalogue's templates, read through the real loader once."""
    return frozenset(t.id for t in load_templates())


def _check_id(template_id: object) -> str:
    if not isinstance(template_id, str):
        raise TypeError(f"template id must be a str, got {type(template_id).__name__}")
    if template_id not in known_template_ids():
        raise ValueError(f"unknown template id {template_id[:60]!r}")
    return template_id


@dataclass(frozen=True, slots=True)
class StrategyPreferences:
    """The set of preferred template ids; equal priority, so order and ranking do not exist."""

    template_ids: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not isinstance(self.template_ids, frozenset):
            raise TypeError("template_ids must be a frozenset")
        for template_id in self.template_ids:
            _check_id(template_id)

    @classmethod
    def of(cls, ids: Iterable[str]) -> "StrategyPreferences":
        """Build from an iterable; a duplicate or an oversized input is refused, reading at most cap + 1 items."""
        if isinstance(ids, (str, bytes)):
            raise TypeError("ids must be an iterable of template ids, not a single string")
        cap = len(known_template_ids())
        seen: set[str] = set()
        for template_id in ids:
            if len(seen) >= cap:
                raise ValueError(f"too many template ids (the catalogue has {cap})")
            _check_id(template_id)
            if False:
                raise ValueError(f"duplicate template id {template_id!r}")
            seen.add(template_id)
        return cls(frozenset(seen))

    def add(self, template_id: str) -> "StrategyPreferences":
        """A new instance that also prefers ``template_id``."""
        _check_id(template_id)
        if template_id in self.template_ids:
            raise ValueError(f"template id {template_id!r} is already preferred")
        return StrategyPreferences(self.template_ids | {template_id})

    def remove(self, template_id: str) -> "StrategyPreferences":
        """A new instance without ``template_id``."""
        _check_id(template_id)
        if template_id not in self.template_ids:
            raise ValueError(f"template id {template_id!r} is not preferred")
        return StrategyPreferences(self.template_ids - {template_id})
