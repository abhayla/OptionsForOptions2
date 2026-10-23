"""REQ-117 AC-5 (W-132): "Flags never loosen a safety gate: margin, reconciliation block, market hours, kill switch and
freeze-limit checks run the same whatever a flag says." The kill switch lives in ofo_app, so its half of this proof is
``tests_app/test_flags_never_loosen_kill_switch.py``; the import scan over every gate module is
``tests/execution/test_gates_import_no_flags.py``.

Here: every domain gate is run with EVERY flag on, with every flag off, and with held triggers forced on (the one flag
that must never be on), each on an input that passes and one that blocks; the outcomes must be identical. A tripwire
then turns every way to read a flag into an error while the gates run: a gate that starts asking a flag goes red even
when the outcomes happen to agree.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from execution_inputs import all_true_context, check
from ofo.broker import flags as flags_module
from ofo.broker import kite_flags
from ofo.broker.flags import FLAG_NAMES, FlagSet, FlagValue
from ofo.errors.templates import display_text
from ofo.execution.freeze import freeze_check
from ofo.execution.margin_gate import check_margin
from ofo.execution.review import execution_review
from ofo.reconciliation.blocking import blocked_strategy_ids
from plan_inputs import FakeMargin
from test_freeze_review_block import REAL, SYMBOL, TODAY, plan_of

DAY = datetime.date(2026, 10, 22)
SOURCE = "tests/execution/test_flags_never_loosen_gates.py"
D100, D50, D1, D0 = Decimal("100.00"), Decimal("50.00"), Decimal("1.00"), Decimal("0.00")


def _flags(monkeypatch: pytest.MonkeyPatch, *, on: bool, held_triggers: bool = False) -> None:
    """Zerodha's declared set replaced: every flag on (held triggers only when asked) or none on."""
    declared = {n: (held_triggers if n == "broker_held_triggers" else on, SOURCE, DAY) for n in FLAG_NAMES}
    monkeypatch.setattr(kite_flags, "declared", lambda: declared)


def _gate_signature(condor, catalogue, eligibility) -> dict[str, object]:
    """Every domain gate, each on a passing and on a blocking input, reduced to plain comparable values."""
    out: dict[str, object] = {}
    cases = {  # context overrides: market hours, reconciliation block, margin (in the safety gate)
        "open_ok": {}, "market_closed": {"market_open": False}, "market_unknown": {"market_open": None},
        "reconciliation_blocked": {"reconciliation_blocked_strategy_ids": frozenset({"S-1"})},
        "margin_short": {"margin_available": D100}, "margin_unknown": {"margin_available": None},
    }
    for name, overrides in cases.items():
        result = check(condor, all_true_context(**overrides), catalogue, eligibility)
        out[f"safety:{name}"] = (result.blocked, tuple(sorted(c.value for c in result.failed_codes)),
                                 tuple(sorted(f.reason for f in result.failures)))
    for name, (available, required) in {"enough": (D100, D50), "short": (D50, D100), "unknown": (None, D100),
                                        "negative": (-D1, D0)}.items():
        verdict = check_margin(available, required)
        out[f"margin:{name}"] = (verdict.allowed, None if verdict.message is None else display_text(verdict.message))
    for units in (54 * 65, 55 * 65):
        review = execution_review(plan_of(units), FakeMargin({}), freeze_limits={SYMBOL: REAL}, today=TODAY)
        out[f"freeze:{units}"] = (review.can_execute, tuple(display_text(b.message) for b in review.blocked))
        found = freeze_check(plan_of(units), {SYMBOL: REAL}, today=TODAY)
        out[f"freeze_check:{units}"] = tuple(display_text(b.message) for b in found.blocks)
    out["reconciliation:none"] = blocked_strategy_ids(None, {})
    return out


def test_ac5_every_gate_gives_the_same_outcome_with_every_flag_on_and_every_flag_off(
        condor, catalogue, eligibility, monkeypatch) -> None:
    """AC-5 (attack 6): margin, reconciliation block, market hours and freeze limit, each on an input that passes and
    one that blocks, give identical outcomes with all flags on, all off, and held triggers forced on."""
    _flags(monkeypatch, on=True)
    all_on = _gate_signature(condor, catalogue, eligibility)
    _flags(monkeypatch, on=False)
    all_off = _gate_signature(condor, catalogue, eligibility)
    _flags(monkeypatch, on=False, held_triggers=True)
    triggers_only = _gate_signature(condor, catalogue, eligibility)
    assert all_on == all_off == triggers_only
    # the signature is not vacuous: it holds both a pass and a block for each gate (expected from the gate rules)
    assert all_on["safety:open_ok"][0] is False  # type: ignore[index]
    assert all_on["safety:market_closed"][0] is True  # type: ignore[index]
    assert "MARKET_CLOSED" in all_on["safety:market_closed"][1]  # type: ignore[index]
    assert "RECONCILIATION_MISMATCH" in all_on["safety:reconciliation_blocked"][1]  # type: ignore[index]
    assert "MARGIN_INSUFFICIENT" in all_on["safety:margin_short"][1]  # type: ignore[index]
    assert all_on["margin:enough"][0] is True and all_on["margin:short"][0] is False  # type: ignore[index]
    assert all_on[f"freeze:{54 * 65}"][0] is True and all_on[f"freeze:{55 * 65}"][0] is False  # type: ignore[index]


def test_ac5_a_gate_never_reads_a_flag(condor, catalogue, eligibility, monkeypatch) -> None:
    """AC-5: with every way to read a flag turned into an error, every gate still runs: none of them asks a flag."""
    def tripwire(*_a: object, **_k: object) -> None:
        raise AssertionError("a safety gate read a broker flag")

    monkeypatch.setattr(flags_module, "is_supported", tripwire)
    monkeypatch.setattr(flags_module, "flags_or_off", tripwire)
    monkeypatch.setattr(FlagSet, "value", tripwire)
    monkeypatch.setattr(kite_flags, "load_zerodha_flags", tripwire)
    monkeypatch.setattr(kite_flags, "declared", tripwire)
    _gate_signature(condor, catalogue, eligibility)


def test_ac5_the_tripwire_itself_trips_when_a_flag_is_read(monkeypatch) -> None:
    """AC-5 (mutation of the tripwire): a read of a flag really does raise under the tripwire, so the test above can go
    red."""
    def tripwire(*_a: object, **_k: object) -> None:
        raise AssertionError("read")

    monkeypatch.setattr(FlagSet, "value", tripwire)
    with pytest.raises(AssertionError):
        FlagSet({"funds_read": FlagValue(True, "x", DAY)}).value("funds_read")
