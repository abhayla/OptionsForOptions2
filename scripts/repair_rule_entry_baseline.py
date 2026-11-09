"""Repair the F-71 rule memory written with a baseline taken AFTER the entry (issue 65, finding
``rule-entry-baseline-taken-at-first-check``; ADR-258, REQ-159 / F-71).

Class: rule state rows at the entry starting point (``adjustment_no`` 0) stored held_at_entry=true, seen_clear=false.
For each, the rule is evaluated on the strategy's REAL entry (stored entry facts: first-fill spot and time, today's
short strikes, no Greeks, the strategy's playbook and the user's gap window). A rule that is computable there and was
NOT true is repaired: seen_clear set to true through the store's one write (``put_rule_state``; the 0031 guard allows
only false -> true). Nothing is deleted; held_at_entry is never changed. A rule true at entry, not computable at
entry (needs Greeks), or a strategy with no entry facts / no open legs / no playbook is left as it is and counted.

Dry run by default (prints the counts, writes nothing); ``--apply`` writes, in one transaction. Re-runnable: a
repaired row has seen_clear=true, so it is no longer in the class.

Usage: python scripts/repair_rule_entry_baseline.py [--apply]   (DATABASE_URL = the target database)
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import datetime
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from ofo.adjustment import playbook_eval as pe
from ofo.adjustment.preferences import from_values as prefs_from_values
from ofo.engine.legs import Action
from ofo_app import adjustment_check as check
from ofo_app import catalogue_store, entry_facts_store, playbook_store, user_preferences_store
from sqlalchemy import text

_CLASS = text(
    "SELECT r.strategy_id, s.user_ref, r.rule_id, f.entry_spot, f.created_at "
    "FROM public.adjustment_rule_state r JOIN public.strategies s ON s.id = r.strategy_id "
    "LEFT JOIN public.strategy_entry_facts f ON f.strategy_id = r.strategy_id "
    "WHERE r.adjustment_no = 0 AND r.held_at_entry AND NOT r.seen_clear ORDER BY r.strategy_id, r.rule_id")

#: count keys, in print order
HELD = "held_not_seen_clear"
FALSE_AT_ENTRY = "false_at_entry"  # the repaired (or, dry run, to-repair) rows
TRUE_AT_ENTRY = "true_at_entry"
NOT_COMPUTABLE = "not_computable_at_entry"
NO_FACTS = "no_entry_facts"
NO_POSITION = "no_open_legs"
NO_BODY = "no_playbook"
KEYS = (HELD, FALSE_AT_ENTRY, TRUE_AT_ENTRY, NOT_COMPUTABLE, NO_FACTS, NO_POSITION, NO_BODY)


def _base_state(position: Any) -> pe.StrategyState:
    shorts = tuple(pe.ShortLeg(x.strike, None, None, x.type) for x in position.legs if x.side == Action.SELL.value)
    return pe.StrategyState(stops=None, expiry_kind=position.expiry_kind or "weekly",  # type: ignore[arg-type]
                            days_left=0, hhmm="00:00", shorts=shorts)


def _entry_state(position: Any, spot: Any, at: datetime.datetime) -> pe.StrategyState:
    return check._entry_state(at, spot, None, _base_state(position), position)  # the worker's own builder


async def repair(conn: Any, read_position: Callable[[int], Awaitable[Any]], *, apply: bool) -> dict[str, int]:
    """The class counted (and, with ``apply``, repaired) on ``conn``; ``read_position(strategy_id)`` -> the open
    ``Position`` or None. Returns the counts (``KEYS``)."""
    counts = dict.fromkeys(KEYS, 0)
    by_strategy: dict[int, list] = collections.defaultdict(list)
    for row in (await conn.execute(_CLASS)).all():
        by_strategy[row.strategy_id].append(row)
    counts[HELD] = sum(len(v) for v in by_strategy.values())
    # the stored live contracts, for the strike gap the type read needs (as the worker's instrument master)
    listed = [lc for _, lc, _ in await catalogue_store._load_live(conn)] if by_strategy else []
    for sid, rows in by_strategy.items():
        first = rows[0]
        if first.entry_spot is None or first.created_at is None:
            counts[NO_FACTS] += len(rows)
            continue
        position = await read_position(sid)
        if position is None or not position.legs:
            counts[NO_POSITION] += len(rows)
            continue
        resolved = await check.resolve(conn, first.user_ref, sid,
                                       check.strategy_type(position, first.entry_spot, listed))
        if resolved.body is None:
            counts[NO_BODY] += len(rows)
            continue
        gap_until = prefs_from_values(await user_preferences_store.values_for(conn, first.user_ref)).gap_until
        basket = await entry_facts_store.read_basket(conn, sid, 0)  # ADR-283: the stored fill, as the checks read it
        if basket is None:
            entry = _entry_state(position, first.entry_spot, first.created_at)
        else:
            entry = check.entry_baseline(None, _base_state(position), position, None, 0, basket)
        ev = pe.evaluate(resolved.body, entry, None, entry, gap_until=gap_until)
        clear = set(ev.clear)
        fired = {r.rule_id for r in ev.results if isinstance(r, (pe.Flag, pe.AlreadyTrue))}
        for row in rows:
            if row.rule_id in clear:
                counts[FALSE_AT_ENTRY] += 1
                if apply:
                    await playbook_store.put_rule_state(conn, first.user_ref, sid, row.rule_id, held_at_entry=True,
                                                        seen_clear=True, adjustment_no=0)
            elif row.rule_id in fired:
                counts[TRUE_AT_ENTRY] += 1
            else:
                counts[NOT_COMPUTABLE] += 1
    return counts


async def _main(apply: bool) -> int:  # pragma: no cover - process wiring; ``repair`` is tested on a throwaway DB
    from ofo_app.adjustment_readers import TrackedExited, TrackedUnreadable, read_tracked  # noqa: PLC0415
    from ofo_app.db import get_sessionmaker  # noqa: PLC0415

    async def position_of(sid: int) -> Any:
        try:
            tracked = await read_tracked(sid, None)
        except (TrackedExited, TrackedUnreadable):
            return None
        return None if tracked is None else tracked.position

    async with get_sessionmaker()() as db, db.begin():
        counts = await repair(db, position_of, apply=apply)
    print(("APPLIED " if apply else "DRY RUN ") + " ".join(f"{k}={counts[k]}" for k in KEYS))
    return 0


if __name__ == "__main__":  # pragma: no cover
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the repair (default: dry run, counts only)")
    sys.exit(asyncio.run(_main(parser.parse_args().apply)))
