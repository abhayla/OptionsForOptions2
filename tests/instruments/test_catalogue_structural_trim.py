"""ADR-147: the structural second pass that tells a far-strike trim from a broken download, on the real Kite lists of
2026-10-15 and 2026-10-21 (reduced by scripts/cut_trim_fixture.py to NIFTY + SENSEX).

Real case: the 2026-10-21 list carries NIFTY 2026-10-27 strikes 20050-27200 only; the 2026-10-15 list carried
17000-30000. 234 of 522 live NIFTY contracts vanish (44.8%), so ADR-058 refuses; every dropped strike is a tail.
"""
from __future__ import annotations

import dataclasses
import gzip
import random
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from ofo.audit import AuditLog, EventType
from ofo.instruments.catalogue import (
    TRIM_ACCEPTED_ACTION,
    Catalogue,
    StructuralPass,
    _anchor,
)
from ofo.instruments.models import BSE_FO, InstrumentId, ListedContract
from ofo.instruments.parser import parse_instruments_stream
from ofo.timeutil import IST

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "instruments"
AS_OF = datetime(2026, 10, 21, 8, 40, tzinfo=IST)
NIFTY_WEEKLY = date(2026, 10, 27)


def _rows(name: str) -> list[ListedContract]:
    with gzip.open(FIXTURES / name, "rt", encoding="utf-8") as fh:
        return list(parse_instruments_stream(fh))


OLD = _rows("kite-2026-10-15-nifty-sensex.csv.gz")
NEW = _rows("kite-2026-10-21-nifty-sensex.csv.gz")


def _catalogue(rows: list[ListedContract] = OLD) -> Catalogue:
    cat = Catalogue()
    cat.load(rows)
    return cat


def _pass(held: frozenset[InstrumentId] | None = frozenset()) -> tuple[StructuralPass, AuditLog]:
    log = AuditLog()
    return StructuralPass(held=held, audit_log=log, actor="system:catalogue-update"), log


def _weekly(r: ListedContract) -> bool:
    return r.contract.name == "NIFTY" and r.contract.expiry == NIFTY_WEEKLY


def _refused(new: list[ListedContract], held: frozenset[InstrumentId] | None = frozenset(),
             old: list[ListedContract] = OLD) -> str:
    cat = _catalogue(old)
    structural, log = _pass(held)
    with pytest.raises(ValueError) as exc:
        cat.update(new, as_of=AS_OF, structural=structural)
    assert len(log.events) == 0, "a refused update writes no audit row"
    return str(exc.value)


def test_core_real_far_strike_trim_refused_by_count_guard_today() -> None:
    with pytest.raises(ValueError, match=r"234 of 522 live NIFTY contracts.*ADR-058"):
        _catalogue().update(NEW, as_of=AS_OF)


def test_core_real_far_strike_trim_accepted_by_structural_pass() -> None:
    cat = _catalogue()
    structural, log = _pass()
    result = cat.update(NEW, as_of=AS_OF, structural=structural)
    assert result.structural_trim_accepted is True
    assert len(result.delisted) == 234
    gone = {cat.get(i).contract.strike for i in result.delisted}
    assert max(s for s in gone if s < 23500) == Decimal("20000") and min(s for s in gone if s > 23500) == 27250
    events = list(log.events)
    assert len(events) == 1 and events[0].event_type is EventType.ADMIN_CHANGE_RECORDED
    payload = events[0].payload
    assert payload["action"] == TRIM_ACCEPTED_ACTION
    assert "234 of 904 live contracts" in payload["reason"] and "ADR-058" in payload["reason"]
    assert len(payload["dropped_instrument_tokens"]) == 234 and len(payload["dropped_tradingsymbols"]) == 234


def test_near_band_of_one_expiry_missing_is_refused() -> None:
    new = [r for r in NEW if not (_weekly(r) and Decimal(24000) <= r.contract.strike <= Decimal(24300))]
    assert "inside the near-the-money band" in _refused(new)


def test_tail_inside_the_band_is_refused() -> None:
    # Only tails are cut (no hole), but the lower cut reaches into the band around the anchor 23500 (+/- 1175).
    new = [r for r in NEW if not (_weekly(r) and r.contract.strike < Decimal(23000))]
    assert "inside the near-the-money band" in _refused(new)


def test_hole_outside_the_band_is_refused() -> None:
    new = [r for r in NEW if not (_weekly(r) and r.contract.strike == Decimal(21000))]
    assert "leaves a hole inside the kept strikes 20050-27200" in _refused(new)


def test_one_whole_segment_missing_is_refused() -> None:
    new = [r for r in NEW if r.contract.exchange_segment != BSE_FO]
    assert f"segment(s) ['{BSE_FO}']" in _refused(new)


def test_forty_percent_random_cut_is_refused() -> None:
    rng = random.Random(244)  # Q244's original failure: a list missing a random 40%
    new = [r for r in NEW if rng.random() >= 0.4]
    assert "structural trim check (ADR-147) also refused" in _refused(new)


def test_empty_list_is_refused() -> None:
    assert "absent from the list" in _refused([])


def test_list_without_index_rows_is_refused() -> None:
    new = [r for r in NEW if not r.contract.is_index()]
    msg = _refused(new)
    assert "is not an option strike" in msg or "absent from the list" in msg


def test_dropped_contract_held_by_an_open_plan_leg_is_refused() -> None:
    far = next(r.id for r in OLD if _weekly(r) and r.contract.strike == Decimal(17000))
    assert "dropped contract(s) are held" in _refused(NEW, held=frozenset({far}))


def test_held_contracts_unreadable_is_refused() -> None:
    assert "could not be read" in _refused(NEW, held=None)


def test_no_anchor_derivable_is_refused() -> None:
    one_strike = [r for r in OLD if not _weekly(r) or r.contract.strike == Decimal(17000)]
    assert "no anchor level is derivable" in _refused(NEW, old=one_strike)
    assert _anchor({Decimal(17000)}) is None and _anchor(set()) is None


def test_token_reused_on_a_live_contract_is_refused() -> None:
    victim = next(r for r in NEW if _weekly(r) and r.contract.strike == Decimal(24000))
    moved = dataclasses.replace(victim, contract=dataclasses.replace(victim.contract, expiry=date(2026, 12, 29)))
    new = [moved if r.id == victim.id else r for r in NEW]
    assert "token reused" in _refused(new)


def test_without_structural_inputs_the_count_refusal_stands() -> None:
    with pytest.raises(ValueError) as exc:
        _catalogue().update(NEW, as_of=AS_OF)
    assert "ADR-147" not in str(exc.value)


def test_second_pass_never_runs_when_count_guards_pass() -> None:
    cat = _catalogue()
    structural, log = _pass(held=None)  # would refuse if it ran
    small_drop = [r for r in OLD if not (_weekly(r) and r.contract.strike == Decimal(17000))]  # 2 of 522
    result = cat.update(small_drop, as_of=AS_OF, structural=structural)
    assert len(result.delisted) == 2
    assert result.structural_trim_accepted is False and len(log.events) == 0


def test_force_path_unchanged_with_structural_given() -> None:
    cat = _catalogue()
    structural, trim_log = _pass()
    force_log = AuditLog()
    result = cat.update(NEW, as_of=AS_OF, force=True, reason="real delisting", actor="admin",
                        audit_log=force_log, structural=structural)
    assert result.structural_trim_accepted is False and len(trim_log.events) == 0
    assert [e.payload["action"] for e in force_log.events] == ["catalogue_force_update"]


def test_dropped_future_is_refused_even_with_its_segment_present() -> None:
    future = next(r for r in NEW if _weekly(r) and r.contract.is_future())
    new = [r for r in NEW if r.id != future.id]
    assert "is not an option strike" in _refused(new, old=OLD + [future])


def test_type_with_no_kept_strike_is_refused() -> None:
    # Stored ladder 17000/30000 only (anchor 23500, both far); the list drops every weekly PE.
    old = [r for r in OLD if not _weekly(r) or r.contract.strike in (Decimal(17000), Decimal(30000))]
    new = [r for r in NEW if not (_weekly(r) and r.contract.instrument_type == "PE")]
    assert f"the list keeps no NIFTY {NIFTY_WEEKLY} PE strike" in _refused(new, old=old)
