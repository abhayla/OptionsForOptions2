"""W-122 (REQ-109 AC-1, AC-2): paper tracking and the order path never import each other, in either direction.
No database needed."""
from __future__ import annotations

import ast
import pathlib

import pytest

pytestmark = pytest.mark.repo_scan

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_ac1_the_tracking_modules_import_nothing_from_the_order_path():
    """AC-1 (structural): the tracking route, store and domain import no execute/execution/basket module."""
    for path in (ROOT / "backend/ofo_app/routes/tracking.py", ROOT / "backend/ofo_app/tracking_store.py",
                 ROOT / "backend/ofo/tracking/paper.py"):
        imports = [line for line in path.read_text(encoding="utf-8").splitlines()
                   if line.startswith(("import ", "from "))]
        assert not [line for line in imports if "execut" in line or "basket" in line or "orders" in line], path


TRACKING_CODE = ("backend/ofo_app/routes/tracking.py", "backend/ofo_app/tracking_store.py")
#: The raw catalogue identity a stored contract id could be priced by without the live-identity check.
RAW_IDENTITY = ("exchange_token", "catalogue_contracts", "load_contract", "live_contract_id")


def _raw_identity_uses(path: pathlib.Path) -> list[str]:
    """Every way ``path`` could turn a stored contract id into a feed key without ofo_app.tracked_contracts: an import
    of the catalogue store (by import source, whatever local name it gets), a relative or dynamic import (cannot be
    resolved: fails closed), and any name, attribute or string naming the raw identity."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names = {a.name for a in node.names}
            if node.level or node.module is None:
                found.append(f"{node.lineno}: relative import (unresolvable)")
            elif node.module.startswith("ofo_app.catalogue_store") or (
                    node.module == "ofo_app" and "catalogue_store" in names) or "*" in names:
                found.append(f"{node.lineno}: from {node.module} import {sorted(names)}")
        elif isinstance(node, ast.Import):
            found += [f"{node.lineno}: import {a.name}" for a in node.names
                      if "catalogue_store" in a.name or a.name == "importlib"]
        elif isinstance(node, ast.Name) and node.id in {"__import__", "import_module"}:
            found.append(f"{node.lineno}: dynamic import {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in RAW_IDENTITY:
            found.append(f"{node.lineno}: .{node.attr}")
        elif isinstance(node, ast.Name) and node.id in RAW_IDENTITY:
            found.append(f"{node.lineno}: {node.id}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and any(
                r in node.value for r in RAW_IDENTITY[:2]):
            found.append(f"{node.lineno}: string naming {node.value[:40]!r}")
    return found


def test_tracking_reaches_a_feed_key_only_through_tracked_contracts():
    """Round-3 detection upgrade (run-discipline C8): ofo_app.tracked_contracts is the single choke point from a stored
    contract id to a feed key. The tracking route and store never import the catalogue store, never name the raw
    identity (exchange_token, the catalogue table, load_contract, live_contract_id) and never import dynamically or
    relatively; the route does import the choke point."""
    for name in TRACKING_CODE:
        path = ROOT / name
        assert path.exists(), path
        assert _raw_identity_uses(path) == [], name
    route = (ROOT / TRACKING_CODE[0]).read_text(encoding="utf-8")
    assert "from ofo_app import tracked_contracts, tracking_store" in route


def test_the_choke_point_checks_the_live_holder_of_the_token():
    """The choke point itself prices nothing unless the live contract holding the token is the stored id: it calls
    catalogue_store.live_contract_id and compares the holder with the contract id."""
    source = (ROOT / "backend/ofo_app/tracked_contracts.py").read_text(encoding="utf-8")
    assert "from ofo_app.catalogue_store import CatalogueStoreError, StoredContract, live_contract_id, load_contract" \
        in source
    assert "holder != stored.contract_id" in source and 'return LIVE if holder == stored.contract_id' in source


@pytest.mark.parametrize("snippet", [
    "from ofo_app.catalogue_store import load_contract as lc\n",
    "from ofo_app import catalogue_store\n",
    "from . import catalogue_store\n",
    "import ofo_app.catalogue_store as c\n",
    "import importlib\n",
    "m = __import__('ofo_app.catalogue_store')\n",
    "key = f'{c.exchange_segment}:{c.exchange_token}'\n",
    "q = 'SELECT id FROM public.catalogue_contracts'\n",
])
def test_the_scan_fails_closed_on_every_bypass_shape(tmp_path, snippet):
    """Mutation check of the scan itself: each bypass shape is flagged."""
    path = tmp_path / "bypass.py"
    path.write_text(snippet, encoding="utf-8")
    assert _raw_identity_uses(path) != []


ORDER_PATH = ("backend/ofo/execution", "backend/ofo/orders", "backend/ofo_app/basket_post.py",
              "backend/ofo_app/checked_basket.py", "backend/ofo_app/execute_plan.py")


def test_ac1_no_order_path_module_imports_the_tracking_code():
    """REQ-109 AC-1/AC-2 (no account-wide switch, paper never mixed with real): the reverse direction - no module of
    the order path (execution, orders, the basket and execute-plan modules) imports ofo.tracking or
    ofo_app.tracking_store, so a paper entry cannot be read into an order. Every listed path must exist (a renamed
    module fails here, never passes silently)."""
    files = []
    for name in ORDER_PATH:
        path = ROOT / name
        assert path.exists(), path
        files += sorted(path.rglob("*.py")) if path.is_dir() else [path]
    offenders = []
    for path in files:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            names_tracking = "ofo.tracking" in stripped or "tracking_store" in stripped
            if stripped.startswith(("import ", "from ")) and names_tracking:
                offenders.append(f"{path.relative_to(ROOT)}: {stripped}")
    assert offenders == []
    assert len(files) > len(ORDER_PATH)  # the directories really held modules
