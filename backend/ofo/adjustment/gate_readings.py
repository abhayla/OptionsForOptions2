"""One evaluation -> the alert gate's readings (GC-ALERT1 wire-a; REQ-170 AC-1..AC-3, ADR-237 (1)/(2), ADR-217).

The one function that turns a ``playbook_eval.Evaluation`` into ``alert_gate.step`` readings (finding
engine-input-chosen-per-caller: the worker and every test call this, none builds its own). Pure: no clock, no I/O.

- A checked rule (flagged or false) reads its lead trigger's value; a ge / le rule's ladder is its current threshold
  then the playbook's later-stage thresholds of this expiry kind (``alert_gate.ladder_for``), e.g. T-03 weekly Early
  0.30 -> (0.30, 0.35, 0.40).
- A yes/no rule reads True / False with no ladder (ADR-237 (1): re-arms at a false close): T-02 (``lt`` 0), a clock
  rule (T-10b, an "HH:MM" value), and a rule combining several triggers (one value cannot stand for an AND / OR).
- A NotChecked or AlreadyTrue rule, a withheld check, or a rule with no value reads None: neither clears nor opens
  (ADR-217; F-71). Its RuleSpec is a yes/no placeholder the gate never reads (a None value gives no sample).
- Fails closed: a comparison the gate does not know, or a value whose level disagrees with the evaluator's own
  exact flag, raises ValueError; it is never guessed.
"""
from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from ofo.adjustment import alert_gate as gate
from ofo.adjustment.playbook_eval import AlreadyTrue, Evaluation, NotChecked, RuleValue

Reading = tuple[gate.RuleSpec, gate.Value | None]


def _yes_no(v: RuleValue) -> Reading:
    return gate.RuleSpec(v.rule_id, "bool", ()), v.fired


def reading(v: RuleValue) -> Reading:
    """One checked rule's reading; ValueError on an unknown comparison or a value that disagrees with its flag."""
    if v.members > 1 or isinstance(v.value, str) or v.cmp == "lt":
        return _yes_no(v)
    if v.cmp not in ("ge", "le"):
        raise ValueError(f"rule {v.rule_id}: the alert gate does not know the cmp {v.cmp!r}")
    if not isinstance(v.threshold, Decimal):
        raise ValueError(f"rule {v.rule_id}: a {v.cmp} rule needs a decimal threshold, got {v.threshold!r}")
    later = tuple(x for x in v.later if isinstance(x, Decimal))
    spec = gate.RuleSpec(v.rule_id, v.cmp, gate.ladder_for(v.cmp, v.threshold, later))
    if (gate.level_of(spec, v.value) >= 0) != v.fired:
        raise ValueError(f"rule {v.rule_id}: value {v.value} disagrees with the evaluator's flag {v.fired}")
    return spec, v.value


def readings(evaluation: Evaluation) -> Mapping[str, Reading]:
    """Every rule of the evaluation -> (RuleSpec, value | None)."""
    out: dict[str, Reading] = {}
    for r in evaluation.results:
        if isinstance(r, (NotChecked, AlreadyTrue)):
            out[r.rule_id] = (gate.RuleSpec(r.rule_id, "bool", ()), None)
    for rule_id in evaluation.clear:
        out.setdefault(rule_id, (gate.RuleSpec(rule_id, "bool", ()), None))
    for v in evaluation.values:
        out[v.rule_id] = reading(v)
    return out
