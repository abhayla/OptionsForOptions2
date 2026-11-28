"""The plan-watch batch's set-based reads (Lane B3, 28 Nov 2026; I-48, PC round 2 W-02).

Why: on the owner's real database link every query costs one round trip (about 134 ms). The batch answered nine rows
with 136 statements: 18 s, whatever the statement text. The cost is the NUMBER OF ROUND TRIPS, and it grew with the
rows. Here the batch reads every table of the check path ONCE for all its rows, in one statement (``= ANY(:ids)``), and
for the length of the request the session answers the per-row statements from memory, so the count is fixed whatever
the number of rows (``tests_app/test_plan_watch_batch_b3_1128.py`` pins it: 3 rows and 9 rows run the same queries).

How it stays the same answer: the per-row code is NOT changed. ``install`` replaces ``execute`` of the request's own
session; the replacement recognises a statement by its exact text (``ORIGINAL`` below, a copy of each store's statement;
a test holds every copy equal to the store's own, and a store that rewords a statement just stops matching: the
statement then runs against the database as before, slower, never different), takes the row's id and user from its
parameters, and returns the rows the same statement would return for that id (same columns, same order, the real
values) through the converter the caller already uses. Another statement, an id or a user the batch did not read, any
write: straight to the database. The prefetch is as of the request start (the same for every row of one answer).
Everything prefetched is a SELECT; nothing is written.
"""
from __future__ import annotations

import collections
import contextlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import MultipleResultsFound, NoResultFound
from sqlalchemy.sql.elements import TextClause

SID = "_sid"  # the strategy id column every table of the combined query carries (never handed on to the caller)
_ANY = "= ANY(CAST(:ids AS BIGINT[]))"

#: the statements the check path repeats per row, as the stores write them (whitespace folded); a test compares each
#: with the store's own constant
ORIGINAL: dict[str, str] = {
    "marker": "SELECT scenario_id FROM public.strategies WHERE id = :id AND user_ref = :user_ref",
    "owns": "SELECT 1 FROM public.strategies WHERE id = :strategy_id AND user_ref = :user_ref AND deleted_at IS NULL",
    "pause": "SELECT paused_until FROM public.strategy_monitor_pause WHERE user_ref = :u AND strategy_id = :s "
             "ORDER BY effective_from DESC LIMIT 1",
    "facts": "SELECT entry_spot, call_distance, put_distance, entry_atm_iv, created_at "
             "FROM public.strategy_entry_facts WHERE strategy_id = :id",
    "baskets": "SELECT basket_no, clock, spot, atm_iv, legs FROM public.strategy_basket_facts WHERE strategy_id = :id",
    "rule_state": "SELECT adjustment_no, rule_id, held_at_entry, seen_clear FROM public.adjustment_rule_state "
                  "WHERE strategy_id = :strategy_id ORDER BY adjustment_no, rule_id",
    "plan": "SELECT p.strategy_id, p.playbook_id, p.strategy_type, p.body::text, p.accepted_at, p.stop_base::text "
            "FROM public.strategy_adjustment_plans p JOIN public.strategies s ON s.id = p.strategy_id "
            "WHERE p.strategy_id = :strategy_id AND s.user_ref = :user_ref AND s.deleted_at IS NULL",
    "open": "SELECT g.id, g.strategy_id, g.rule_id, g.trigger_id, g.stage, g.value, g.threshold, g.shown_at, "
            "g.outcome, g.dismiss_reason, g.timeline::text FROM public.adjustment_suggestions g "
            "JOIN public.strategies s ON s.id = g.strategy_id "
            "WHERE g.strategy_id = :strategy_id AND s.user_ref = :user_ref AND g.outcome = 'open' ORDER BY g.id",
    "dismissed": "SELECT g.id, g.strategy_id, g.rule_id, g.trigger_id, g.stage, g.value, g.threshold, g.shown_at, "
                 "g.outcome, g.dismiss_reason, g.timeline::text FROM public.adjustment_suggestions g "
                 "JOIN public.strategies s ON s.id = g.strategy_id "
                 "WHERE g.strategy_id = :strategy_id AND s.user_ref = :user_ref AND g.outcome = 'dismissed' "
                 "AND g.id = (SELECT max(m.id) FROM public.adjustment_suggestions m WHERE m.strategy_id = "
                 "g.strategy_id AND m.rule_id = g.rule_id) AND NOT EXISTS (SELECT 1 FROM "
                 "jsonb_array_elements(g.timeline) e WHERE e ->> 'event' = 'condition_cleared')",
    "triggers": "SELECT t.id, t.strategy_id, t.kind, t.direction, t.level, t.contract_id, t.underlying, t.created_at, "
                "t.fired_at, t.cancelled_at FROM public.paper_triggers AS t WHERE t.strategy_id = :sid ORDER BY t.id",
    "adr247": "SELECT min(saved_at) FROM public.system_playbook_versions "
              "WHERE strategy_type = 'ic' AND reason = :reason",
}


def norm(sql: object) -> str:
    """A statement's text, whitespace folded (a SQLAlchemy ``text()`` or a string)."""
    return " ".join((sql.text if isinstance(sql, TextClause) else str(sql)).split())


class Rows:
    """The part of a SQLAlchemy ``Result`` the check path uses, over rows already read."""

    def __init__(self, rows: Sequence[Any]) -> None:
        self._rows = list(rows)

    def all(self) -> list[Any]:
        return list(self._rows)

    fetchall = all

    def __iter__(self):
        return iter(self._rows)

    def first(self) -> Any:
        return self._rows[0] if self._rows else None

    def one_or_none(self) -> Any:
        if len(self._rows) > 1:
            raise MultipleResultsFound("Multiple rows were found when one or none was required")
        return self.first()

    def one(self) -> Any:
        if not self._rows:
            raise NoResultFound("No row was found when one was required")
        return self.one_or_none()

    def scalar(self) -> Any:
        return self._rows[0][0] if self._rows else None

    def scalar_one_or_none(self) -> Any:
        row = self.one_or_none()
        return None if row is None else row[0]


@dataclass(frozen=True)
class Table:
    """One table read for all ids: ``select`` is the caller's column list plus ``_sid`` (``cols`` names the columns in
    order), ``tail`` the FROM / WHERE, ``order`` the order of the rows inside the combined query."""

    select: str
    tail: str
    cols: tuple[str, ...]
    order: str


_SUGGESTION_SELECT = (f"g.strategy_id AS {SID}, g.id, g.strategy_id, g.rule_id, g.trigger_id, g.stage, g.value, "
                      "g.threshold, g.shown_at, g.outcome, g.dismiss_reason, g.timeline::text")
_SUGGESTION_COLS = (SID, "id", "strategy_id", "rule_id", "trigger_id", "stage", "value", "threshold", "shown_at",
                    "outcome", "dismiss_reason", "timeline")
_SUGGESTION_FROM = "FROM public.adjustment_suggestions g JOIN public.strategies s ON s.id = g.strategy_id "

# One sub-select per table; the column list equals the caller's statement, so its converter reads the rows unchanged.
_TABLES: dict[str, Table] = {
    "strategies": Table(f"scenario_id, (deleted_at IS NULL) AS live, id AS {SID}",
                        f"FROM public.strategies WHERE id {_ANY} AND user_ref = :user_ref",
                        ("scenario_id", "live", SID), SID),
    "pause": Table(f"paused_until, strategy_id AS {SID}, effective_from",
                   f"FROM public.strategy_monitor_pause WHERE user_ref = :user_ref AND strategy_id {_ANY}",
                   ("paused_until", SID, "effective_from"), f"{SID}, effective_from DESC"),
    "facts": Table(f"entry_spot, call_distance, put_distance, entry_atm_iv, created_at, strategy_id AS {SID}",
                   f"FROM public.strategy_entry_facts WHERE strategy_id {_ANY}",
                   ("entry_spot", "call_distance", "put_distance", "entry_atm_iv", "created_at", SID), SID),
    "baskets": Table(f"basket_no, clock, spot, atm_iv, legs, strategy_id AS {SID}",
                     f"FROM public.strategy_basket_facts WHERE strategy_id {_ANY}",
                     ("basket_no", "clock", "spot", "atm_iv", "legs", SID), SID),
    "rule_state": Table(f"adjustment_no, rule_id, held_at_entry, seen_clear, strategy_id AS {SID}",
                        f"FROM public.adjustment_rule_state WHERE strategy_id {_ANY}",
                        ("adjustment_no", "rule_id", "held_at_entry", "seen_clear", SID),
                        f"{SID}, adjustment_no, rule_id"),
    "plan": Table(f"p.strategy_id AS {SID}, p.strategy_id, p.playbook_id, p.strategy_type, p.body::text, "
                  "p.accepted_at, p.stop_base::text",
                  "FROM public.strategy_adjustment_plans p JOIN public.strategies s ON s.id = p.strategy_id "
                  f"WHERE p.strategy_id {_ANY} AND s.user_ref = :user_ref AND s.deleted_at IS NULL",
                  (SID, "strategy_id", "playbook_id", "strategy_type", "body", "accepted_at", "stop_base"), SID),
    "open": Table(_SUGGESTION_SELECT,
                  _SUGGESTION_FROM + f"WHERE g.strategy_id {_ANY} AND s.user_ref = :user_ref AND g.outcome = 'open'",
                  _SUGGESTION_COLS, f"{SID}, id"),
    "dismissed": Table(_SUGGESTION_SELECT,
                       _SUGGESTION_FROM + f"WHERE g.strategy_id {_ANY} AND s.user_ref = :user_ref "  # noqa: S608 constant SQL
                       "AND g.outcome = 'dismissed' AND g.id = (SELECT max(m.id) FROM public.adjustment_suggestions m "
                       "WHERE m.strategy_id = g.strategy_id AND m.rule_id = g.rule_id) AND NOT EXISTS (SELECT 1 FROM "
                       "jsonb_array_elements(g.timeline) e WHERE e ->> 'event' = 'condition_cleared')",
                       _SUGGESTION_COLS, f"{SID}, id"),
    "triggers": Table("t.id, t.strategy_id, t.kind, t.direction, t.level, t.contract_id, t.underlying, t.created_at, "
                      f"t.fired_at, t.cancelled_at, t.strategy_id AS {SID}",
                      f"FROM public.paper_triggers AS t WHERE t.strategy_id {_ANY}",
                      ("id", "strategy_id", "kind", "direction", "level", "contract_id", "underlying", "created_at",
                       "fired_at", "cancelled_at", SID), f"{SID}, id"),
}


def _first(rows: list[Any]) -> list[Any]:
    return rows[:1]  # a ``LIMIT 1`` the set-based query cannot carry per id


def _marker(rows: list[Any]) -> list[Any]:
    return [(r[0],) for r in rows]  # the ``scenario_id`` (a row exists for the user's strategy, deleted or not)


def _owned(rows: list[Any]) -> list[Any]:
    return [(1,) for r in rows if r[1]]  # ``SELECT 1 ... deleted_at IS NULL``


def _same(rows: list[Any]) -> list[Any]:
    return rows


@dataclass(frozen=True)
class Match:
    """A per-row statement that can be answered: which table, its id and user parameters, how it reads the table."""

    table: str
    id_param: str
    user_param: str | None
    view: Callable[[list[Any]], list[Any]] = _same


_MATCH: dict[str, Match] = {
    norm(ORIGINAL["marker"]): Match("strategies", "id", "user_ref", _marker),
    norm(ORIGINAL["owns"]): Match("strategies", "strategy_id", "user_ref", _owned),
    norm(ORIGINAL["pause"]): Match("pause", "s", "u", _first),
    norm(ORIGINAL["facts"]): Match("facts", "id", None),
    norm(ORIGINAL["baskets"]): Match("baskets", "id", None),
    norm(ORIGINAL["rule_state"]): Match("rule_state", "strategy_id", None),
    norm(ORIGINAL["plan"]): Match("plan", "strategy_id", "user_ref"),
    norm(ORIGINAL["open"]): Match("open", "strategy_id", "user_ref"),
    norm(ORIGINAL["dismissed"]): Match("dismissed", "strategy_id", "user_ref"),
    norm(ORIGINAL["triggers"]): Match("triggers", "sid", None),
}
#: statements with no id that every row repeats: the first row's read answers the rest (the ADR-247 cut-off time)
_ONCE = {norm(ORIGINAL["adr247"])}


def _combined_sql(tables: dict[str, Table]) -> str:
    """ONE statement: each table as an array of rows (``ROW(q.*)``, native types), in its own order."""
    parts = [f"(SELECT array_agg(ROW(q.*) ORDER BY q.{t.order.replace(', ', ', q.')}) FROM "  # noqa: S608 constants
             f"(SELECT {t.select} {t.tail}) q) AS {name}" for name, t in tables.items()]
    return "SELECT " + ", ".join(parts)


@dataclass
class Prefetch:
    """What was read: ``data[table][strategy id]`` (an id with no rows is present and empty: read, nothing there)."""

    user_ref: str
    data: dict[str, dict[int, list[Any]]]
    once: dict[str, list[Any]] = field(default_factory=dict)
    served: int = 0  # statements answered from memory (a measurement)
    #: statements learned at run time from the store's own public function (see ``_learn_owns``)
    learned: dict[str, Match] = field(default_factory=dict)


class _Capture:
    """A connection that only records the statement it is asked to run."""

    statement: Any = None

    async def execute(self, statement: Any, *_args: Any, **_kw: Any) -> Rows:
        self.statement = statement
        return Rows([])


async def _learn_owns() -> dict[str, Match]:
    """The ownership statement ``strategy_store.owns`` runs (the pause read asks it once per row), learned from that
    public function itself: the ownership SQL has ONE home (tests/test_ownership_sql_one_home.py) and is not copied
    here. Params of that statement: ``s`` the strategy, ``u`` the user."""
    from ofo_app import strategy_store  # noqa: PLC0415 - late: strategy_store reaches the order modules
    capture = _Capture()
    await strategy_store.owns(capture, "-", 0)
    return {} if capture.statement is None else {norm(capture.statement): Match("strategies", "s", "u", _owned)}


async def read_all(conn: Any, ids: list[int], user_ref: str) -> Prefetch:
    """Every table, for every id, in ONE query. Raises on any failure: the caller then lets each row read for itself."""
    row = (await conn.execute(text(_combined_sql(_TABLES)), {"ids": ids, "user_ref": user_ref})).one()
    data: dict[str, dict[int, list[Any]]] = {}
    for name, table in _TABLES.items():
        per: dict[int, list[Any]] = {sid: [] for sid in ids}
        named = collections.namedtuple("Row", [c for c in table.cols if c != SID], rename=True)
        for record in row._mapping[name] or ():
            values = dict(zip(table.cols, record, strict=True))
            per.setdefault(int(values[SID]), []).append(named(*[values[c] for c in table.cols if c != SID]))
        data[name] = per
    for sid, rows in data["strategies"].items():  # a strategy of someone else is not in this table: left to the row
        if not rows:
            for per in data.values():
                per.pop(sid, None)
    return Prefetch(user_ref, data, learned=await _learn_owns())


def install(db: Any, pre: Prefetch) -> Callable[[], None]:
    """Replace ``db.execute`` for the rest of this request; returns the function that puts the real one back."""
    real = db.execute

    def serve(statement: Any, params: Any) -> Rows | None:
        key = norm(statement)
        if key in pre.once:
            return Rows(pre.once[key])
        match = _MATCH.get(key) or pre.learned.get(key)
        if match is None or not isinstance(params, dict):
            return None
        if match.user_param is not None and params.get(match.user_param) != pre.user_ref:
            return None
        sid = params.get(match.id_param)
        rows = pre.data.get(match.table, {}).get(sid) if isinstance(sid, int) else None
        return None if rows is None else Rows(match.view(rows))

    async def execute(statement: Any, params: Any = None, *args: Any, **kwargs: Any) -> Any:
        served = None if args or kwargs else serve(statement, params)
        if served is not None:
            pre.served += 1
            return served
        result = await real(statement, params, *args, **kwargs)
        if norm(statement) in _ONCE and not args and not kwargs:
            rows = result.all()
            pre.once[norm(statement)] = rows
            return Rows(rows)
        return result

    db.execute = execute

    def restore() -> None:
        with contextlib.suppress(AttributeError):
            del db.execute  # the instance attribute only: the class's own method is back

    return restore
