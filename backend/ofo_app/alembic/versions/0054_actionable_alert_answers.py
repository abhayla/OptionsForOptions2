"""Actionable alerts stay open until the user answers: kind, answer, answered_at, no_longer_true_since (ADR-330 (3)(4)).

Spec basis: ADR-330 (3) ("Such an alert does not close, lapse or leave the Active list until the user himself
acknowledges it and takes his call: exit the position, or continue with the position ... if its condition later stops
being true it adds 'no longer true since HH:MM' and still stays. His answer and its time are kept with the alert in
History"), (4) (the bell counts the unanswered actionable alerts); supersedes ADR-237 (4) lapse for actionable records.
ADR-048 (limited app role, allow-list); 0031 / 0036 (the suggestion guard, copied and extended).

Changes (owner-run, one transaction; ADDITIVE columns, no back-fill, old rows keep NULL):
- public.adjustment_suggestions: kind TEXT NULL (CHECK in KINDS = ofo.alerts kinds, a test compares), answer TEXT NULL
  (CHECK in ANSWERS), answered_at TIMESTAMPTZ NULL, no_longer_true_since TIMESTAMPTZ NULL,
  escalated_at TIMESTAMPTZ NULL (the last time a WORSE value of the same rule updated this open alert; the existing
  ``worse`` column keeps its meaning, how the row was opened relative to an earlier record, and never changes),
  CHECK (answer and answered_at are both set or both NULL).
- Guard adjustment_suggestions_guard (0036's, every protection kept) plus:
  * a record of a kind (kind NOT NULL) leaves 'open' only with an answer; the one exception is a level_watch record
    (ADR-242 (3): one record per crossing episode, no answer asked), which may lapse with reason condition_stopped;
    a 'lapsed' one only as 'closed_by_system'
    and 'closed_by_system' only with 'lapsed' (no path closes an actionable record without the user or the position);
  * the answer and its time are written once, with the final outcome;
  * no_longer_true_since and escalated_at change only while the record is open and stays open;
  * stage, value and threshold change only while the record is open and stays open (a worse escalation updates the
    open row); id, strategy, rule, trigger, shown_at (= "Fired at"), worse and kind never change;
  * an INSERT names its kind (NULL refused) and is open and unanswered (an actionable kind), or an informational
    note (kind stop_fired, settled, orders_placed or stop_saved only): outcome 'dismissed', answer 'noted',
    answered_at set (History only, never open, so never counted); 'noted' is never written by an UPDATE.
- Grants: INSERT (shown_at, kind, outcome, answer, answered_at) (shown_at = the event time "Fired at", never in the
  future); UPDATE (stage, value, threshold, answer, answered_at,
  no_longer_true_since, escalated_at). public.ofo_assert_app_role_allowlist: block 23's suggestion part re-pinned.
- downgrade: refuses (OF031) while any row has a kind, answer or no_longer_true_since; otherwise restores 0036's guard.

Revision ID: 0054_actionable_alert_answers
Revises: 0053_close_finished_strategies
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "0054_actionable_alert_answers"
down_revision = "0053_close_finished_strategies"
branch_labels = None
depends_on = None


def _load(filename: str, name: str):
    path = Path(__file__).with_name(filename)
    found = importlib.util.spec_from_file_location(name, path)
    if found is None or found.loader is None:
        raise RuntimeError(f"cannot load the migration {path}")
    module = importlib.util.module_from_spec(found)
    found.loader.exec_module(module)
    return module


_M31 = _load("0031_adjustment_playbooks.py", "ofo_migration_0031_for_0054")
_M36 = _load("0036_alert_gate_storage.py", "ofo_migration_0036_for_0054")
_M52 = _load("0052_strategy_held_entries.py", "ofo_migration_0052_for_0054")
_M4 = _M36._M4
_BASE = _M36._BASE

SUGGESTIONS = _M31.SUGGESTIONS
GUARD = _M36.SUGGESTION_GUARD
#: copy of ``ofo.alerts`` kinds (a test compares the two)
KINDS = ("plan_loss_stop", "plan_profit_target", "plan_rupee_loss", "plan_rupee_profit", "plan_time_exit",
         "adjustment_rule", "side_closed", "level_watch", "stop_fired", "settled", "orders_placed", "stop_saved")
# ofo.alerts: actionable False (a test compares)
INFORMATIONAL_KINDS = ("stop_fired", "settled", "orders_placed", "stop_saved")
ANSWERS = ("exit", "continue", "add_legs", "confirm_new_shape", "closed_by_system", "noted")
NEW_COLUMNS = ("kind", "answer", "answered_at", "no_longer_true_since", "escalated_at")
INSERT_COLUMNS = (*_M36.SUGGESTION_INSERT_COLUMNS, "shown_at", "kind", "outcome", "answer", "answered_at")
UPDATE_COLUMNS = (*_M36.SUGGESTION_UPDATE_COLUMNS, "stage", "value", "threshold", "answer", "answered_at",
                  "no_longer_true_since", "escalated_at")
_FINAL = "('dismissed', 'acted_on', 'lapsed')"


def _list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def guard_sql() -> str:
    raise_ = _M31._raise
    return _M31._fn("adjustment_suggestions_guard", f"""
            IF TG_OP = 'DELETE' THEN
                {raise_('a suggestion record is never deleted')}
            END IF;
            IF TG_OP = 'INSERT' THEN
                IF NEW.shown_at > clock_timestamp() THEN
                    {raise_('a suggestion is never shown in the future')}
                END IF;
                IF NEW.kind IS NULL THEN
                    {raise_('a new suggestion record names its kind')}
                END IF;
                IF NEW.answer IS NULL THEN
                    IF NEW.kind IN ({_list(INFORMATIONAL_KINDS)}) THEN
                        {raise_('an informational note is never open: it is stored already noted')}
                    END IF;
                    IF NEW.outcome <> 'open' OR NEW.dismiss_reason IS NOT NULL OR NEW.answered_at IS NOT NULL
                       OR NEW.no_longer_true_since IS NOT NULL OR NEW.escalated_at IS NOT NULL THEN
                        {raise_('a suggestion record starts open')}
                    END IF;
                ELSIF NOT (NEW.answer = 'noted' AND NEW.outcome = 'dismissed' AND NEW.dismiss_reason IS NULL
                           AND NEW.kind IN ({_list(INFORMATIONAL_KINDS)}) AND NEW.answered_at IS NOT NULL
                           AND NEW.no_longer_true_since IS NULL AND NEW.escalated_at IS NULL) THEN
                    {raise_('only an informational note is stored already answered')}
                END IF;
                RETURN NEW;
            END IF;
            IF (NEW.id, NEW.strategy_id, NEW.rule_id, NEW.trigger_id, NEW.shown_at, NEW.worse, NEW.kind)
               IS DISTINCT FROM (OLD.id, OLD.strategy_id, OLD.rule_id, OLD.trigger_id, OLD.shown_at, OLD.worse,
                                 OLD.kind) THEN
                {raise_('the strategy, rule, trigger, kind and first-shown time of a suggestion never change')}
            END IF;
            IF (NEW.stage, NEW.value, NEW.threshold) IS DISTINCT FROM (OLD.stage, OLD.value, OLD.threshold)
               AND NOT (OLD.outcome = 'open' AND NEW.outcome = 'open') THEN
                {raise_('the stage, value and threshold of a suggestion change only while it is open and stays open')}
            END IF;
            IF NEW.outcome IS DISTINCT FROM OLD.outcome AND NOT (
               (OLD.outcome = 'open' AND NEW.outcome IN {_FINAL})
               OR (OLD.outcome = 'acted_on' AND NEW.outcome IN ('completed', 'partly_completed'))) THEN
                {raise_('a suggestion has at most one final outcome')}
            END IF;
            IF NEW.dismiss_reason IS DISTINCT FROM OLD.dismiss_reason
               AND NOT (OLD.outcome = 'open' AND NEW.outcome = 'dismissed') THEN
                {raise_('a dismiss reason is written once, with the dismissal')}
            END IF;
            IF NEW.answer IS DISTINCT FROM OLD.answer
               AND NOT (OLD.answer IS NULL AND OLD.outcome = 'open' AND NEW.outcome IN {_FINAL}) THEN
                {raise_('an answer is written once, with the final outcome')}
            END IF;
            IF NEW.answer = 'noted' AND OLD.answer IS DISTINCT FROM 'noted' THEN
                {raise_('a note is stored already noted; an open record is never noted afterwards')}
            END IF;
            IF NEW.answered_at IS DISTINCT FROM OLD.answered_at AND NEW.answer IS NOT DISTINCT FROM OLD.answer THEN
                {raise_('the answer time is written only with the answer')}
            END IF;
            IF OLD.outcome = 'open' AND NEW.outcome IN {_FINAL} AND OLD.kind IS NOT NULL AND NEW.answer IS NULL
               AND NOT (OLD.kind = 'level_watch' AND NEW.outcome = 'lapsed'
                        AND (NEW.timeline -> -1 ->> 'reason') = 'condition_stopped') THEN
                {raise_('a record of a kind leaves open only with an answer')}
            END IF;
            IF NEW.kind IS NOT NULL AND (NEW.outcome = 'lapsed') IS DISTINCT FROM (NEW.answer = 'closed_by_system')
               AND NEW.answer IS NOT NULL THEN
                {raise_('closed_by_system goes with lapsed, and only with it')}
            END IF;
            IF (NEW.no_longer_true_since, NEW.escalated_at)
               IS DISTINCT FROM (OLD.no_longer_true_since, OLD.escalated_at)
               AND NOT (OLD.outcome = 'open' AND NEW.outcome = 'open') THEN
                {raise_('no longer true since and escalated at change only while the record is open and stays open')}
            END IF;
            IF NEW.outcome IS DISTINCT FROM OLD.outcome AND (
               jsonb_array_length(NEW.timeline) <> jsonb_array_length(OLD.timeline) + 1
               OR (NEW.timeline -> -1 ->> 'outcome') IS DISTINCT FROM NEW.outcome
               OR (NEW.timeline -> -1 ->> 'suggestion_id') IS DISTINCT FROM NEW.id::text) THEN
                {raise_('an outcome change appends exactly one timeline entry naming it and the suggestion')}
            END IF;
            IF jsonb_array_length(NEW.timeline) < jsonb_array_length(OLD.timeline)
               OR (SELECT coalesce(jsonb_agg(e ORDER BY i), '[]'::jsonb)
                   FROM jsonb_array_elements(NEW.timeline) WITH ORDINALITY AS t(e, i)
                   WHERE i <= jsonb_array_length(OLD.timeline)) IS DISTINCT FROM OLD.timeline THEN
                {raise_('a suggestion timeline is append-only')}
            END IF;
            RETURN NEW;""")  # noqa: S608 constant names


PREVIOUS_GUARD_PIN = _M36.SUGGESTION_PIN
GUARD_PIN = _M4._md5_body(guard_sql())


def _new_block() -> str:
    block = _M31._table_block(SUGGESTIONS, _M36.SUGGESTION_LABEL, GUARD, _M36.SUGGESTION_TRIGGER, False,
                              INSERT_COLUMNS, UPDATE_COLUMNS)
    if block.count(_M31.PINS[GUARD]) != 1:
        raise RuntimeError("0031's suggestion allow-list block changed shape: cannot re-pin it safely")
    return block.replace(_M31.PINS[GUARD], GUARD_PIN, 1)


def previous_allowlist_sql() -> str:
    return _M52.extended_allowlist_sql()  # 0053 does not touch the allow-list


def extended_allowlist_sql() -> str:
    """0052's chain text with block 23's suggestion part re-pinned and given the new columns. Fails closed."""
    previous = previous_allowlist_sql()
    old = _M36._new_suggestion_block()
    if previous.count(old) != 1:
        raise RuntimeError("previous allowlist SQL changed shape: cannot re-pin the suggestion checks safely")
    return previous.replace(old, _new_block(), 1)


def upgrade() -> None:
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(
        f"""
        ALTER TABLE {SUGGESTIONS}
            ADD COLUMN kind TEXT NULL CHECK (kind IS NULL OR kind IN ({_list(KINDS)})),
            ADD COLUMN answer TEXT NULL CHECK (answer IS NULL OR answer IN ({_list(ANSWERS)})),
            ADD COLUMN answered_at TIMESTAMPTZ NULL,
            ADD COLUMN no_longer_true_since TIMESTAMPTZ NULL,
            ADD COLUMN escalated_at TIMESTAMPTZ NULL,
            ADD CONSTRAINT adjustment_suggestions_answer_pair CHECK ((answer IS NULL) = (answered_at IS NULL))
        """
    )
    op.execute(guard_sql())
    op.execute(f'GRANT INSERT (shown_at, kind, outcome, answer, answered_at) ON TABLE {SUGGESTIONS} TO "{role}"')
    op.execute(f'GRANT UPDATE (stage, value, threshold, answer, answered_at, no_longer_true_since, escalated_at) '
               f'ON TABLE {SUGGESTIONS} TO "{role}"')
    op.execute(extended_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")


def downgrade() -> None:
    op.execute(
        f"""
        DO $down$
        DECLARE
            n BIGINT;
        BEGIN
            EXECUTE 'LOCK TABLE {SUGGESTIONS} IN ACCESS EXCLUSIVE MODE';
            EXECUTE 'SELECT count(*) FROM {SUGGESTIONS} WHERE kind IS NOT NULL OR answer IS NOT NULL '
                    'OR no_longer_true_since IS NOT NULL OR escalated_at IS NOT NULL' INTO n;
            IF n > 0 THEN
                RAISE EXCEPTION 'refusing to downgrade {revision}: % suggestions carry a kind or an answer', n
                    USING ERRCODE = '{_M31.SQLSTATE}';
            END IF;
        END
        $down$;
        """  # noqa: S608 constant names
    )
    role = _BASE._app_role()
    allowlist = _BASE.ALLOWLIST_FUNCTION
    op.execute(f"SELECT {allowlist}('{role}', 'pre')")
    op.execute(f'REVOKE INSERT (shown_at, kind, outcome, answer, answered_at) ON TABLE {SUGGESTIONS} FROM "{role}"')
    op.execute(f'REVOKE UPDATE (stage, value, threshold, answer, answered_at, no_longer_true_since, escalated_at) '
               f'ON TABLE {SUGGESTIONS} FROM "{role}"')
    op.execute(f"ALTER TABLE {SUGGESTIONS} DROP CONSTRAINT adjustment_suggestions_answer_pair")
    op.execute(_M36.suggestions_guard_sql())
    op.execute(f"ALTER TABLE {SUGGESTIONS} DROP COLUMN escalated_at, "
               "DROP COLUMN no_longer_true_since, DROP COLUMN answered_at, DROP COLUMN answer, DROP COLUMN kind")
    op.execute(previous_allowlist_sql())
    op.execute(f"REVOKE ALL ON FUNCTION {allowlist}(TEXT, TEXT) FROM PUBLIC")
    op.execute(f"SELECT {allowlist}('{role}', 'post')")
