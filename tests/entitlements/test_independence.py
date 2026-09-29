"""Entitlement is independent of strategy state, broker session and identity (REQ-017 AC-5).

Proof has two halves: (1) the module cannot see such state: it imports nothing from any other ``ofo``
area and nothing outside the standard library, and ``access_at`` accepts only a ledger and an instant;
(2) the access result is the same whatever that outside state is.
"""

import ast
import dataclasses
import inspect
import sys
from datetime import timedelta
from pathlib import Path

import pytest

import ofo.entitlements
from ofo.entitlements import engine
from ofo.entitlements.engine import access_at, trial_grant
from ofo.entitlements.events import AccessLevel, NewGrant, Source
from ofo.entitlements.ledger import EntitlementLedger

from .helpers import ist, ledger_for, note, record

PACKAGE_DIR = Path(ofo.entitlements.__file__).parent


def _foreign_imports(source: str) -> list[str]:
    """Every import in ``source`` that is neither standard library nor ``ofo.entitlements``."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import would stay inside the package only if level == 1
                names = [] if node.level == 1 else ["<relative beyond package>"]
            else:
                names = [node.module or ""]
        else:
            continue
        for name in names:
            top = name.split(".")[0]
            if name == "ofo.entitlements" or name.startswith("ofo.entitlements."):
                continue
            if top in sys.stdlib_module_names and top != "ofo":
                continue
            found.append(name)
    return found


def test_entitlement_package_imports_only_stdlib_and_itself():
    """AC-5: no file in ofo/entitlements imports another ofo area (strategy, broker, identity) or a third party."""
    files = sorted(PACKAGE_DIR.glob("*.py"))
    assert {f.name for f in files} >= {"__init__.py", "events.py", "ledger.py", "engine.py"}
    for path in files:
        assert _foreign_imports(path.read_text(encoding="utf-8")) == [], path.name


@pytest.mark.parametrize(
    "source",
    [
        "from ofo.broker import session",
        "import ofo.strategy.state",
        "from ofo import identity",
        "import requests",
        "from ..broker import session",
    ],
)
def test_import_scanner_flags_a_foreign_import(source):
    """AC-5: the scanner discriminates: each forbidden import in a synthetic file is reported."""
    assert _foreign_imports(source) != []


def test_access_takes_only_a_ledger_and_an_instant():
    """AC-5: access_at has no parameter through which strategy, broker or identity state could enter."""
    assert list(inspect.signature(access_at).parameters) == ["ledger", "at"]
    public = [name for name, obj in vars(engine).items() if inspect.isfunction(obj) and not name.startswith("_")]
    forbidden = ("strategy", "broker", "session", "zerodha", "kite", "identity", "email", "connected")
    for name in public:
        params = inspect.signature(getattr(engine, name)).parameters
        for param in params:
            assert not any(word in param.lower() for word in forbidden), f"{name}({param})"


def test_req_scenarios_pro_disconnected_limited_with_active_strategy_reconciliation_required():
    """AC-5: the three REQ-017 scenarios resolve from entitlement events alone, and Access carries no such state."""
    registered = ist(2026, 9, 29, 10)
    pro_user = record(
        ledger_for("u-pro"), NewGrant("paid-1", Source.PAID_MONTHLY, ist(2026, 9, 1), timedelta(days=30), "pay", note())
    )
    trial_user = record(ledger_for("u-trial"), trial_grant("t", registered, "reg", note()))

    # "A Pro user can be disconnected from Zerodha" and "a strategy can be Reconciliation Required while the
    # subscription is active": the Pro user's ledger holds no session or strategy, and stays Pro.
    assert access_at(pro_user, ist(2026, 9, 20)).level is AccessLevel.PRO
    # "A Limited user can have an Active strategy": after the trial the user is Limited, with nothing to consult.
    assert access_at(trial_user, ist(2026, 10, 7)).level is AccessLevel.LIMITED
    assert [f.name for f in dataclasses.fields(engine.Access)] == ["level", "at", "contributing"]


def test_user_id_does_not_change_access():
    """AC-5: the same events under a different user id (identity) give the same access at every instant."""
    paid = NewGrant("paid-1", Source.PAID_MONTHLY, ist(2026, 9, 1), timedelta(days=30), "pay", note())
    a, b = record(ledger_for("user-a"), paid), record(ledger_for("user-b"), paid)
    assert a.events == b.events
    for at in (ist(2026, 8, 31), ist(2026, 9, 1), ist(2026, 9, 30, 23, 59, 59), ist(2026, 10, 1)):
        assert access_at(a, at) == access_at(b, at)
