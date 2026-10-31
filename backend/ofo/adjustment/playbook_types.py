"""The twelve playbook strategy types (REQ-158 AC-1): the keys (the fixture's family keys) live here; each type's
shown name lives in the wording catalogue's label table (ofo.errors.explanations.PLAYBOOK_TYPE_LABEL_TEXT, pinned
as `labels:playbook_type`). Read by the 0031 migration's CHECK (a test pins it), the playbook store and the body check.
"""
from __future__ import annotations

from collections.abc import Mapping

from ofo.errors.explanations import PLAYBOOK_TYPE_LABEL_TEXT

#: Order = the design note's table order.
TYPE_KEYS: tuple[str, ...] = ("strangle", "straddle", "ic", "ifly", "credit", "debit", "longopt", "longvol",
                              "calendar", "ratio", "dirfly", "other")
#: key -> the name a user sees (the catalogue's table, read here, never retyped).
SHOWN_NAMES: Mapping[str, str] = PLAYBOOK_TYPE_LABEL_TEXT
if tuple(SHOWN_NAMES) != TYPE_KEYS:  # fail closed at import: a key without a label, or a label without a key
    raise RuntimeError("playbook type keys and the catalogue's playbook_type labels differ")
#: REQ-158 AC-2 / ADR-216: the only system playbook whose numbers the owner approved.
APPROVED_SYSTEM_TYPES = frozenset({"ic"})
NAME_MAX = 80
BODY_SCHEMA = 1
