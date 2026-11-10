"""GC-ICSAFE c32/c33 (issue #680): the daily-list guard accepts a strike-grid change, still refuses a cut-off file.

Fixture: tests/fixtures/instruments/nifty-contracts-2026-11-09.csv - the 4118 real NIFTY rows read from the dev store
after the forced load of 2026-11-09 (2049 rows dropped). STORED = first seen before 9 Nov; 9 NOV LIST = not delisted.
"""
from __future__ import annotations

import csv
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from ofo.audit import AuditLog
from ofo.instruments.catalogue import Catalogue
from ofo.instruments.models import Contract
from ofo.settings import calc as _calc
from ofo.settings import defaults as _defaults

AS_OF = datetime(2026, 11, 9, 11, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
MAX_DELIST = _calc.max_delist_percent(_defaults())
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "instruments" / "nifty-contracts-2026-11-09.csv"


def _contract(r: dict[str, str]) -> Contract:
    return Contract(exchange_segment=r["exchange_segment"], exchange_token=int(r["exchange_token"]), name=r["name"],
                    expiry=date.fromisoformat(r["expiry"]), strike=Decimal(r["strike"]), tick_size=Decimal("0.05"),
                    lot_size=75, instrument_type=r["instrument_type"])


@pytest.fixture(scope="module")
def real() -> list[dict[str, str]]:
    with FIXTURE.open(newline="") as f:
        return list(csv.DictReader(f))


@pytest.fixture()
def stored(real) -> list[Contract]:
    return [_contract(r) for r in real if r["first_seen_at"][:10] < "2026-11-09"]


@pytest.fixture()
def nov9_list(real) -> list[Contract]:
    return [_contract(r) for r in real if r["delisted"] == "False" and r["first_seen_at"][:10] < "2026-11-10"]


def _cat(stored: list[Contract]) -> Catalogue:
    cat = Catalogue()
    cat.load(stored)
    return cat


def _update(cat: Catalogue, rows: list[Contract], **kw):
    return cat.update(rows, as_of=AS_OF, max_delist_percent=MAX_DELIST, **kw)


def _sorted(rows: list[Contract]) -> list[Contract]:
    return sorted(rows, key=lambda c: (c.expiry, c.strike, c.instrument_type))


def test_the_real_9_nov_list_is_accepted_and_counts_the_grid_change(stored, nov9_list) -> None:
    cat = _cat(stored)
    carried = {c.id for c in nov9_list}
    leavers = {e.id for e in cat.all_entries()
               if e.currently_listed and e.contract.expiry >= date(2026, 11, 9) and e.id not in carried}
    assert len(leavers) > 0.1 * len(cat.all_entries())  # today's code refuses exactly this shape
    result = _update(cat, nov9_list)
    assert result.grid_change_left == len(leavers)


def test_a_list_cut_off_after_60_percent_is_still_refused(stored, nov9_list) -> None:
    rows = _sorted(nov9_list)
    with pytest.raises(ValueError, match="refused"):
        _update(_cat(stored), rows[: int(len(rows) * 0.6)])


def test_a_list_missing_one_whole_expiry_and_type_group_is_still_refused(stored, nov9_list) -> None:
    target = sorted({c.expiry for c in nov9_list})[3]
    cut = [c for c in nov9_list if not (c.expiry == target and c.instrument_type == "CE")]
    with pytest.raises(ValueError, match=r"\(ADR-05[89]\)"):
        _update(_cat(stored), cut)


def test_a_group_expiring_on_the_update_date_that_is_absent_is_not_a_cut_off(stored, nov9_list) -> None:
    assert not any(c.expiry == date(2026, 11, 9) for c in nov9_list)
    assert any(c.expiry == date(2026, 11, 9) for c in stored)
    assert _update(_cat(stored), nov9_list).grid_change_left > 0


def test_an_index_absent_from_the_new_list_is_refused(stored) -> None:
    with pytest.raises(ValueError, match="refused"):
        _update(_cat(stored), [])


def test_the_first_load_of_an_index_is_accepted_with_nothing_left(nov9_list) -> None:
    assert _update(Catalogue(), nov9_list).grid_change_left == 0


def test_only_futures_stored_and_one_future_group_missing_is_refused(stored) -> None:
    futs = sorted((c for c in stored if c.instrument_type == "FUT"), key=lambda c: c.expiry)
    assert len(futs) > 1
    with pytest.raises(ValueError, match="refused"):
        _update(_cat(futs), futs[:1])


def test_only_futures_stored_and_all_groups_carried_is_accepted(stored) -> None:
    futs = [c for c in stored if c.instrument_type == "FUT"]
    assert _update(_cat(futs), futs).grid_change_left == 0


def test_force_still_overrides_and_counts_nothing_under_the_rule(stored) -> None:
    result = _update(_cat(stored), [], force=True, reason="test", actor="ops", audit_log=AuditLog())
    assert result.grid_change_left == 0
