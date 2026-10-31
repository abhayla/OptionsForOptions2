# Playbook body, version 1 (GC-ADJ2 step 1)

The one stored shape of a playbook (REQ-158 AC-7: data, not code). Written once by the GC-ADJ2 run so the store
(step 1A), the evaluator (step 1B) and the editor (step 3) read the same thing. Source of every value:
`tests/fixtures/adjust_scenarios/_playbooks.json` (generator `tests/adjust_scenarios_gen.py`), with ADR-216 for the
iron condor.

## Strategy types

`strategy_type` is the fixture's family key. Twelve types (REQ-158 AC-1):

| key | shown name |
|---|---|
| strangle | Short strangle |
| straddle | Short straddle |
| ic | Iron condor |
| ifly | Iron butterfly |
| credit | Credit spreads |
| debit | Debit spreads |
| longopt | Single long option |
| longvol | Long straddle / strangle |
| calendar | Calendar / diagonal |
| ratio | Ratio and back-spreads |
| dirfly | Directional butterflies / condors |
| other | Naked shorts / futures / others |

## Body (JSON object)

```
{
  "schema": 1,
  "strategy_type": "ic",
  "stages": {"weekly": [{"name": "Early", "from": 5, "to": null}, ...],
             "monthly": [{"name": "Early", "from": 10, "to": null}, ...]},
  "triggers": {
    "T-01": {"on": true, "label": "...", "unit": "%", "cmp": "le", "data": "ok",
             "weekly": ["0.75", "0.5", "0.3"], "monthly": ["1.5", "1.0", "0.5"]},
    "T-20b": {"on": false, "greyed": "Needs price history (not in V1)", ...},
    ...every trigger of _playbooks.json "triggers", once
  },
  "rules": [{"id": "T-01", "any_of": ["T-01"]}, ...],
  "day_rules": [...as _playbooks.json "day_rules"],
  "situations": [...as _playbooks.json "situations"],
  "guards": {...as _playbooks.json "guards"},
  "approaches": {"applicable": [...], "off_in_playbook": [...], "greyed": [{"id": "A-09", "reason": "..."}]}
}
```

- Values are strings of decimals (never floats); `""` = no value in that stage (the trigger is not checked there).
  One value per stage, in stage order; the list length equals the stage count of that expiry kind.
- `on` comes from the family's `triggers_on`; a family's `triggers_greyed` entry sets `on: false` and `greyed`.
- `rules`: the default is one rule per ON trigger (`any_of` of one id), so rules combine as OR. A rule is either
  `{"id", "any_of": [ids]}` (fires when any member fires) or `{"id", "all_of": [ids]}` (fires when every member fires;
  REQ-159 AC-3, REQ-045 AC-3). A member that is NotChecked makes an `all_of` rule NotChecked, never fired.
- `tightened` (step 1B addition): the trigger ids a "Tighten every trigger by X%" day rule changes (an `le` limit x
  (1 + X/100), a `ge` limit x (1 - X/100)), copied from `_playbooks.json` `tightened_by_day_rule`.
- `T-21` is a guard, not a flag: while prices are stale or missing, or spot is not available, every rule answers
  NotChecked and the evaluation carries `withheld` (the reason); it never produces a Flag.
- A float anywhere in a body, or a stage value list whose length is not the stage count, is refused (ValueError).
- Iron condor (`ic`): status `approved`, T-19 is `["1", "1", "1"]` weekly and monthly (ADR-216, owner 2026-10-31);
  every other value as `_playbooks.json`. Every other type: status `draft`.

## Evaluation result (step 1B, `backend/ofo/adjustment/playbook_eval.py`)

Per rule, one of:
- `Flag(rule_id, trigger_id, stage_name, value, threshold, cmp)` - "Your rule was triggered" (a user playbook) or
  "Adjustment opportunity detected" (a system playbook); value and threshold exact Decimals;
- `NotChecked(rule_id, trigger_id, reason)` - data missing, never passed (REQ-160 AC-3);
- `AlreadyTrue(rule_id, trigger_id, value, threshold)` - "Already true when tracking started" (F-71).

## F-71 rule (crossing, not level)

Memory per (strategy, rule): `held_at_entry` (the condition evaluated on the entry state), `seen_clear` (the
condition was evaluated false at some check since entry). A rule that held at entry returns AlreadyTrue until a check
finds it false (`seen_clear` becomes true); from then on it flags like any other rule. A rule that did not hold at
entry flags as soon as it holds. The memory is stored per strategy (step 1A table `adjustment_rule_state`); the
evaluator is pure and takes and returns it.
