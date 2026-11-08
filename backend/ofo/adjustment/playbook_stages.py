"""Playbook body checks the store does not make (GC-ADJ2 step 2; REQ-159 AC-1, docs/design/playbook-body-v1.md).

One function per check, used by the save routes and by the editor's Test, so both answer the same way:
- ``check_stages``: for each expiry kind the stages cover days 0 and up with no gap and no overlap; the refusal names
  the days and the stage names ("Days 2 to 4 are in both Near and Last"). A stage with ``to`` None is open: for naming
  it counts as ``OPEN_END`` days, the longest expiry the app lists.
- ``check_keys``: a key the body shape does not define is refused, never ignored (B4 (c)).
A refusal is a ``StageProblem``: a catalogue template id plus its slots; the caller renders it.
"""
from __future__ import annotations

from collections.abc import Mapping

OPEN_END = 366
NAME_MAX = 80
BODY_KEYS = frozenset({"schema", "strategy_type", "status", "stages", "triggers", "rules", "tightened", "day_rules",
                       "situations", "guards", "approaches"})
STAGE_KEYS = frozenset({"name", "from", "to"})
INVALID = "playbook_body_invalid"
OVERLAP = "playbook_stage_overlap"
GAP = "playbook_stage_gap"


class StageProblem(ValueError):
    def __init__(self, template: str, **slots: object) -> None:
        self.template = template
        self.slots = slots
        super().__init__(template)


def check_keys(body: Mapping) -> None:
    for key in body:
        if key not in BODY_KEYS:
            raise StageProblem(INVALID, field="body")  # never the key itself: it is the sender's text


def _span(kind: str, i: int, row: Mapping) -> tuple[int, int, str]:
    where = f"stages.{kind}.{i}"
    name, start, end = row["name"], row["from"], row["to"]
    if set(row) - STAGE_KEYS:
        raise StageProblem(INVALID, field=where)
    if name != name.strip() or len(name) > NAME_MAX or '"' in name:
        raise StageProblem(INVALID, field=f"{where}.name")
    if start < 0 or (end is not None and end < start):
        raise StageProblem(INVALID, field=where)
    return start, OPEN_END if end is None else end, name


def check_stages(body: Mapping) -> None:
    """``body`` has passed the store's ``check_body`` (two stage lists, each row a name and int from / to)."""
    for kind in ("weekly", "monthly"):
        spans = sorted((_span(kind, i, r) for i, r in enumerate(body["stages"][kind])), key=lambda s: (s[0], s[1]))
        for j, (start_b, end_b, name_b) in enumerate(spans):
            for start_a, end_a, name_a in spans[:j]:
                low, high = max(start_a, start_b), min(end_a, end_b)
                if low <= high:
                    raise StageProblem(OVERLAP, expiry=kind, from_day=low, to_day=high, first=name_a, second=name_b)
        cursor = 0
        for start, end, _name in spans:
            if start > cursor:
                raise StageProblem(GAP, expiry=kind, from_day=cursor, to_day=start - 1)
            cursor = max(cursor, end + 1)
        if cursor <= OPEN_END:
            raise StageProblem(GAP, expiry=kind, from_day=cursor, to_day=OPEN_END)
