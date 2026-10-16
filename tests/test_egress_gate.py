"""W-080 round 7 (REQ-073 AC-4): the runtime egress gate ``ofo.broker.egress``, proven with planted REAL calls.

Verifier END CONDITION: "A fresh module in ordinary Python, using any import route, any client, or any public or private attribute with a literal name, that opens a non-loopback connection or reaches POST /orders* is refused at runtime, or flagged by the scan. Out of scope, and noted only: ctypes/cffi, computed-name reflection (getattr(x, '_'+s), gc), changing the hook's state, and native-code event loops."

Every planted bypass is a real call aimed at TEST-NET address 192.0.2.1 (RFC 5737, never routed, never Kite) and
expects ``EgressRefused``: the gate raises inside the ``socket.connect`` / spawn audit event, BEFORE any packet leaves.
With the gate disabled each one would instead try the network (and time out or fail differently), so each is red.
This file is standard library only (the kit CI); the httpx / websocket bypasses are in
``tests_app/test_egress_gate_doors.py``.
"""
from __future__ import annotations

import http.client
import socket
import ssl
import subprocess
import sys
import urllib  # noqa: F401  (r5: the bare package import route)
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from ofo.broker import egress  # noqa: E402
from ofo.broker.egress import EgressRefused  # noqa: E402

TEST_NET = "192.0.2.1"
BACKEND = Path(__file__).resolve().parents[1] / "backend"


def _fresh(code: str) -> list[str]:
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60, cwd=BACKEND)
    assert out.returncode == 0, out.stderr
    return out.stdout.split()


def test_the_gate_is_installed_by_importing_ofo_in_a_fresh_process() -> None:
    code = ("import socket, ofo\nfrom ofo.broker import egress\nprint(egress.installed())\n"
            f"try:\n    socket.create_connection(('{TEST_NET}', 443), timeout=2)\n"
            "except egress.EgressRefused:\n    print('refused')\n")
    assert _fresh(code) == ["True", "refused"]


# -- planted bypasses (stdlib routes) --------------------------------------------------------------------------------

def test_r1_a_spelling_the_old_scan_missed() -> None:
    """``os.sys.modules[...]``: the old import scan banned ``sys.modules`` only on a name bound to ``sys``."""
    import os
    raw = os.sys.modules["socket"]
    with pytest.raises(EgressRefused):
        raw.create_connection((TEST_NET, 443), timeout=2)


def test_r4_percent_encoded_host_from_a_non_door_module() -> None:
    import urllib.request as request  # a non-door module; urllib resolves the %2E host to the TEST-NET address
    with pytest.raises(EgressRefused):
        request.urlopen("https://192%2E0%2E2%2E1/orders/regular", data=b"x", timeout=2)


def test_r5_bare_urllib_then_request_urlopen() -> None:
    import urllib.request  # noqa: F401 - make sure the submodule is loaded; the call below uses the bare package name
    with pytest.raises(EgressRefused):
        urllib.request.urlopen(f"https://{TEST_NET}/orders/regular", data=b"x", timeout=2)


def test_r5_http_client() -> None:
    conn = http.client.HTTPSConnection(TEST_NET, 443, timeout=2)
    with pytest.raises(EgressRefused):
        conn.request("POST", "/orders/regular", body=b"x")


def test_r5_raw_socket_and_ssl() -> None:
    with pytest.raises(EgressRefused):
        raw = socket.create_connection((TEST_NET, 443), timeout=2)
        ssl.create_default_context().wrap_socket(raw, server_hostname="x").sendall(b"POST /orders/regular")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(EgressRefused):
            s.connect((TEST_NET, 443))
        with pytest.raises(EgressRefused):
            s.connect_ex((TEST_NET, 443))
    finally:
        s.close()


def test_r5_sys_modules_lookup() -> None:
    with pytest.raises(EgressRefused):
        sys.modules["socket"].create_connection((TEST_NET, 443), timeout=2)


def test_udp_sendto_is_refused() -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        with pytest.raises(EgressRefused):
            s.sendto(b"POST /orders/regular", (TEST_NET, 53))
    finally:
        s.close()


def test_a_process_spawn_is_refused() -> None:
    """A child process does not inherit the hook, so spawning is refused, even here in test mode (only this Python
    and git are allowed, for the suite's own script tests)."""
    import os
    with pytest.raises(EgressRefused):
        subprocess.run(["curl", "-X", "POST", f"https://{TEST_NET}/orders/regular"], timeout=5)
    with pytest.raises(EgressRefused):
        subprocess.run(f"curl https://{TEST_NET}/orders/regular", shell=True, timeout=5)
    with pytest.raises(EgressRefused):
        os.system(f"curl https://{TEST_NET}/orders/regular")


def test_outside_test_mode_even_this_python_cannot_be_spawned(monkeypatch) -> None:
    monkeypatch.setitem(egress._state, "programs", frozenset())
    with pytest.raises(EgressRefused):
        subprocess.run([sys.executable, "-c", "pass"], timeout=30)


# -- what the gate allows, and the shapes it cannot classify ---------------------------------------------------------

def test_a_loopback_connect_is_allowed() -> None:
    server = socket.create_server(("127.0.0.1", 0))
    try:
        client = socket.create_connection(server.getsockname(), timeout=2)  # no EgressRefused
        client.close()
    finally:
        server.close()


class _Sock:
    def __init__(self, family: object) -> None:
        self.family = family


@pytest.mark.parametrize("family, address", [
    (12345, (TEST_NET, 443)),                        # an address family the gate does not know
    (socket.AF_INET, TEST_NET),                      # an address shape it cannot read
    (socket.AF_INET, (b"192.0.2.1", 443)),
    (socket.AF_INET, ("127.1", 443)),                # not a plain IP literal: not treated as loopback
    (socket.AF_INET6, ("::ffff:192.0.2.1", 443, 0, 0)),
    (socket.AF_INET, ("api.kite.trade", 443)),       # a host name that is not the configured database
])
def test_shapes_the_gate_cannot_classify_are_refused(family: object, address: object) -> None:
    with pytest.raises(EgressRefused):
        egress._hook("socket.connect", (_Sock(family), address))


@pytest.mark.parametrize("address", [("127.0.0.1", 5432), ("::1", 5432, 0, 0), ("::ffff:127.0.0.1", 5432, 0, 0)])
def test_loopback_shapes_are_allowed(address: tuple) -> None:
    family = socket.AF_INET6 if ":" in address[0] else socket.AF_INET
    egress._hook("socket.connect", (_Sock(family), address))


def test_door_context_allows_and_is_reset() -> None:
    with egress._door():
        egress._hook("socket.connect", (_Sock(socket.AF_INET), (TEST_NET, 443)))
    assert not egress._in_door()
    with pytest.raises(EgressRefused):
        egress._hook("socket.connect", (_Sock(socket.AF_INET), (TEST_NET, 443)))


def test_the_database_endpoint_is_set_once_in_a_fresh_process() -> None:
    code = ("import socket, ofo\nfrom ofo.broker import egress as e\n"
            f"e._allow_endpoints(['postgresql+asyncpg://example@{TEST_NET}:5432/db'])\n"
            f"print(e._address_allowed(socket.AF_INET, ('{TEST_NET}', 5432)), "
            f"e._address_allowed(socket.AF_INET, ('{TEST_NET}', 443)))\n"
            "try:\n    e._allow_endpoints(['postgresql://example@203.0.113.1:443/x'])\n"
            "except e.EgressRefused:\n    print('sealed')\n")
    assert _fresh(code) == ["True", "False", "sealed"]


@pytest.mark.parametrize("module", ["ofo.broker.kite_http"])
def test_public_names_equal_all(module: str) -> None:
    """A door re-exports nothing by accident (round 6 found ``from ofo_app.kite_http import httpx``)."""
    mod = __import__(module, fromlist=["_"])
    public = {n for n, v in vars(mod).items() if not n.startswith("_") and type(v).__name__ != "module"}
    assert public - {"annotations"} == set(mod.__all__)
