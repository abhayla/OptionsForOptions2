"""REQ-054 AC-2 (W-131): "Only the Zerodha implementation exists in V1; no unused broker implementations are built."

An ALLOW-LIST, discovered from the source tree, not a list of forbidden broker names (finding
``guard-as-forbidden-list``) and failing closed (standing item c):

* every ``.py`` under ``backend/`` is parsed; one that does not parse is a finding (a module we cannot read cannot be
  classified);
* a module is a *Kite* module when a part of its path names Kite or Zerodha; the set of them must equal ``KITE_MODULES``
  exactly: a new Zerodha module is a deliberate edit of this list, a module named for any other broker (or any module
  we cannot place) breaks it;
* a module that carries a web address may carry only a Zerodha host (``ZERODHA_HOSTS``);
* a class that has the ``BrokerReader`` method shape (3 of its 4 methods) is a broker implementation whatever its module
  is called, and must be exactly ``KiteBrokerReader``.

A module whose path names a broker (``BROKERISH``: the word "broker" or another broker's name) is allowed only when it
is a Kite/Zerodha module or on ``NEUTRAL_BROKER_NAMED`` (the generic broker plumbing that exists today). The scratch
cases below prove each rule goes red.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Final

import pytest

pytestmark = pytest.mark.repo_scan

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"

#: The Zerodha/Kite modules (relative to ``backend/``): the whole of REQ-054 AC-2's "only the Zerodha implementation".
KITE_MODULES: Final = frozenset({
    "ofo/broker/kite_auth.py", "ofo/broker/kite_flags.py", "ofo/broker/kite_endpoints.py", "ofo/broker/kite_http.py",
    "ofo/marketdata/kite_frames.py", "ofo/marketdata/kite_provider.py",
    "ofo_app/eligibility_from_zerodha.py", "ofo_app/kite_broker_reader.py", "ofo_app/kite_client.py",
    "ofo_app/kite_history.py", "ofo_app/kite_http.py", "ofo_app/kite_margin.py", "ofo_app/kite_reads.py",
    "ofo_app/kite_replies.py", "ofo_app/kite_ws.py",
})
#: Generic broker plumbing that names no vendor (session state, tokens, config, the egress gate, routes).
NEUTRAL_BROKER_NAMED: Final = frozenset({
    "ofo/broker/__init__.py", "ofo/broker/flags.py", "ofo/broker/egress.py", "ofo/broker/session.py",
    "ofo_app/alembic/versions/0004_broker_instruments.py", "ofo_app/alembic/versions/0007_broker_sessions.py",
    "ofo_app/alembic/versions/0015_audit_broker_allowlist.py", "ofo_app/broker_config.py", "ofo_app/broker_crypto.py",
    "ofo_app/broker_sync.py", "ofo_app/broker_token_store.py", "ofo_app/routes/broker.py",
    "ofo_app/routes/broker_capabilities.py", "ofo_app/routes/broker_status.py",
})
VENDOR_PARTS: Final = ("kite", "zerodha")
BROKERISH: Final = re.compile(r"broker|upstox|angel|fyers|dhan|groww|paytm|icici|"
                              r"kotak|motilal|5paisa|shoonya|finvasia|flattrade|aliceblue|iifl|openalgo|smartapi",
                              re.IGNORECASE)
ZERODHA_HOSTS: Final = frozenset({"api.kite.trade", "kite.trade", "kite.zerodha.com", "zerodha.com", "ws.kite.trade"})
HOST: Final = re.compile(r"(?:https?|wss?)://([A-Za-z0-9.-]+)")
READER_METHODS: Final = frozenset({"fetch_positions", "fetch_order_statuses", "fetch_available_margin",
                                   "fetch_required_margin"})
READER_SHAPE_MIN: Final = 3
MIN_FILES: Final = 100  # the real tree is ~300 modules; fewer means the wrong folder was read
THE_READER: Final = ("ofo_app/kite_broker_reader.py", "KiteBrokerReader")


def _hosts(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.update(m.group(1).lower() for m in HOST.finditer(node.value))
    return found


def _is_protocol(node: ast.ClassDef) -> bool:
    return any(isinstance(b, ast.Name) and b.id == "Protocol" for b in node.bases)


def _reader_classes(tree: ast.AST) -> list[str]:
    """Classes with the reader shape, the interface itself (a ``Protocol``: no implementation) apart."""
    return [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and not _is_protocol(n)
            and len(READER_METHODS & {f.name for f in n.body if isinstance(f, ast.FunctionDef | ast.AsyncFunctionDef)})
            >= READER_SHAPE_MIN]


def findings(files: list[tuple[str, str]]) -> list[str]:
    """What breaks REQ-054 AC-2 in ``files`` (``(path relative to backend/, source)`` pairs). Empty = holds."""
    out: list[str] = []
    kite_found: set[str] = set()
    for rel, source in files:
        lowered = rel.lower()
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError):
            out.append(f"{rel}: does not parse, so it cannot be classified (fail closed)")
            continue
        if any(v in lowered for v in VENDOR_PARTS):
            kite_found.add(rel)
        elif BROKERISH.search(lowered) and rel not in NEUTRAL_BROKER_NAMED:
            out.append(f"{rel}: a broker-looking module that is neither Zerodha/Kite nor generic broker plumbing")
        out.extend(f"{rel}: web address of {h}: only Zerodha hosts are allowed"
                   for h in sorted(_hosts(tree) - ZERODHA_HOSTS))
        out.extend(f"{rel}: class {c} implements the broker reader shape; only {THE_READER[1]} may"
                   for c in _reader_classes(tree) if (rel, c) != THE_READER)
    # the exact-set check runs on a whole tree only (a scratch file list would trivially miss the real modules)
    return out + _set_findings(kite_found, files)


def _set_findings(kite_found: set[str], files: list[tuple[str, str]]) -> list[str]:
    if not any(rel in KITE_MODULES for rel, _ in files):
        return []  # a scratch list that holds none of the real modules: only per-file rules apply
    return [f"Kite module set differs: extra {sorted(kite_found - KITE_MODULES)}, missing "
            f"{sorted(KITE_MODULES - kite_found)}"] if kite_found != KITE_MODULES else []


def real_tree() -> list[tuple[str, str]]:
    return [(p.relative_to(BACKEND).as_posix(), p.read_text(encoding="utf-8")) for p in sorted(BACKEND.rglob("*.py"))]


def test_ac2_the_source_tree_has_only_the_zerodha_broker_implementation() -> None:
    """AC-2: discovered from the real tree: the Kite modules equal the list, every other module is neutral, every web
    address is Zerodha's, and exactly one class has the BrokerReader shape: KiteBrokerReader."""
    files = real_tree()
    assert len(files) > MIN_FILES  # the scan really read the tree
    assert findings(files) == []
    assert [(rel, c) for rel, src in files for c in _reader_classes(ast.parse(src))] == [THE_READER]


@pytest.mark.parametrize("rel", ["ofo_app/upstox_reader.py", "ofo/broker/angelone_x.py",
                                 "ofo_app/fyers_client.py", "ofo_app/dhan.py", "ofo/broker/groww.py",
                                 "ofo_app/some_new_broker_thing.py", "ofo_app/Upstox_X.py"])
def test_ac2_a_module_named_like_another_broker_turns_it_red(rel: str) -> None:
    """AC-2 attack 6: a scratch module named for another broker (or any broker-looking word) is a finding."""
    assert findings([*real_tree(), (rel, "x = 1\n")])


def test_ac2_a_module_with_an_innocent_name_but_another_brokers_address_turns_it_red() -> None:
    """AC-2: the name is not the only road in: a web address of another broker is found by its content."""
    bad = [("ofo_app/orders_helper.py", 'URL = "https://api.upstox.com/v2/user/profile"\n')]
    assert findings([*real_tree(), *bad])
    assert findings([("ofo_app/orders_helper.py", 'U = "wss://stream.angelone.in/x"\n')])


def test_ac2_a_class_with_the_reader_shape_in_any_module_turns_it_red() -> None:
    """AC-2: a second BrokerReader implementation under an innocent module name is found by its shape."""
    src = ("class Sneaky:\n    def fetch_positions(self, s): ...\n    def fetch_order_statuses(self, s): ...\n"
           "    def fetch_available_margin(self): ...\n")
    assert findings([*real_tree(), ("ofo_app/helpers.py", src)])
    assert findings([("ofo_app/helpers.py", src.replace("class Sneaky", "async def x(): ...\nclass Sneaky"))])


def test_ac2_an_unparseable_module_fails_closed() -> None:
    """AC-2 attack 6 / standing item (c): a module that does not parse cannot be classified, so it is a finding."""
    assert findings([*real_tree(), ("ofo_app/whatever.py", "def broken(:\n")])
    assert findings([("ofo_app/whatever.py", "x = '\x00'\n")])


def test_ac2_a_new_kite_named_module_or_a_missing_one_breaks_the_exact_set() -> None:
    """AC-2: the Kite module list is exact: a new kite_* module needs a deliberate edit; a vanished one is noticed."""
    assert findings([*real_tree(), ("ofo_app/kite_new_thing.py", "x = 1\n")])
    assert findings([f for f in real_tree() if f[0] != "ofo_app/kite_ws.py"])


def test_ac2_only_zerodha_hosts_are_allowed_in_the_allow_list_itself() -> None:
    """AC-2: the allow-list of hosts names Zerodha's hosts and nothing else (a widened list is a reviewed edit)."""
    assert {"api.kite.trade", "kite.trade", "kite.zerodha.com", "zerodha.com", "ws.kite.trade"} == ZERODHA_HOSTS
