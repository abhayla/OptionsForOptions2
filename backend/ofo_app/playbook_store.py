"""PostgreSQL store of adjustment playbooks, the active choice, a strategy's plan, the F-71 rule memory and the
suggestion record (GC-ADJ2 step 1A; REQ-158, REQ-161 AC-1..AC-3, REQ-112 AC-1/AC-2/AC-4). Schema: migration 0031.
Body shape: docs/design/playbook-body-v1.md.

- The user always comes from the caller (the signed-in session), never from a body. Another user's playbook or
  strategy answers `playbook_not_found` / `not_found` exactly like a missing one.
- A system playbook is read-only: save_in_place refuses it (`system_playbook_save_in_place`), and the database guard
  refuses any UPDATE or DELETE of it by the application role (SQLSTATE OF031) whatever this module does.
- Names are unique per user and type, case-insensitive (`playbook_name_taken`, carrying the name and the type's shown
  name). Every body is checked before any write (`playbook_body_invalid`, naming the field).
- A system playbook's numbers are its CURRENT version (REQ-169, migration 0034: the newest row of
  system_playbook_versions): get / list_for_type / active_for answer that version's body, status, number and time,
  so a strategy tracked on the system playbook gets an admin's new version at its next check, and a copy or a plan
  made earlier keeps the body it copied (ADR-222 (9)).
- active_for: the user's active row, else the type's system playbook (no row = system). Deleting the active playbook
  removes its active row (FK cascade) and the answer says the system playbook is active again (REQ-158 AC-4).
- accept_plan COPIES the body into the strategy's plan; a later edit or delete of the playbook never changes it
  (REQ-158 AC-5); a deleted playbook leaves the plan's playbook_id NULL.
The caller commits.
"""
from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from ofo.adjustment.gate_rows import GateRow, GateRows
from ofo.adjustment.playbook_eval import validate_body
from ofo.adjustment.playbook_types import BODY_SCHEMA, NAME_MAX, SHOWN_NAMES
from ofo.errors.explanations import render_explanation
from ofo.settings import layers
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from ofo_app import strategy_store
from ofo_app.sql_time import IST_SQL_ZONE

NAME_TAKEN = "playbook_name_taken"
SYSTEM_SAVE_IN_PLACE = "system_playbook_save_in_place"
VERSION_CONFLICT = "playbook_version_conflict"
NOT_FOUND = "playbook_not_found"
BODY_INVALID = "playbook_body_invalid"
NAME_INDEX = "adjustment_playbooks_name"
SUGGESTION_FINAL = ("dismissed", "acted_on", "lapsed")
SUGGESTION_NOT_FOUND = "suggestion_not_found"
SUGGESTION_NOT_OPEN = "suggestion_not_open"
#: REQ-112 AC-2: the Dismiss reasons, a short closed list (the shown words live in the catalogue)
DISMISS_REASONS = ("expected_within_plan", "will_act_later", "not_relevant", "other")
#: why a record lapsed (REQ-112 AC-2), written into its timeline entry (the dismiss reason column is Dismiss's only)
LAPSE_CONDITION_STOPPED = "condition_stopped"
LAPSE_STRATEGY_CLOSED = "strategy_closed"
#: Review round 2, finding 5: an escalation closed the record because a worse one of the same rule opened.
LAPSE_SUPERSEDED_BY_WORSE = "superseded_by_worse"
LAPSE_REASONS = (LAPSE_CONDITION_STOPPED, LAPSE_STRATEGY_CLOSED, LAPSE_SUPERSEDED_BY_WORSE)
WORSE_MARKS = (None, "last", "dismissed")  # = migration 0036 WORSE plus none (a test asserts it)
HELD_REASONS = ("daily_limit", "quiet_time")  # = alert_gate.HELD_DAILY_LIMIT / HELD_QUIET_TIME
SOURCE_SYSTEM = "system"  # "Adjustment opportunity detected" (a system playbook's flag)
SOURCE_OWN = "own"  # "Your rule was triggered" (the user's own playbook or the strategy's plan)
_DECIMAL = re.compile(r"-?[0-9]+(\.[0-9]+)?")
_ID = re.compile(r"[A-Za-z0-9_.\-]{1,40}")
_CLOCK = re.compile(r"([01][0-9]|2[0-3]):[0-5][0-9]")


class PlaybookStoreError(ValueError):
    def __init__(self, code: str, detail: str, **slots: str) -> None:
        self.code = code
        self.detail = detail
        self.slots = slots
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class Playbook:
    id: int
    user_ref: str | None
    strategy_type: str
    name: str
    is_system: bool
    status: str
    body: dict
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class DeleteAnswer:
    deleted: int
    active_now_system: bool
    message: str | None  # "<type>: the system playbook is active again" when the active one was deleted


@dataclass(frozen=True)
class Plan:
    strategy_id: int
    playbook_id: int | None
    strategy_type: str
    body: dict
    accepted_at: datetime


@dataclass(frozen=True)
class Suggestion:
    id: int
    strategy_id: int
    rule_id: str
    trigger_id: str | None
    stage: str | None
    value: Decimal | None
    threshold: Decimal | None
    shown_at: datetime
    outcome: str
    dismiss_reason: str | None
    timeline: list

    @property
    def group(self) -> str | None:
        """REQ-045 AC-8: the check that opened it; records of one strategy at one check share it."""
        return self.timeline[0].get("group") if self.timeline else None

    @property
    def source(self) -> str | None:
        """system / own: which label the flag carried when it was shown (REQ-045 AC-1)."""
        return self.timeline[0].get("source") if self.timeline else None

    @property
    def cmp(self) -> str | None:
        """le / ge / lt: the flag's comparison when it was shown (its condition in plain words)."""
        return self.timeline[0].get("cmp") if self.timeline else None

    @property
    def label(self) -> str | None:
        """The trigger's label as the evaluated body held it when the flag was shown (None on an older record)."""
        return self.timeline[0].get("label") if self.timeline else None

    @property
    def approach(self) -> str | None:
        """ADR-221: the T-19 record's cheapest priced approach when it was shown (None: not T-19, or older)."""
        return self.timeline[0].get("approach") if self.timeline else None

    @property
    def approach_cost(self) -> Decimal | None:
        """That approach's Compare cost when the record opened (stored as exact text)."""
        raw = self.timeline[0].get("approach_cost") if self.timeline else None
        return None if raw is None else Decimal(raw)

    @property
    def unpriced(self) -> int:
        """How many offered approaches could not be priced at that check (left out of the pick)."""
        raw = self.timeline[0].get("unpriced") if self.timeline else None
        return raw if isinstance(raw, int) else 0

    @property
    def unit(self) -> str | None:
        """The trigger's unit as the evaluated body held it when the flag was shown (None on an older record)."""
        return self.timeline[0].get("unit") if self.timeline else None

    @property
    def placed_order_ids(self) -> tuple[int, ...] | None:
        """REQ-163 AC-1: the paper orders the basket acted on from this record placed (its ``orders_placed`` timeline
        entry, written once by ``link_orders``); None when no basket names it, () when the entry is unreadable."""
        found = [e for e in self.timeline if isinstance(e, dict) and e.get("event") == ORDERS_PLACED]
        if not found:
            return None
        ids = found[0].get("order_ids")
        return tuple(ids) if isinstance(ids, list) and all(type(i) is int for i in ids) else ()

    @property
    def basket_legs(self) -> int | None:
        """How many legs the prepared basket held when it was placed (the ``orders_placed`` entry); None when the
        placement did not say, or the entry is unreadable."""
        found = [e for e in self.timeline if isinstance(e, dict) and e.get("event") == ORDERS_PLACED]
        legs = found[0].get("basket_legs") if found else None
        return legs if type(legs) is int and legs > 0 else None

    @property
    def shown_outcome(self) -> str:
        """REQ-112 AC-3 (IC e2e design 11): the outcome from what was actually placed. An acted-on record whose basket
        placed every leg it held is completed, some of them partly_completed; no basket named, the basket's size not
        said, no readable orders, or more orders than legs (inconsistent) stay acted_on. Others are as stored."""
        if self.outcome != "acted_on":
            return self.outcome
        placed, legs = self.placed_order_ids, self.basket_legs
        if not placed or legs is None or len(set(placed)) > legs:
            return "acted_on"
        return "completed" if len(set(placed)) == legs else "partly_completed"

    @property
    def lapse_reason(self) -> str | None:
        """condition_stopped / strategy_closed / superseded_by_worse on a lapsed record (its last timeline entry)."""
        return self.timeline[-1].get("reason") if self.outcome == "lapsed" and self.timeline else None


@dataclass(frozen=True)
class InboxRow:
    """One suggestion of the user's strategies for the inbox (REQ-162), with its strategy's saved name."""

    suggestion: Suggestion
    strategy_name: str
    paper: bool  # the strategy has paper orders: an acted-on basket is not sent to Zerodha (ADR-135)


_PB_COLUMNS = "id, user_ref, strategy_type, name, is_system, status, body::text, version, created_at, updated_at"
_VISIBLE = "(user_ref IS NULL OR user_ref = :user_ref)"
_SELECT_ONE = text(f"SELECT {_PB_COLUMNS} FROM public.adjustment_playbooks "  # noqa: S608 constant columns
                   f"WHERE id = :id AND {_VISIBLE}")
_SELECT_TYPE = text(f"SELECT {_PB_COLUMNS} FROM public.adjustment_playbooks "  # noqa: S608 constant columns
                    f"WHERE strategy_type = :type AND {_VISIBLE} ORDER BY is_system DESC, lower(name), id")
_SELECT_SYSTEM = text(f"SELECT {_PB_COLUMNS} FROM public.adjustment_playbooks "  # noqa: S608 constant columns
                      "WHERE strategy_type = :type AND is_system")
_SELECT_ACTIVE = text(f"SELECT {', '.join('p.' + c for c in _PB_COLUMNS.split(', '))} "  # noqa: S608 constant columns
                      "FROM public.adjustment_playbook_active a JOIN public.adjustment_playbooks p "
                      "ON p.id = a.playbook_id WHERE a.user_ref = :user_ref AND a.strategy_type = :type")
#: REQ-169: a system playbook's current version is the newest stored one (never the first, never the 0031 row's body)
_SYSTEM_CURRENT = text("SELECT version, status, body::text, saved_at FROM public.system_playbook_versions "
                       "WHERE strategy_type = :type ORDER BY version DESC LIMIT 1")
#: REQ-158 AC-3: the user's own names AND the type's system playbook's name (user_ref IS NULL) are taken
_NAME_USED = text("SELECT 1 FROM public.adjustment_playbooks WHERE (user_ref = :user_ref OR is_system) "
                  "AND strategy_type = :type "
                  "AND lower(name) = lower(:name) AND id IS DISTINCT FROM :id")
_INSERT = text("INSERT INTO public.adjustment_playbooks (user_ref, strategy_type, name, body) "  # noqa: S608
               f"VALUES (:user_ref, :type, :name, CAST(:body AS JSONB)) RETURNING {_PB_COLUMNS}")
_RENAME = text("UPDATE public.adjustment_playbooks SET name = :name "  # noqa: S608
               f"WHERE id = :id AND user_ref = :user_ref RETURNING {_PB_COLUMNS}")
_SAVE = text("UPDATE public.adjustment_playbooks SET body = CAST(:body AS JSONB) "  # noqa: S608
             f"WHERE id = :id AND user_ref = :user_ref AND version = :version RETURNING {_PB_COLUMNS}")
_IS_ACTIVE = text("SELECT strategy_type FROM public.adjustment_playbook_active "
                  "WHERE user_ref = :user_ref AND playbook_id = :id")
_DELETE = text("DELETE FROM public.adjustment_playbooks WHERE id = :id AND user_ref = :user_ref AND NOT is_system "
               "RETURNING id")
_MAKE_ACTIVE = text("INSERT INTO public.adjustment_playbook_active (user_ref, strategy_type, playbook_id) "
                    "VALUES (:user_ref, :type, :id) ON CONFLICT (user_ref, strategy_type) "
                    "DO UPDATE SET playbook_id = EXCLUDED.playbook_id")
_PLAN_COLUMNS = "strategy_id, playbook_id, strategy_type, body::text, accepted_at"
_UPSERT_PLAN = text("INSERT INTO public.strategy_adjustment_plans (strategy_id, playbook_id, strategy_type, body) "  # noqa: S608
                    "VALUES (:strategy_id, :playbook_id, :type, CAST(:body AS JSONB)) ON CONFLICT (strategy_id) "
                    "DO UPDATE SET playbook_id = EXCLUDED.playbook_id, body = EXCLUDED.body "
                    f"RETURNING {_PLAN_COLUMNS}")
_SELECT_PLAN = text(f"SELECT {', '.join('p.' + c for c in _PLAN_COLUMNS.split(', '))} "  # noqa: S608 constant columns
                    "FROM public.strategy_adjustment_plans p JOIN public.strategies s ON s.id = p.strategy_id "
                    "WHERE p.strategy_id = :strategy_id AND s.user_ref = :user_ref")
_OWNS_STRATEGY = text("SELECT 1 FROM public.strategies WHERE id = :strategy_id AND user_ref = :user_ref")
_SELECT_STATE = text("SELECT rule_id, held_at_entry, seen_clear FROM public.adjustment_rule_state "
                     "WHERE strategy_id = :strategy_id ORDER BY rule_id")
_PUT_STATE = text("INSERT INTO public.adjustment_rule_state (strategy_id, rule_id, held_at_entry, seen_clear) "
                  "VALUES (:strategy_id, :rule_id, :held, :seen) ON CONFLICT (strategy_id, rule_id) "
                  "DO UPDATE SET seen_clear = adjustment_rule_state.seen_clear OR EXCLUDED.seen_clear")
_SG_COLUMNS = ("id, strategy_id, rule_id, trigger_id, stage, value, threshold, shown_at, outcome, dismiss_reason, "
               "timeline::text")
_OPEN_FOR_RULE = text(f"SELECT {_SG_COLUMNS} FROM public.adjustment_suggestions "  # noqa: S608 constant columns
                      "WHERE strategy_id = :strategy_id AND rule_id = :rule_id AND outcome = 'open'")
_INSERT_SUGGESTION = text(
    "INSERT INTO public.adjustment_suggestions (strategy_id, rule_id, trigger_id, stage, value, threshold, worse, "  # noqa: S608
    "timeline) VALUES (:strategy_id, :rule_id, :trigger_id, :stage, :value, :threshold, CAST(:worse AS TEXT), "
    "jsonb_build_array(jsonb_build_object('at', clock_timestamp(), 'outcome', 'open', "
    "'group', CAST(:group AS TEXT), 'source', CAST(:source AS TEXT), 'cmp', CAST(:cmp AS TEXT), "
    "'label', CAST(:label AS TEXT), 'unit', CAST(:unit AS TEXT), 'approach', CAST(:approach AS TEXT), "
    "'approach_cost', CAST(:approach_cost AS TEXT), 'unpriced', CAST(:unpriced AS INTEGER), "
    "'carry', CAST(:carry AS JSONB)))) "
    f"RETURNING {_SG_COLUMNS}")
_CLOSE_SUGGESTION = text(
    "UPDATE public.adjustment_suggestions AS g SET outcome = CAST(:outcome AS TEXT), "  # noqa: S608
    "dismiss_reason = CAST(:reason AS TEXT), timeline = g.timeline || jsonb_build_array(jsonb_build_object("
    "'at', clock_timestamp(), 'outcome', CAST(:outcome AS TEXT), 'suggestion_id', g.id, "
    "'reason', CAST(:note AS TEXT))) "
    "FROM public.strategies s WHERE g.id = :id AND s.id = g.strategy_id "
    "AND s.user_ref = :user_ref AND g.outcome = 'open' "
    f"RETURNING {', '.join('g.' + c for c in _SG_COLUMNS.split(', '))}")
_SUGGESTION_OUTCOME = text("SELECT g.outcome FROM public.adjustment_suggestions g JOIN public.strategies s "
                           "ON s.id = g.strategy_id WHERE g.id = :id AND s.user_ref = :user_ref")
_OPEN_OF_STRATEGY = text(f"SELECT {', '.join('g.' + c for c in _SG_COLUMNS.split(', '))} "  # noqa: S608 constant
                         "FROM public.adjustment_suggestions g JOIN public.strategies s ON s.id = g.strategy_id "
                         "WHERE g.strategy_id = :strategy_id AND s.user_ref = :user_ref AND g.outcome = 'open' "
                         "ORDER BY g.id")
#: ADR-217 "cleared since dismissal" lives in the dismissed record's own timeline (migration 0031 allows an append
#: without an outcome change): one entry {'at', 'event': 'condition_cleared'}, written by the first check that finds
#: the rule false after the dismissal. The latest record of a rule that is dismissed and has no such entry is "held".
_LATEST_DISMISSED = text(
    f"SELECT {', '.join('g.' + c for c in _SG_COLUMNS.split(', '))} "  # noqa: S608 constant columns
    "FROM public.adjustment_suggestions g JOIN public.strategies s ON s.id = g.strategy_id "
    "WHERE g.strategy_id = :strategy_id AND s.user_ref = :user_ref AND g.outcome = 'dismissed' "
    "AND g.id = (SELECT max(m.id) FROM public.adjustment_suggestions m "
    "WHERE m.strategy_id = g.strategy_id AND m.rule_id = g.rule_id) "
    "AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements(g.timeline) e WHERE e ->> 'event' = 'condition_cleared')")
_MARK_CLEARED = text(
    "UPDATE public.adjustment_suggestions AS g SET timeline = g.timeline || jsonb_build_array(jsonb_build_object("
    "'at', clock_timestamp(), 'event', 'condition_cleared')) "
    "FROM public.strategies s WHERE g.id = :id AND s.id = g.strategy_id AND s.user_ref = :user_ref "
    "AND g.outcome = 'dismissed'")
#: REQ-163 AC-1 (GC-IC1 step 10): an acted-on record names the paper orders its basket placed, so the history can say
#: why the adjustment was made. One timeline entry {'at', 'event': 'orders_placed', 'order_ids': [...]} (migration 0031
#: allows an append without an outcome change), written once, in the placement's own transaction, and only on a record
#: of the SAME strategy and user that is acted on and names no basket yet.
ORDERS_PLACED = "orders_placed"
_LINK_ORDERS = text(
    "UPDATE public.adjustment_suggestions AS g SET timeline = g.timeline || jsonb_build_array(jsonb_build_object("
    "'at', clock_timestamp(), 'event', 'orders_placed', 'order_ids', CAST(:order_ids AS JSONB), "
    "'basket_legs', CAST(:basket_legs AS JSONB))) "
    "FROM public.strategies s WHERE g.id = :id AND s.id = g.strategy_id AND s.user_ref = :user_ref "
    "AND g.strategy_id = :strategy_id AND g.outcome = 'acted_on' "
    "AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements(g.timeline) e WHERE e ->> 'event' = 'orders_placed') "
    "RETURNING g.id")
_SUGGESTION_OF_STRATEGY = text(
    "SELECT g.outcome FROM public.adjustment_suggestions g JOIN public.strategies s ON s.id = g.strategy_id "
    "WHERE g.id = :id AND g.strategy_id = :strategy_id AND s.user_ref = :user_ref")
_INBOX = text(f"SELECT {', '.join('g.' + c for c in _SG_COLUMNS.split(', '))}, s.name, "  # noqa: S608 constant
              "EXISTS (SELECT 1 FROM public.paper_orders o WHERE o.strategy_id = s.id) "
              "FROM public.adjustment_suggestions g JOIN public.strategies s ON s.id = g.strategy_id "
              "WHERE s.user_ref = :user_ref ORDER BY g.shown_at DESC, g.id DESC")
_LIST_SUGGESTIONS = text(f"SELECT {', '.join('g.' + c for c in _SG_COLUMNS.split(', '))} "  # noqa: S608 constant
                         "FROM public.adjustment_suggestions g JOIN public.strategies s ON s.id = g.strategy_id "
                         "WHERE g.strategy_id = :strategy_id AND s.user_ref = :user_ref ORDER BY g.id")


# ---------------------------------------------------------------------------------------------------------------
# Body check (docs/design/playbook-body-v1.md): fails closed naming the first bad field
# ---------------------------------------------------------------------------------------------------------------


def _bad(field: str) -> PlaybookStoreError:
    return PlaybookStoreError(BODY_INVALID, f"playbook body field {field}", field=field)


def _stage_counts(stages: object) -> dict[str, int]:
    if not isinstance(stages, dict) or set(stages) != {"weekly", "monthly"}:
        raise _bad("stages")
    counts = {}
    for kind, rows in stages.items():
        if not isinstance(rows, list) or not rows:
            raise _bad(f"stages.{kind}")
        for i, row in enumerate(rows):
            if (not isinstance(row, dict) or not isinstance(row.get("name"), str) or not row["name"].strip()
                    or type(row.get("from")) is not int or not (row.get("to") is None or type(row["to"]) is int)):
                raise _bad(f"stages.{kind}.{i}")
        counts[kind] = len(rows)
    return counts


def check_body(body: object, strategy_type: str) -> dict:
    """The v1 shape: schema 1, the row's type, stages, triggers with one decimal string (or "") per stage, rules
    naming known triggers; day_rules / situations / guards / approaches, where present, JSON containers."""
    if not isinstance(body, dict):
        raise _bad("body")
    if body.get("schema") != BODY_SCHEMA or type(body.get("schema")) is not int:
        raise _bad("schema")
    if body.get("strategy_type") != strategy_type:
        raise _bad("strategy_type")
    triggers = _check_triggers(body.get("triggers"), _stage_counts(body.get("stages")))
    _check_rules(body.get("rules"), triggers)
    for key, kind in (("day_rules", (list, dict)), ("situations", (list, dict)), ("guards", dict),
                      ("approaches", dict)):
        if key in body and not isinstance(body[key], kind):
            raise _bad(key)
    _check_day_rule_times(body.get("day_rules"))
    from ofo_app.settings_in_force import check_stop_values  # noqa: PLC0415 - it imports this module's callers
    if (bad := check_stop_values(body)) is not None:  # a stop value out of range is refused on save (ADR-252)
        raise _bad(bad)
    if layers.PLAN_SETTINGS in body:  # ADR-245: the strategy layer's values, each a registry-accepted decimal string
        try:
            layers.check_plan_settings(body[layers.PLAN_SETTINGS])
        except ValueError:
            raise _bad(layers.PLAN_SETTINGS) from None
    try:  # second layer: the evaluator's own validator (step 1B) must accept what is stored
        validate_body(body)
    except ValueError:
        raise _bad("body") from None
    return body


def _check_day_rule_times(day_rules: object) -> None:
    """A day rule's ``at``, when present, is HH:MM (REQ-159 AC-4): "2:30 pm" is refused here, since its rule id
    would be outside the Identifier pattern. An absent ``at`` is the evaluator's "incomplete rule", not refused."""
    for i, rule in enumerate(day_rules if isinstance(day_rules, list) else []):
        at = rule.get("at") if isinstance(rule, dict) else None
        if isinstance(rule, dict) and "at" in rule and not (isinstance(at, str) and _CLOCK.fullmatch(at)):
            raise _bad(f"day_rules.{i}.at")


def _check_triggers(triggers: object, counts: dict[str, int]) -> dict:
    if not isinstance(triggers, dict):
        raise _bad("triggers")
    for tid, trig in triggers.items():
        if not isinstance(tid, str) or not _ID.fullmatch(tid) or not isinstance(trig, dict):
            raise _bad("triggers")
        if type(trig.get("on")) is not bool:
            raise _bad(f"triggers.{tid}.on")
        for kind, count in counts.items():
            values = trig.get(kind)
            if values is None and kind in trig:  # no values for this expiry kind (1B: adjust_trigger_no_expiry_values)
                continue
            if not isinstance(values, list) or len(values) != count:
                raise _bad(f"triggers.{tid}.{kind}")
            shape = _CLOCK if trig.get("unit") == "time" else _DECIMAL  # a clock trigger holds HH:MM (T-10b)
            for i, v in enumerate(values):
                if not isinstance(v, str) or (v != "" and not shape.fullmatch(v)):
                    raise _bad(f"triggers.{tid}.{kind}.{i}")
    return triggers


def _check_rules(rules: object, triggers: dict) -> None:
    if not isinstance(rules, list):
        raise _bad("rules")
    for i, rule in enumerate(rules):
        members = rule.get("any_of", rule.get("all_of")) if isinstance(rule, dict) else None
        if (not isinstance(rule, dict) or not isinstance(rule.get("id"), str) or not _ID.fullmatch(rule["id"])
                or ("any_of" in rule) == ("all_of" in rule) or not isinstance(members, list) or not members
                or any(m not in triggers for m in members)):
            raise _bad(f"rules.{i}")


def _dump(body: dict) -> str:
    return json.dumps(body, sort_keys=True, ensure_ascii=False)


def _no_float(value: str) -> None:
    raise ValueError(f"a stored playbook body holds a float ({value})")


def _load(raw: str) -> Any:
    return json.loads(raw, parse_float=_no_float)


#: Public names for the body codec, shared with the system playbook version store (GC-SET step 9): one codec for
#: every stored playbook body (sorted keys; a float in a stored body is refused).
dump_body = _dump
load_body = _load


def _type(strategy_type: str) -> str:
    if strategy_type not in SHOWN_NAMES:
        raise PlaybookStoreError(BODY_INVALID, f"strategy type {strategy_type!r}", field="strategy_type")
    return strategy_type


def _name(name: object) -> str:
    """Trimmed, every inner whitespace run (tab, newline, no-break space, ...) folded to one space - the shape the
    database CHECK adjustment_playbooks_name_shape holds, so 'IC  Safe' and 'IC Safe' are one name."""
    folded = " ".join(name.split()) if isinstance(name, str) else ""
    if not folded or len(folded) > NAME_MAX:
        raise PlaybookStoreError(BODY_INVALID, "playbook name", field="name")
    return folded


def _playbook(row: Any) -> Playbook:
    return Playbook(id=row[0], user_ref=row[1], strategy_type=row[2], name=row[3], is_system=row[4], status=row[5],
                    body=_load(row[6]), version=row[7], created_at=row[8], updated_at=row[9])


async def _current(conn: Any, pb: Playbook) -> Playbook:
    """A system playbook as its current version (REQ-169); a user's own playbook unchanged. A system playbook with
    no stored version is a broken database (0034 seeds all 12): fails closed, never the 0031 row's body."""
    if not pb.is_system:
        return pb
    row = (await conn.execute(_SYSTEM_CURRENT, {"type": pb.strategy_type})).one_or_none()
    if row is None:
        raise RuntimeError(f"no stored version of the system playbook for {pb.strategy_type}")
    return dataclasses.replace(pb, version=row[0], status=row[1], body=_load(row[2]), updated_at=row[3])


def _not_found(playbook_id: object) -> PlaybookStoreError:
    return PlaybookStoreError(NOT_FOUND, f"playbook {playbook_id}")


def _taken(name: str, strategy_type: str) -> PlaybookStoreError:
    return PlaybookStoreError(NAME_TAKEN, f"name {name!r} in {strategy_type}", name=name,
                              type=SHOWN_NAMES[strategy_type])


# ---------------------------------------------------------------------------------------------------------------
# Playbooks
# ---------------------------------------------------------------------------------------------------------------


async def get(conn: Any, user_ref: str, playbook_id: int) -> Playbook:
    if type(playbook_id) is not int:
        raise _not_found(playbook_id)
    row = (await conn.execute(_SELECT_ONE, {"id": playbook_id, "user_ref": user_ref})).one_or_none()
    if row is None:
        raise _not_found(playbook_id)
    return await _current(conn, _playbook(row))


async def list_for_type(conn: Any, user_ref: str, strategy_type: str) -> list[Playbook]:
    """The type's system playbook first, then the user's own by name."""
    rows = (await conn.execute(_SELECT_TYPE, {"type": _type(strategy_type), "user_ref": user_ref})).all()
    return [await _current(conn, _playbook(r)) for r in rows]


async def _write_named(conn: Any, statement: Any, params: dict, name: str, strategy_type: str) -> Any:
    """Runs an INSERT / rename under a savepoint; a name clash (checked first, and the unique index for a race)
    answers playbook_name_taken."""
    used = await conn.execute(_NAME_USED, {"user_ref": params["user_ref"], "type": strategy_type, "name": name,
                                           "id": params.get("id")})
    if used.first() is not None:
        raise _taken(name, strategy_type)
    try:
        async with conn.begin_nested():
            return (await conn.execute(statement, params)).one_or_none()
    except IntegrityError as exc:
        if NAME_INDEX in str(exc.orig):
            raise _taken(name, strategy_type) from None
        raise


async def create(conn: Any, user_ref: str, strategy_type: str, name: str, body: object) -> Playbook:
    strategy_type, name = _type(strategy_type), _name(name)
    body = check_body(body, strategy_type)
    row = await _write_named(conn, _INSERT, {"user_ref": user_ref, "type": strategy_type, "name": name,
                                             "body": _dump(body)}, name, strategy_type)
    return _playbook(row)


async def duplicate(conn: Any, user_ref: str, playbook_id: int, new_name: str) -> Playbook:
    """Save as new (REQ-158 AC-6): a copy of a system or own playbook under a new name, owned by the user."""
    source = await get(conn, user_ref, playbook_id)
    return await create(conn, user_ref, source.strategy_type, new_name, source.body)


async def rename(conn: Any, user_ref: str, playbook_id: int, name: str) -> Playbook:
    current = await get(conn, user_ref, playbook_id)
    if current.is_system:
        raise PlaybookStoreError(SYSTEM_SAVE_IN_PLACE, f"playbook {playbook_id} is a system playbook")
    name = _name(name)
    row = await _write_named(conn, _RENAME, {"user_ref": user_ref, "id": playbook_id, "name": name}, name,
                             current.strategy_type)
    if row is None:
        raise _not_found(playbook_id)
    return _playbook(row)


async def save_in_place(conn: Any, user_ref: str, playbook_id: int, body: object, version: int) -> Playbook:
    """Save changes (REQ-158 AC-6): the user's own playbook only, at the version the caller read."""
    current = await get(conn, user_ref, playbook_id)
    if current.is_system:
        raise PlaybookStoreError(SYSTEM_SAVE_IN_PLACE, f"playbook {playbook_id} is a system playbook")
    body = check_body(body, current.strategy_type)
    row = (await conn.execute(_SAVE, {"id": playbook_id, "user_ref": user_ref, "version": version,
                                      "body": _dump(body)})).one_or_none()
    if row is None:
        raise PlaybookStoreError(VERSION_CONFLICT, f"playbook {playbook_id} is not at version {version}")
    return _playbook(row)


async def delete(conn: Any, user_ref: str, playbook_id: int) -> DeleteAnswer:
    current = await get(conn, user_ref, playbook_id)
    if current.is_system:
        raise PlaybookStoreError(SYSTEM_SAVE_IN_PLACE, f"playbook {playbook_id} is a system playbook")
    was_active = (await conn.execute(_IS_ACTIVE, {"user_ref": user_ref, "id": playbook_id})).first() is not None
    if (await conn.execute(_DELETE, {"id": playbook_id, "user_ref": user_ref})).first() is None:
        raise _not_found(playbook_id)
    message = (str(render_explanation("playbook_system_active_again", type=SHOWN_NAMES[current.strategy_type]))
               if was_active else None)
    return DeleteAnswer(deleted=playbook_id, active_now_system=was_active, message=message)


async def make_active(conn: Any, user_ref: str, playbook_id: int) -> Playbook:
    chosen = await get(conn, user_ref, playbook_id)
    await conn.execute(_MAKE_ACTIVE, {"user_ref": user_ref, "type": chosen.strategy_type, "id": chosen.id})
    return chosen


async def active_for(conn: Any, user_ref: str, strategy_type: str) -> Playbook:
    """The user's active playbook of the type; with no active row, the type's system playbook."""
    strategy_type = _type(strategy_type)
    row = (await conn.execute(_SELECT_ACTIVE, {"user_ref": user_ref, "type": strategy_type})).one_or_none()
    if row is None:
        row = (await conn.execute(_SELECT_SYSTEM, {"type": strategy_type})).one_or_none()
    if row is None:  # the migration seeds all 12: a missing one is a broken database, never a silent default
        raise RuntimeError(f"no system playbook for {strategy_type}")
    return await _current(conn, _playbook(row))


# ---------------------------------------------------------------------------------------------------------------
# A strategy's plan (a copy), rule memory (F-71), suggestions (REQ-112)
# ---------------------------------------------------------------------------------------------------------------


def _plan(row: Any) -> Plan:
    return Plan(strategy_id=row[0], playbook_id=row[1], strategy_type=row[2], body=_load(row[3]), accepted_at=row[4])


async def accept_plan(conn: Any, user_ref: str, strategy_id: int, playbook_id: int,
                      body: object | None = None) -> Plan:
    """REQ-161 AC-2/AC-3: the plan is a copy of the chosen playbook's body (or the customised sheet's body, same
    type); accepting again replaces the strategy's own plan."""
    await strategy_store.lock_strategy(conn, user_ref, strategy_id)  # not_found for a missing / another user's
    source = await get(conn, user_ref, playbook_id)
    current = await plan_for(conn, user_ref, strategy_id)
    if current is not None and current.strategy_type != source.strategy_type:  # a plan keeps its type (guard OF031)
        raise PlaybookStoreError(BODY_INVALID, f"plan of strategy {strategy_id} is {current.strategy_type}, "
                                 f"playbook {source.id} is {source.strategy_type}", field="strategy_type")
    copy = check_body(source.body if body is None else body, source.strategy_type)
    row = (await conn.execute(_UPSERT_PLAN, {"strategy_id": strategy_id, "playbook_id": source.id,
                                             "type": source.strategy_type, "body": _dump(copy)})).one()
    return _plan(row)


#: ADR-250: when migration 0040 saved the iron condor ADR-247 version (margin stop and T-16 off). The row is found by
#: the reason 0040 writes (as 0040's own downgrade finds it), NEVER by a version number: an admin save or restore also
#: writes newest + 1, so "version 2" can be someone else's row
#: (finding cutoff-by-version-number-not-by-the-row-written).
#: The text equals ``0040_ic_default_stop_adr247.REASON`` (a test asserts it). No such row -> None -> every plan
#: predates ADR-247 (fail closed: it keeps its own stops).
ADR247_REASON = "ADR-247: default stop 50 % of max loss or 2x credit; % of margin stop and T-16 off by default"
_ADR247_SAVED_AT = text("SELECT min(saved_at) FROM public.system_playbook_versions WHERE strategy_type = 'ic' "
                        "AND reason = :reason")


async def adr247_saved_at(conn: Any) -> datetime | None:
    return (await conn.execute(_ADR247_SAVED_AT, {"reason": ADR247_REASON})).scalar_one_or_none()


async def plan_for(conn: Any, user_ref: str, strategy_id: int) -> Plan | None:
    row = (await conn.execute(_SELECT_PLAN, {"strategy_id": strategy_id, "user_ref": user_ref})).one_or_none()
    return None if row is None else _plan(row)


async def _owned(conn: Any, user_ref: str, strategy_id: int) -> None:
    if (await conn.execute(_OWNS_STRATEGY, {"strategy_id": strategy_id, "user_ref": user_ref})).first() is None:
        raise strategy_store.StrategyStoreError(strategy_store.NOT_FOUND, f"strategy {strategy_id}")


async def rule_state(conn: Any, user_ref: str, strategy_id: int) -> dict[str, tuple[bool, bool]]:
    """rule id -> (held_at_entry, seen_clear)."""
    await _owned(conn, user_ref, strategy_id)
    rows = (await conn.execute(_SELECT_STATE, {"strategy_id": strategy_id})).all()
    return {r[0]: (r[1], r[2]) for r in rows}


async def put_rule_state(conn: Any, user_ref: str, strategy_id: int, rule_id: str, *, held_at_entry: bool,  # noqa: PLR0913
                         seen_clear: bool) -> None:
    """First call records held_at_entry; later calls only ever turn seen_clear on (F-71)."""
    await _owned(conn, user_ref, strategy_id)
    await conn.execute(_PUT_STATE, {"strategy_id": strategy_id, "rule_id": rule_id, "held": held_at_entry,
                                    "seen": seen_clear})


def _suggestion(row: Any) -> Suggestion:
    return Suggestion(id=row[0], strategy_id=row[1], rule_id=row[2], trigger_id=row[3], stage=row[4], value=row[5],
                      threshold=row[6], shown_at=row[7], outcome=row[8], dismiss_reason=row[9],
                      timeline=json.loads(row[10]))


async def open_suggestion(conn: Any, user_ref: str, strategy_id: int, rule_id: str, *,  # noqa: PLR0913
                          trigger_id: str | None, stage: str | None, value: Decimal | None,
                          threshold: Decimal | None, group: str | None = None,
                          source: str | None = None, cmp: str | None = None, label: str | None = None,
                          unit: str | None = None, approach: str | None = None,
                          approach_cost: Decimal | None = None, unpriced: int | None = None,
                          worse: str | None = None, carry: Mapping[str, str | None] | None = None) -> Suggestion:
    """REQ-112 AC-1: one open record per (strategy, rule); a rule still open returns its existing record.
    ``carry``: a carry check's content (GC-IC1 1b; money as strings, None = not known with its reason code).
    ``worse``: None / 'last' / 'dismissed' (REQ-170 AC-3, ADR-237 (5)), written once at insert."""
    if worse not in WORSE_MARKS:
        raise ValueError(f"unknown worse marker {worse!r}")
    await _owned(conn, user_ref, strategy_id)
    params = {"strategy_id": strategy_id, "rule_id": rule_id}
    existing = (await conn.execute(_OPEN_FOR_RULE, params)).one_or_none()
    if existing is not None:
        return _suggestion(existing)
    row = (await conn.execute(_INSERT_SUGGESTION, {**params, "trigger_id": trigger_id, "stage": stage,
                                                   "value": value, "threshold": threshold, "group": group,
                                                   "source": source, "cmp": cmp, "label": label,
                                                   "unit": unit, "approach": approach, "unpriced": unpriced,
                                                   "worse": worse,
                                                   "carry": None if carry is None else json.dumps(carry),
                                                   "approach_cost": None if approach_cost is None
                                                   else format(approach_cost, "f")})).one()
    return _suggestion(row)


async def _close(conn: Any, user_ref: str, suggestion_id: int, outcome: str, reason: str | None,  # noqa: PLR0913
                 note: str | None = None) -> Suggestion:
    if outcome not in SUGGESTION_FINAL:
        raise ValueError(f"unknown suggestion outcome {outcome!r}")
    if type(suggestion_id) is not int:
        raise strategy_store.StrategyStoreError(SUGGESTION_NOT_FOUND, f"suggestion {suggestion_id}")
    row = (await conn.execute(_CLOSE_SUGGESTION, {"id": suggestion_id, "user_ref": user_ref, "outcome": outcome,
                                                  "reason": reason, "note": note})).one_or_none()
    if row is None:  # the outcome is never written twice: missing / another user's, or already final
        found = (await conn.execute(_SUGGESTION_OUTCOME, {"id": suggestion_id, "user_ref": user_ref})).first()
        if found is None:
            raise strategy_store.StrategyStoreError(SUGGESTION_NOT_FOUND, f"suggestion {suggestion_id}")
        raise strategy_store.StrategyStoreError(SUGGESTION_NOT_OPEN, f"suggestion {suggestion_id} is {found[0]}")
    return _suggestion(row)


async def dismiss(conn: Any, user_ref: str, suggestion_id: int, reason: str | None = None) -> Suggestion:
    return await _close(conn, user_ref, suggestion_id, "dismissed", reason)


async def act_on(conn: Any, user_ref: str, suggestion_id: int) -> Suggestion:
    return await _close(conn, user_ref, suggestion_id, "acted_on", None)


async def link_orders(conn: Any, user_ref: str, strategy_id: int, suggestion_id: int,  # noqa: PLR0913
                      order_ids: list[int], basket_legs: int | None = None) -> None:
    """REQ-163 AC-1: the acted-on record ``suggestion_id`` names the paper orders ``order_ids`` its basket placed.

    Fail closed, nothing written: a missing record, another user's, or one of another strategy -> SUGGESTION_NOT_FOUND;
    a record not acted on, or one that already names a basket -> SUGGESTION_NOT_OPEN. The caller rolls back the orders.
    """
    if type(suggestion_id) is not int or not order_ids or any(type(i) is not int for i in order_ids):
        raise strategy_store.StrategyStoreError(SUGGESTION_NOT_FOUND, f"suggestion {suggestion_id!r}")
    args = {"id": suggestion_id, "user_ref": user_ref, "strategy_id": strategy_id}
    row = (await conn.execute(_LINK_ORDERS, {**args, "order_ids": json.dumps(order_ids),
                                                 "basket_legs": json.dumps(basket_legs)})).one_or_none()
    if row is not None:
        return
    found = (await conn.execute(_SUGGESTION_OF_STRATEGY, args)).first()
    if found is None:
        raise strategy_store.StrategyStoreError(SUGGESTION_NOT_FOUND, f"suggestion {suggestion_id}")
    raise strategy_store.StrategyStoreError(SUGGESTION_NOT_OPEN,
                                            f"suggestion {suggestion_id} is {found[0]} or already names a basket")


async def placed_links(conn: Any, user_ref: str, strategy_id: int) -> dict[int, list[Suggestion]]:
    """REQ-163 AC-1: paper order id -> EVERY record whose basket placed it (one basket may answer several records;
    ``link_orders`` writes the whole order list into each), oldest record first, for one strategy of the user."""
    out: dict[int, list[Suggestion]] = {}
    for s in sorted(await suggestions(conn, user_ref, strategy_id), key=lambda s: s.id):
        for oid in dict.fromkeys(s.placed_order_ids or ()):
            out.setdefault(oid, []).append(s)
    return out


async def lapse(conn: Any, user_ref: str, suggestion_id: int, reason: str = LAPSE_CONDITION_STOPPED) -> Suggestion:
    if reason not in LAPSE_REASONS:
        raise ValueError(f"unknown lapse reason {reason!r}")
    return await _close(conn, user_ref, suggestion_id, "lapsed", None, reason)


async def open_suggestions(conn: Any, user_ref: str, strategy_id: int) -> list[Suggestion]:
    rows = (await conn.execute(_OPEN_OF_STRATEGY, {"strategy_id": strategy_id, "user_ref": user_ref})).all()
    return [_suggestion(r) for r in rows]


async def lapse_all(conn: Any, user_ref: str, strategy_id: int, reason: str) -> list[Suggestion]:
    """Every open record of the strategy lapses (REQ-112 AC-2: the strategy closed)."""
    return [await lapse(conn, user_ref, s.id, reason) for s in await open_suggestions(conn, user_ref, strategy_id)]


async def inbox(conn: Any, user_ref: str) -> list[InboxRow]:
    """REQ-162 AC-1: every record of the user's strategies, newest first."""
    rows = (await conn.execute(_INBOX, {"user_ref": user_ref})).all()
    return [InboxRow(_suggestion(r), r[11], r[12] is True) for r in rows]


async def suggestions(conn: Any, user_ref: str, strategy_id: int) -> list[Suggestion]:
    rows = (await conn.execute(_LIST_SUGGESTIONS, {"strategy_id": strategy_id, "user_ref": user_ref})).all()
    return [_suggestion(r) for r in rows]


async def dismissed_holding(conn: Any, user_ref: str, strategy_id: int) -> dict[str, Suggestion]:
    """ADR-217: rule id -> its dismissed record, for each rule whose latest record is dismissed and which no check has
    found false since (so a flag for it opens no new record)."""
    rows = (await conn.execute(_LATEST_DISMISSED, {"strategy_id": strategy_id, "user_ref": user_ref})).all()
    return {r[2]: _suggestion(r) for r in rows}


async def mark_cleared(conn: Any, user_ref: str, suggestion_id: int) -> None:
    """ADR-217: a check found the dismissed record's rule false; the next flag may open a new record."""
    await conn.execute(_MARK_CLEARED, {"id": suggestion_id, "user_ref": user_ref})


# ---- alert gate storage (migration 0036; ADR-237 (5); REQ-170 AC-4) ----------------------------------------------
_INSERT_HELD = text(
    "INSERT INTO public.adjustment_held_crossings (strategy_id, rule_id, trigger_id, stage, value, threshold, reason) "
    "VALUES (:strategy_id, :rule_id, :trigger_id, :stage, :value, :threshold, :reason) "
    "RETURNING id, strategy_id, rule_id, trigger_id, stage, value, threshold, reason, held_at")
#: the last record per rule (by id) and the count of records shown on `today` in IST (the cap counts every record)
_GATE_LAST = text(
    "SELECT DISTINCT ON (g.rule_id) g.rule_id, g.shown_at, g.threshold, g.outcome, g.id "
    "FROM public.adjustment_suggestions g JOIN public.strategies s ON s.id = g.strategy_id "
    "WHERE g.strategy_id = :strategy_id AND s.user_ref = :user_ref ORDER BY g.rule_id, g.id DESC")
_GATE_TODAY = text(
    "SELECT count(*) FROM public.adjustment_suggestions g JOIN public.strategies s ON s.id = g.strategy_id "  # noqa: S608 constant zone fragment
    "WHERE g.strategy_id = :strategy_id AND s.user_ref = :user_ref "
    f"AND (g.shown_at {IST_SQL_ZONE})::date = :today")


@dataclass(frozen=True)
class HeldCrossing:
    id: int
    strategy_id: int
    rule_id: str
    trigger_id: str | None
    stage: str | None
    value: Decimal | None
    threshold: Decimal | None
    reason: str
    held_at: datetime


async def record_held(conn: Any, user_ref: str, strategy_id: int, rule_id: str, *,  # noqa: PLR0913
                      trigger_id: str | None, stage: str | None, value: Decimal | None,
                      threshold: Decimal | None, reason: str) -> HeldCrossing:
    """REQ-170 AC-4: a capped or quiet-time crossing is a stored row ("held: daily limit / quiet time"), never
    dropped. A yes/no rule's value and threshold are None. held_at is the database clock (the guard sets it)."""
    if reason not in HELD_REASONS:
        raise ValueError(f"unknown held reason {reason!r}")
    if isinstance(value, bool):
        raise ValueError("a yes/no rule's held value is stored as None, not a bool")
    await _owned(conn, user_ref, strategy_id)
    row = (await conn.execute(_INSERT_HELD, {"strategy_id": strategy_id, "rule_id": rule_id, "trigger_id": trigger_id,
                                             "stage": stage, "value": value, "threshold": threshold,
                                             "reason": reason})).one()
    return HeldCrossing(*row)


async def gate_rows(conn: Any, user_ref: str, strategy_id: int, today: date) -> GateRows:
    """ADR-237 (5): what ``alert_gate.restore`` needs - the last record per rule (time, threshold, dismissed, still
    open) and today's (IST) record count. No record -> empty, 0. Another user's or a missing strategy -> not found;
    a store error raises (never an empty default)."""
    await _owned(conn, user_ref, strategy_id)
    params = {"strategy_id": strategy_id, "user_ref": user_ref}
    last = (await conn.execute(_GATE_LAST, params)).all()
    count = (await conn.execute(_GATE_TODAY, {**params, "today": today})).scalar_one()
    rows = tuple(GateRow(r[0], r[1], r[2], dismissed=r[3] == "dismissed", open=r[3] == "open", id=r[4])
                 for r in last)
    return GateRows(rows, int(count))


_HELD_TODAY = text(
    "SELECT h.rule_id, h.reason, h.threshold, h.held_at FROM public.adjustment_held_crossings h "  # noqa: S608 constant zone fragment
    "JOIN public.strategies s ON s.id = h.strategy_id WHERE h.strategy_id = :strategy_id AND s.user_ref = :user_ref "
    f"AND (h.held_at {IST_SQL_ZONE})::date = :today ORDER BY h.id")


@dataclass(frozen=True)
class HeldToday:
    rule_id: str
    reason: str
    threshold: Decimal | None
    held_at: datetime


_HELD_INBOX = text(
    "SELECT h.id, h.strategy_id, h.rule_id, h.trigger_id, h.reason, h.held_at, s.name "
    "FROM public.adjustment_held_crossings h JOIN public.strategies s ON s.id = h.strategy_id "
    "WHERE s.user_ref = :user_ref ORDER BY h.held_at DESC, h.id DESC")


@dataclass(frozen=True)
class HeldInboxRow:
    id: int
    strategy_id: int
    rule_id: str
    trigger_id: str | None
    reason: str
    held_at: datetime
    strategy_name: str


async def held_inbox(conn: Any, user_ref: str) -> list[HeldInboxRow]:
    """REQ-170 AC-4: every crossing the gate held on the user's strategies, newest first (the timeline's reader)."""
    rows = (await conn.execute(_HELD_INBOX, {"user_ref": user_ref})).all()
    return [HeldInboxRow(*r) for r in rows]


async def held_today(conn: Any, user_ref: str, strategy_id: int, today: date) -> tuple[HeldToday, ...]:
    """GC-ALERT1 wire-b item 5: the crossings held on ``today`` (IST), oldest first, so a restarted worker restores
    the held episode instead of writing a second Held row. Read only; a store error raises."""
    await _owned(conn, user_ref, strategy_id)
    rows = (await conn.execute(_HELD_TODAY, {"strategy_id": strategy_id, "user_ref": user_ref, "today": today})).all()
    return tuple(HeldToday(r[0], r[1], r[2], r[3]) for r in rows)
