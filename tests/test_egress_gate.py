"""W-080 round 7 (REQ-073 AC-4): the runtime egress gate ``ofo.broker.egress``, proven with planted REAL calls.

Verifier END CONDITION: "A fresh module in ordinary Python, using any import route, any client, or any public or private attribute with a literal name, that opens a non-loopback connection or reaches POST /orders* is refused at runtime, or flagged by the scan. Out of scope, and noted only: ctypes/cffi, computed-name reflection (getattr(x, '_'+s), gc), changing the hook's state, and native-code event loops."

Every planted bypass is a real call aimed at TEST-NET address 192.0.2.1 (RFC 5737, never routed, never Kite) and
expects ``EgressRefused``: the gate raises inside the ``socket.connect`` / spawn audit event, BEFORE any packet leaves.
With the gate disabled each one would instead try the network (and time out or fail differently), so each is red.
This file is standard library only (the kit CI); the httpx / websocket bypasses are in
``tests_app/test_egress_gate_doors.py``.
"""  # noqa: E501
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

from ofo.broker import egress
from ofo.broker.egress import EgressRefused
from ofo.broker.kite_endpoints import CALLER_KITE_READS

TEST_NET = "192.0.2.1"
BACKEND = Path(__file__).resolve().parents[1] / "backend"


def _fresh(code: str) -> list[str]:
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60, cwd=BACKEND)  # noqa: PLW1510, S603
    assert out.returncode == 0, out.stderr
    return out.stdout.split()


def test_importing_ofo_alone_does_not_gate_a_tool_process() -> None:
    """W-080 integration: migrations, scripts and dev programs import ``ofo`` and must be free to run git or ruff; only
    the API process (``create_app``, proven in tests_app/test_egress_gate_api_install.py) and the test suites install
    the gate. No connect is attempted here: ``installed()`` is read and a spawn of this Python is made."""
    code = ("import subprocess, sys, ofo\nfrom ofo.broker import egress\nprint(egress.installed())\n"
            "out = subprocess.run([sys.executable, '-c', 'print(1)'], capture_output=True, text=True)\n"
            "print(out.stdout.strip())\n")
    assert _fresh(code) == ["False", "1"]


def test_importing_the_urllib_kite_door_gates_a_fresh_process() -> None:
    """Review MAJOR (W-080 integration): every process that can reach Kite imports a door, and importing a door
    installs the gate, so a Kite-capable process that never calls create_app (history_finalize) is still gated."""
    code = ("import socket, subprocess, sys\nimport ofo.broker.kite_http\nfrom ofo.broker import egress\n"
            "print(egress.installed())\n"
            f"try:\n    socket.create_connection(('{TEST_NET}', 443), timeout=2)\n"
            "except egress.EgressRefused:\n    print('connect-refused')\n"
            "try:\n    subprocess.run([sys.executable, '-c', 'pass'])\n"
            "except egress.EgressRefused:\n    print('spawn-refused')\n")
    assert _fresh(code) == ["True", "connect-refused", "spawn-refused"]


def test_install_the_way_the_app_does_gates_a_fresh_process() -> None:
    """The same ``install()`` call ``create_app`` makes: a connect to TEST-NET and a process start are both refused."""
    code = ("import socket, subprocess, sys\nfrom ofo.broker import egress\n"
            "egress.install()\nprint(egress.installed())\n"
            f"try:\n    socket.create_connection(('{TEST_NET}', 443), timeout=2)\n"
            "except egress.EgressRefused:\n    print('connect-refused')\n"
            "try:\n    subprocess.run([sys.executable, '-c', 'pass'])\n"
            "except egress.EgressRefused:\n    print('spawn-refused')\n")
    assert _fresh(code) == ["True", "connect-refused", "spawn-refused"]


# -- planted bypasses (stdlib routes) --------------------------------------------------------------------------------

def test_r1_a_spelling_the_old_scan_missed() -> None:
    """``os.sys.modules[...]``: the old import scan banned ``sys.modules`` only on a name bound to ``sys``."""
    import os  # noqa: PLC0415
    raw = os.sys.modules["socket"]
    with pytest.raises(EgressRefused):
        raw.create_connection((TEST_NET, 443), timeout=2)


def test_r4_percent_encoded_host_from_a_non_door_module() -> None:
    import urllib.request as request  # a non-door module; urllib resolves the %2E host to the TEST-NET address  # noqa: PLC0415, PLR0402
    with pytest.raises(EgressRefused):
        request.urlopen("https://192%2E0%2E2%2E1/orders/regular", data=b"x", timeout=2)


def test_r5_bare_urllib_then_request_urlopen() -> None:
    import urllib.request  # noqa: PLC0415
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


_NEEDS_SENDMSG = pytest.mark.skipif(not hasattr(socket.socket, "sendmsg"),
                                    reason="no socket.sendmsg on this OS (Windows)")


def _loopback_pair():
    server = socket.create_server(("127.0.0.1", 0))
    client = socket.create_connection(server.getsockname(), timeout=2)
    conn, _ = server.accept()
    conn.settimeout(2)
    return server, client, conn


@_NEEDS_SENDMSG
def test_sendmsg_without_address_on_a_connected_loopback_socket_is_allowed() -> None:
    server, client, conn = _loopback_pair()
    try:
        client.sendmsg([b"hello"])  # the Linux asyncio write shape; raised EgressRefused before the fix
        assert conn.recv(10) == b"hello"
    finally:
        client.close()
        conn.close()
        server.close()


def test_hook_allows_sendmsg_and_sendto_none_on_a_connected_socket() -> None:
    server, client, conn = _loopback_pair()
    try:
        egress._hook("socket.sendmsg", (client, None))
        egress._hook("socket.sendto", (client, None))
    finally:
        client.close()
        conn.close()
        server.close()


@_NEEDS_SENDMSG
def test_sendmsg_without_address_on_an_unconnected_udp_socket_sends_nothing() -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    listener.bind(("127.0.0.1", 0))
    listener.settimeout(0.3)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        with pytest.raises((EgressRefused, OSError)):
            s.sendmsg([b"x"])
        with pytest.raises(socket.timeout):
            listener.recv(10)
        with pytest.raises(EgressRefused):
            egress._hook("socket.sendmsg", (s, None))
    finally:
        s.close()
        listener.close()


@_NEEDS_SENDMSG
def test_sendmsg_with_an_address_to_a_foreign_host_is_refused() -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        with pytest.raises(EgressRefused):
            s.sendmsg([b"x"], [], 0, (TEST_NET, 53))
    finally:
        s.close()


def test_a_subclass_faking_getpeername_is_refused() -> None:
    class Liar(socket.socket):
        def getpeername(self):
            return ("127.0.0.1", 5432)

    s = Liar(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        with pytest.raises(EgressRefused):
            egress._hook("socket.sendmsg", (s, None))
    finally:
        s.close()


def test_a_non_socket_object_with_no_address_is_refused() -> None:
    with pytest.raises(EgressRefused):
        egress._hook("socket.sendmsg", (_Sock(socket.AF_INET), None))


def test_connect_with_no_address_is_still_refused() -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(EgressRefused):
            egress._hook("socket.connect", (s, None))
    finally:
        s.close()


def test_a_foreign_connect_is_refused_and_leaves_no_peer() -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(EgressRefused):
            s.connect((TEST_NET, 443))
        with pytest.raises(OSError):
            s.getpeername()
    finally:
        s.close()


def test_a_process_spawn_is_refused() -> None:
    """A child process does not inherit the hook, so spawning is refused, even here in test mode (only this Python
    and git are allowed, for the suite's own script tests)."""
    import os  # noqa: PLC0415
    with pytest.raises(EgressRefused):
        subprocess.run(["curl", "-X", "POST", f"https://{TEST_NET}/orders/regular"], timeout=5)  # noqa: PLW1510, S603, S607
    with pytest.raises(EgressRefused):
        subprocess.run(f"curl https://{TEST_NET}/orders/regular", shell=True, timeout=5)  # noqa: PLW1510, S602
    with pytest.raises(EgressRefused):
        os.system(f"curl https://{TEST_NET}/orders/regular")  # noqa: S605


def test_outside_test_mode_even_this_python_cannot_be_spawned(monkeypatch) -> None:
    monkeypatch.setitem(egress._state, "programs", frozenset())
    with pytest.raises(EgressRefused):
        subprocess.run([sys.executable, "-c", "pass"], timeout=30)  # noqa: PLW1510


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


# -- W-080 round 8: a door refuses every host that is not Kite's, before door context ----------------------------------

_NON_KITE = "192.0.2.1"  # TEST-NET, never routed


@pytest.fixture
def door_entries(monkeypatch) -> list[int]:
    """Counts every entry into door context; a refusal must leave it empty (zero connect attempts)."""
    import contextlib
    entries: list[int] = []

    @contextlib.contextmanager
    def counting():
        entries.append(1)
        yield

    monkeypatch.setattr(egress, "_door", counting)
    return entries


@pytest.mark.parametrize(("method", "url"), [("POST", f"http://{_NON_KITE}/orders/regular"),
                                             ("GET", f"http://{_NON_KITE}/"),
                                             ("GET", "https://example.com/instruments")])
def test_r8_check_call_refuses_every_non_kite_host(method: str, url: str) -> None:
    from ofo.broker.kite_http import KiteCallRefused, check_call
    with pytest.raises(KiteCallRefused):
        check_call(method, url, caller=CALLER_KITE_READS)


def test_r8_check_ws_url_refuses_a_non_kite_host() -> None:
    from ofo.broker.kite_http import KiteCallRefused, check_ws_url
    with pytest.raises(KiteCallRefused):
        check_ws_url(f"ws://{_NON_KITE}:80")


def test_r8_open_url_refuses_with_zero_door_entries(door_entries: list[int]) -> None:
    from ofo.broker.kite_http import KiteCallRefused, open_url
    with pytest.raises(KiteCallRefused):
        open_url(f"http://{_NON_KITE}/", caller=CALLER_KITE_READS)
    assert door_entries == []


def test_r8_loopback_is_allowed_only_in_test_mode(monkeypatch) -> None:
    from ofo.broker.kite_http import KiteCallRefused, check_call, check_ws_url
    check_call("GET", "http://127.0.0.1/x", caller=CALLER_KITE_READS)  # test mode is on in this suite
    check_ws_url("ws://127.0.0.1:8080")
    monkeypatch.setitem(egress._state, "test", False)
    with pytest.raises(KiteCallRefused):
        check_call("GET", "http://127.0.0.1/x", caller=CALLER_KITE_READS)
    with pytest.raises(KiteCallRefused):
        check_ws_url("ws://127.0.0.1:8080")
