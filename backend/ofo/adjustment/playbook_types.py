"""The twelve playbook strategy types (REQ-158 AC-1) and their shown names: the one table
(docs/design/playbook-body-v1.md "Strategy types"). Read by the 0031 migration's CHECK, the playbook store,
the body check and the error slots.
No imports: the error catalogue reads it lazily."""
from __future__ import annotations

from types import MappingProxyType

#: key (the fixture's family key) -> the name a user sees. Order = the design note's table order.
SHOWN_NAMES = MappingProxyType({
    "strangle": "Short strangle",
    "straddle": "Short straddle",
    "ic": "Iron condor",
    "ifly": "Iron butterfly",
    "credit": "Credit spreads",
    "debit": "Debit spreads",
    "longopt": "Single long option",
    "longvol": "Long straddle / strangle",
    "calendar": "Calendar / diagonal",
    "ratio": "Ratio and back-spreads",
    "dirfly": "Directional butterflies / condors",
    "other": "Naked shorts / futures / others",
})
TYPE_KEYS: tuple[str, ...] = tuple(SHOWN_NAMES)
#: REQ-158 AC-2 / ADR-216: the only system playbook whose numbers the owner approved.
APPROVED_SYSTEM_TYPES = frozenset({"ic"})
NAME_MAX = 80
BODY_SCHEMA = 1
