"""PostgreSQL store of adjustment playbooks, the active choice, a strategy's plan, the F-71 rule memory and the
suggestion record (GC-ADJ2 step 1A; REQ-158, REQ-161 AC-1..AC-3, REQ-112 AC-1/AC-2/AC-4). Schema: migration 0031.
Body shape: docs/design/playbook-body-v1.md.

- The user always comes from the caller (the signed-in session), never from a body. Another user's playbook or
  strategy answers `playbook_not_found` / `not_found` exactly like a missing one.
- A system playbook is read-only: save_in_place refuses it (`system_playbook_save_in_place`), and the database guard
  refuses any UPDATE or DELETE of it by the application role (SQLSTATE OF031) whatever this module does.
- Names are unique per user and type, case-insensitive (`playbook_name_taken`, carrying the name and the type's shown
  name). Every body is checked before any write (`playbook_body_invalid`, naming the field).
- active_for: the user's active row, else the type's system playbook (no row = system). Deleting the active playbook
  removes its active row (FK cascade) and the answer says the system playbook is active again (REQ-158 AC-4).
- accept_plan COPIES the body into the strategy's plan; a later edit or delete of the playbook never changes it
  (REQ-158 AC-5); a deleted playbook leaves the plan's playbook_id NULL.
The caller commits.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from ofo.adjustment.playbook_types import BODY_SCHEMA, NAME_MAX, SHOWN_NAMES
from ofo.errors.explanations import render_explanation
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from ofo_app import strategy_store

NAME_TAKEN = "playbook_name_taken"
SYSTEM_SAVE_IN_PLACE = "system_playbook_save_in_place"
VERSION_CONFLICT = "playbook_version_conflict"
NOT_FOUND = "playbook_not_found"
BODY_INVALID = "playbook_body_invalid"
NAME_INDEX = "adjustment_playbooks_name"
SUGGESTION_FINAL = ("dismissed", "acted_on", "lapsed")
_DECIMAL = re.compile(r"-?[0-9]+(\.[0-9]+)?")
_ID = re.compile(r"[A-Za-z0-9_.\-]{1,40}")


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
_NAME_USED = text("SELECT 1 FROM public.adjustment_playbooks WHERE user_ref = :user_ref AND strategy_type = :type "
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
    "INSERT INTO public.adjustment_suggestions (strategy_id, rule_id, trigger_id, stage, value, threshold, timeline) "  # noqa: S608
    "VALUES (:strategy_id, :rule_id, :trigger_id, :stage, :value, :threshold, "
    "jsonb_build_array(jsonb_build_object('at', clock_timestamp(), 'outcome', 'open'))) "
    f"RETURNING {_SG_COLUMNS}")
_CLOSE_SUGGESTION = text(
    "UPDATE public.adjustment_suggestions AS g SET outcome = CAST(:outcome AS TEXT), "  # noqa: S608
    "dismiss_reason = CAST(:reason AS TEXT), timeline = g.timeline || jsonb_build_array(jsonb_build_object("
    "'at', clock_timestamp(), 'outcome', CAST(:outcome AS TEXT), 'suggestion_id', g.id)) "
    "FROM public.strategies s WHERE g.id = :id AND s.id = g.strategy_id "
    "AND s.user_ref = :user_ref AND g.outcome = 'open' "
    f"RETURNING {', '.join('g.' + c for c in _SG_COLUMNS.split(', '))}")
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
    return body


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
            if not isinstance(values, list) or len(values) != count:
                raise _bad(f"triggers.{tid}.{kind}")
            for i, v in enumerate(values):
                if not isinstance(v, str) or (v != "" and not _DECIMAL.fullmatch(v)):
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


def _type(strategy_type: str) -> str:
    if strategy_type not in SHOWN_NAMES:
        raise PlaybookStoreError(BODY_INVALID, f"strategy type {strategy_type!r}", field="strategy_type")
    return strategy_type


def _name(name: object) -> str:
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > NAME_MAX:
        raise PlaybookStoreError(BODY_INVALID, "playbook name", field="name")
    return name.strip()


def _playbook(row: Any) -> Playbook:
    return Playbook(id=row[0], user_ref=row[1], strategy_type=row[2], name=row[3], is_system=row[4], status=row[5],
                    body=_load(row[6]), version=row[7], created_at=row[8], updated_at=row[9])


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
    return _playbook(row)


async def list_for_type(conn: Any, user_ref: str, strategy_type: str) -> list[Playbook]:
    """The type's system playbook first, then the user's own by name."""
    rows = (await conn.execute(_SELECT_TYPE, {"type": _type(strategy_type), "user_ref": user_ref})).all()
    return [_playbook(r) for r in rows]


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
    return _playbook(row)


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
    copy = check_body(source.body if body is None else body, source.strategy_type)
    row = (await conn.execute(_UPSERT_PLAN, {"strategy_id": strategy_id, "playbook_id": source.id,
                                             "type": source.strategy_type, "body": _dump(copy)})).one()
    return _plan(row)


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
                          threshold: Decimal | None) -> Suggestion:
    """REQ-112 AC-1: one open record per (strategy, rule); a rule still open returns its existing record."""
    await _owned(conn, user_ref, strategy_id)
    params = {"strategy_id": strategy_id, "rule_id": rule_id}
    existing = (await conn.execute(_OPEN_FOR_RULE, params)).one_or_none()
    if existing is not None:
        return _suggestion(existing)
    row = (await conn.execute(_INSERT_SUGGESTION, {**params, "trigger_id": trigger_id, "stage": stage,
                                                   "value": value, "threshold": threshold})).one()
    return _suggestion(row)


async def _close(conn: Any, user_ref: str, suggestion_id: int, outcome: str, reason: str | None) -> Suggestion:
    if outcome not in SUGGESTION_FINAL:
        raise ValueError(f"unknown suggestion outcome {outcome!r}")
    row = (await conn.execute(_CLOSE_SUGGESTION, {"id": suggestion_id, "user_ref": user_ref, "outcome": outcome,
                                                  "reason": reason})).one_or_none()
    if row is None:  # missing, another user's, or no longer open: the outcome is never written twice
        raise strategy_store.StrategyStoreError(strategy_store.NOT_FOUND, f"open suggestion {suggestion_id}")
    return _suggestion(row)


async def dismiss(conn: Any, user_ref: str, suggestion_id: int, reason: str | None = None) -> Suggestion:
    return await _close(conn, user_ref, suggestion_id, "dismissed", reason)


async def act_on(conn: Any, user_ref: str, suggestion_id: int) -> Suggestion:
    return await _close(conn, user_ref, suggestion_id, "acted_on", None)


async def lapse(conn: Any, user_ref: str, suggestion_id: int) -> Suggestion:
    return await _close(conn, user_ref, suggestion_id, "lapsed", None)


async def suggestions(conn: Any, user_ref: str, strategy_id: int) -> list[Suggestion]:
    rows = (await conn.execute(_LIST_SUGGESTIONS, {"strategy_id": strategy_id, "user_ref": user_ref})).all()
    return [_suggestion(r) for r in rows]
