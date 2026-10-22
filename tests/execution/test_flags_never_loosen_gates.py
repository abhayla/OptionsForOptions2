"""REQ-117 AC-5 (W-132): "Flags never loosen a safety gate: margin, reconciliation block, market hours, kill switch and
freeze-limit checks run the same whatever a flag says." The kill switch lives in ofo_app, so its half of this proof is
``tests_app/test_flags_never_loosen_kill_switch.py``; this file holds the domain gates and the source scan over both.

Three layers, each with a test that dies without it:
1. every gate is run with EVERY flag on and with EVERY flag off (and with held triggers on, the one flag that must never
   be on) and its outcome must be identical, on a passing input and on a blocking input;
2. a tripwire: while a gate runs, any read of a flag (``is_supported``, ``CapabilitySet.value``, the Zerodha loader)
   raises, so a gate that starts asking a flag goes red even when the outcomes happen to agree;
3. a source scan: no gate module imports the capabilities modules (discovered by path, fails closed on a file that
   cannot be parsed).
"""
from __future__ import annotations

import ast
import datetime
from decimal import Decimal as D
from pathlib import Path

import pytest
from execution_inputs import all_true_context, check
from plan_inputs import CE, SELL, FakeMargin, leg

from ofo.broker import capabilities as caps_module
from ofo.broker import kite_capabilities
from ofo.broker.capabilities import CAPABILITY_NAMES, CapabilitySet, CapabilityValue
from ofo.errors.templates import display_text
from ofo.execution.freeze import StoredFreeze, freeze_check
from ofo.execution.margin_gate import check_margin
from ofo.execution.planned import ExecutionPlan, PlannedLeg
from ofo.reconciliation.blocking import blocked_strategy_ids

ROOT = Path(__file__).resolve().parents[2]
DAY = datetime.date(2026, 10, 22)
SYMBOL = "NIFTY26O1923550CE"
TODAY = datetime.date(2026, 10, 16)
LIMIT = StoredFreeze(limit=3511, lot=65, file_date=datetime.date(2026, 10, 15))  # the real row, F-36 (see test_freeze_review_block)
#: Gate modules by path: the safety gate, its inputs, the margin and freeze checks, the send guard, every
#: reconciliation module, and the kill switch.
GATE_FILES = ("backend/ofo/execution/safety.py", "backend/ofo/execution/context.py", "backend/ofo/execution/margin_gate.py",
              "backend/ofo/execution/freeze.py", "backend/ofo/execution/send_guard.py", "backend/ofo/execution/price_check.py",
              "backend/ofo/execution/planned.py", "backend/ofo/execution/review.py", "backend/ofo/execution/sequence.py",
              "backend/ofo_app/order_path_switch.py")
GATE_FOLDERS = ("backend/ofo/reconciliation",)
FLAG_MODULES = ("ofo.broker.capabilities", "ofo.broker.kite_capabilities", "capabilities", "kite_capabilities")


def _flags(on: bool, held_triggers: bool = False) -> None:
    """Replace Zerodha's declared set: every flag on (held triggers only when asked) or none at all."""
    declared = {n: (on, "tests/execution/test_flags_never_loosen_gates.py", DAY) for n in CAPABILITY_NAMES}
    declared["broker_held_triggers"] = (held_triggers, "tests/execution/test_flags_never_loosen_gates.py", DAY)
    kite_capabilities.ZERODHA_DECLARED = declared  # type: ignore[misc]


@pytest.fixture(autouse=True)
def _restore_flags():
    original = kite_capabilities.ZERODHA_DECLARED
    yield
    kite_capabilities.ZERODHA_DECLARED = original  # type: ignore[misc]


def _plan(units: int) -> ExecutionPlan:
    from datetime import date
    lg = leg(SELL, CE, "23550", qty=units, expiry=date(2026, 10, 19))
    return ExecutionPlan("S-1", (PlannedLeg("leg-1", SYMBOL, lg),))


def _gate_signature(condor, catalogue, eligibility, monkeypatch) -> dict[str, object]:
    """Every gate, each on a passing and on a blocking input, reduced to plain comparable values."""
    from ofo.execution.review import execution_review

    out: dict[str, object] = {}
    cases = {  # context overrides: market hours, reconciliation block, margin (in the safety gate)
        "open_ok": {}, "market_closed": {"market_open": False}, "market_unknown": {"market_open": None},
        "reconciliation_blocked": {"reconciliation_blocked_strategy_ids": frozenset({"S-1"})},
        "margin_short": {"margin_available": D("100.00")}, "margin_unknown": {"margin_available": None},
    }
    for name, overrides in cases.items():
        result = check(condor, all_true_context(**overrides), catalogue, eligibility)
        out[f"safety:{name}"] = (result.blocked, tuple(sorted(c.value for c in result.failed_codes)),
                                 tuple(sorted(f.reason for f in result.failures)))
    for name, (available, required) in {"enough": (D("100.00"), D("50.00")), "short": (D("50.00"), D("100.00")),
                                        "unknown": (None, D("100.00")), "negative": (D("-1.00"), D("0.00"))}.items():
        verdict = check_margin(available, required)
        out[f"margin:{name}"] = (verdict.allowed, None if verdict.message is None else display_text(verdict.message))
    for units in (54 * 65, 55 * 65):
        review = execution_review(_plan(units), FakeMargin({}), freeze_limits={SYMBOL: LIMIT}, today=TODAY)
        out[f"freeze:{units}"] = (review.can_execute, tuple(display_text(b.message) for b in review.blocked))
        found = freeze_check(_plan(units), {SYMBOL: LIMIT}, today=TODAY)
        out[f"freeze_check:{units}"] = tuple(display_text(b.message) for b in found.blocks)
    out["reconciliation:none"] = blocked_strategy_ids(None, {})
    return out


def test_ac5_every_gate_gives_the_same_outcome_with_every_flag_on_and_every_flag_off(
        condor, catalogue, eligibility, monkeypatch) -> None:
    """AC-5 (attack 6): margin, reconciliation block, market hours, kill switch and freeze limit, each on an input that
    passes and one that blocks, give identical outcomes with all flags on, all off, and held triggers forced on."""
    _flags(on=True)
    all_on = _gate_signature(condor, catalogue, eligibility, monkeypatch)
    _flags(on=False)
    all_off = _gate_signature(condor, catalogue, eligibility, monkeypatch)
    _flags(on=False, held_triggers=True)
    triggers_only = _gate_signature(condor, catalogue, eligibility, monkeypatch)
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
        raise AssertionError("a safety gate read a capability flag")

    monkeypatch.setattr(caps_module, "is_supported", tripwire)
    monkeypatch.setattr(caps_module.CapabilitySet, "value", tripwire)
    monkeypatch.setattr(kite_capabilities, "load_zerodha_capabilities", tripwire)
    monkeypatch.setattr(caps_module, "load_or_off", tripwire)
    _gate_signature(condor, catalogue, eligibility, monkeypatch)


def test_ac5_the_tripwire_itself_trips_when_a_flag_is_read(monkeypatch) -> None:
    """AC-5 (mutation of the tripwire): a read of a flag really does raise under the tripwire, so layer 2 can go red."""
    def tripwire(*_a: object, **_k: object) -> None:
        raise AssertionError("read")

    monkeypatch.setattr(CapabilitySet, "value", tripwire)
    with pytest.raises(AssertionError):
        CapabilitySet({"funds_read": CapabilityValue(True, "x", DAY)}).value("funds_read")


def _gate_sources() -> list[Path]:
    paths = [ROOT / rel for rel in GATE_FILES]
    for folder in GATE_FOLDERS:
        paths.extend(sorted((ROOT / folder).rglob("*.py")))
    return paths


def _flag_imports(source: str) -> list[str]:
    """Names of capability modules a source imports, by import source (an alias or re-export does not hide one)."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.extend(a.name for a in node.names if a.name in FLAG_MODULES)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module in FLAG_MODULES or (module in ("ofo.broker", "ofo_app") and any(
                    a.name in ("capabilities", "kite_capabilities") for a in node.names)):
                found.append(module)
            elif any(a.name in ("capabilities", "kite_capabilities") for a in node.names):
                found.append(module)  # `from . import capabilities` or any other source naming it
    return found


def test_ac5_no_gate_module_imports_the_capability_modules() -> None:
    """AC-5: discovered gate sources (explicit files + every reconciliation module) import no capability module; a file
    that is missing or does not parse is a failure, never a skip."""
    paths = _gate_sources()
    assert len(paths) >= len(GATE_FILES) + 5  # the reconciliation folder really contributed files
    for path in paths:
        assert path.is_file(), f"{path} is missing: a gate module cannot be cleared unread"
        assert _flag_imports(path.read_text(encoding="utf-8")) == [], path.name


@pytest.mark.parametrize("planted", [
    "import ofo.broker.capabilities\n", "from ofo.broker.capabilities import is_supported\n",
    "from ofo.broker import capabilities\n", "from ofo.broker import kite_capabilities\n",
    "from ofo.broker.kite_capabilities import load_zerodha_capabilities as f\n", "from . import capabilities\n",
    "import ofo.broker.kite_capabilities\n",
])
def test_ac5_the_import_scan_sees_every_import_shape(planted: str) -> None:
    """AC-5: each import shape a gate could use to reach a flag is found (the scan itself dies without its rules)."""
    assert _flag_imports(planted), planted
    assert _flag_imports("import os\nfrom ofo.errors import render\n") == []
