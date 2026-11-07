"""THE one way a DB test puts scenario contracts into the catalogue: the UNION of every scenario's instrument list
(``scenario_mode.library_numbers`` gives one token per symbol across the library), loaded once per test database.
A later scenario then changes only quotes and the clock, never the list, so no contract is ever delisted and
re-listed (the 0005 lifecycle guard refuses that once a fixture expiry has passed:
knowledge/findings/fixture-dates-expire-with-the-clock.json). Guarded by tests_app/test_scenario_catalogue_guard.py.
"""
from __future__ import annotations

import datetime

from ofo.settings import calc as _calc
from ofo.settings import defaults as _defaults
from ofo.timeutil import IST
from ofo_app import catalogue_store, scenario_mode
from sqlalchemy import text

#: one list date before every scenario's expiry, so the load retires nothing (ADR-057)
CATALOGUE_AS_OF = datetime.datetime(2026, 10, 31, 9, 0, tzinfo=IST)
MAX_DELIST = _calc.max_delist_percent(_defaults())


def scenario_ids() -> list[str]:
    """Every scenario of the library: the ADJ files and the path scenarios."""
    return sorted([p.stem for p in scenario_mode.FIXTURES.glob("ADJ-*.json")]
                  + [p.name for p in scenario_mode.PATHS.glob("PATH-*") if p.is_dir()])


def library_contracts() -> list:
    """The union of every scenario's instrument list (the index rows once). ADJ-20d leaves NIFTY26N0323700CE out of
    its own list; the union carries it (every other scenario lists it) and ADJ-20d's provider still does not."""
    union: dict[str, object] = {}
    for sid in scenario_ids():
        for lc in scenario_mode.load(sid).provider.instrument_master():
            union.setdefault(scenario_mode.instrument_id(lc), lc)
    return list(union.values())


async def _live_ids(conn) -> set[str]:
    rows = (await conn.execute(text(f"SELECT exchange_segment, exchange_token FROM {catalogue_store.CONTRACTS} "  # noqa: S608 - constant table
                                    "WHERE NOT retired AND NOT delisted"))).all()
    return {f"{seg}:{tok}" for seg, tok in rows}


async def load_library(app_engine) -> None:
    """The union into the catalogue unless every member is already live (then nothing is written). Forced only so a
    list another test committed may be replaced; the union itself is the same list every time, so it never delists
    one of its own members."""
    contracts = library_contracts()
    async with app_engine.begin() as conn:
        if {scenario_mode.instrument_id(lc) for lc in contracts} <= await _live_ids(conn):
            return
        await catalogue_store.apply_update(conn, contracts, as_of=CATALOGUE_AS_OF, force=True,
                                           reason="test: the scenario library's contracts", actor="test",
                                           max_delist_percent=MAX_DELIST)
