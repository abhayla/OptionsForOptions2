"""The runtime egress gate (REQ-073 AC-4, W-080 round 7; run-discipline B8: a structural guarantee, not a scan).

One ``sys.addaudithook`` hook, installed once when the ``ofo`` package is imported, sees every socket connect and
every process spawn that Python code makes, whatever library or spelling made it. It decides on the CALLER, not the
host (a ``socket.connect`` event carries only the resolved IP; measured on Python 3.13):

==========================================  ==========================================================================
connection kind                             what the gate does
==========================================  ==========================================================================
loopback (127.0.0.0/8, ::1, ::ffff:127.x)   allowed (local test fakes, a database tunnel, the dev servers)
unix socket (AF_UNIX)                       allowed (local only)
the configured database endpoint            allowed: ``_allow_endpoints`` is called ONCE by ``ofo_app`` at import with
                                            the database URLs from the environment (resolved once); later calls refused
inside a Kite door, after its URL check     allowed: the door sets ``_DOOR`` to a private sentinel only around the
                                            actual send/connect, and resets it in ``finally``
anything else (any other host, any         refused with ``EgressRefused`` BEFORE the packet leaves
library, raw socket, sendto/sendmsg)
an address family the gate cannot classify  refused (fail closed)
a process spawn (subprocess, os.system,     refused everywhere, door or not: a child process does not inherit the
os.exec*/spawn*/posix_spawn/fork/startfile, hook. Only the test suites' conftest may allow named programs
_winapi.CreateProcess)                      (``_enter_test_mode``); production never calls it
==========================================  ==========================================================================

Out of scope (ADR-003 Q235): code in the same process that deliberately changes this module's state, ctypes/cffi,
native-code event loops (uvloop; the Windows Proactor loop raises no connect event - the app refuses to start on
either, ``ofo_app.event_loop``). The private names here are reachable only by a literal ``_name``, which the source
scan (``tests/test_no_order_placement.py``) refuses outside the doors.

Standard library only (the domain layer imports no HTTP package and no app configuration).
"""
from __future__ import annotations

import contextlib
import contextvars
import ipaddress
import os
import socket
import sys
import threading
from collections.abc import Iterable, Iterator
from typing import Final
from urllib.parse import urlsplit


class EgressRefused(RuntimeError):
    """A connection or process the egress gate does not allow; nothing was sent or started.

    A RuntimeError, not an OSError, so no network library maps it to a retryable connect error."""


_SENTINEL: Final = object()
_DOOR: Final = contextvars.ContextVar("ofo_egress_door", default=None)

_CONNECT_EVENTS: Final = frozenset({"socket.connect", "socket.sendto", "socket.sendmsg"})
_SPAWN_EVENTS: Final = frozenset({"subprocess.Popen", "os.system", "os.exec", "os.spawn", "os.posix_spawn",
                                  "os.fork", "os.forkpty", "os.startfile", "_winapi.CreateProcess"})
_INET: Final = frozenset({socket.AF_INET, socket.AF_INET6})
_UNIX: Final = getattr(socket, "AF_UNIX", None)
_PENDING: Final = threading.local()  # test mode only: one allowed Popen -> its one CreateProcess

_state: dict[str, object] = {"installed": False, "endpoints": frozenset(), "sealed": False, "programs": frozenset(),
                             "test": False}


@contextlib.contextmanager
def _door() -> Iterator[None]:
    """Door context, for the Kite doors only, AFTER their URL check and only around the send/connect itself."""
    token = _DOOR.set(_SENTINEL)
    try:
        yield
    finally:
        _DOOR.reset(token)


def _in_door() -> bool:
    return _DOOR.get() is _SENTINEL


def _allow_endpoints(urls: Iterable[str]) -> None:
    """Called once, by ``ofo_app`` at import, with the database URLs. Every later call is refused."""
    if _state["sealed"]:
        raise EgressRefused("the egress endpoint list is already set; it is set once, at app import")
    allowed: set[tuple[str, int]] = set()
    for url in urls:
        parts = urlsplit(url)
        if not parts.hostname:
            continue
        port = parts.port or 5432
        allowed.add((parts.hostname, port))
        with contextlib.suppress(OSError):  # resolved once, here (no connection); unresolvable: only the name
            allowed.update((info[4][0], port) for info in socket.getaddrinfo(parts.hostname, port))
    _state["endpoints"] = frozenset(allowed)
    _state["sealed"] = True


def _enter_test_mode(programs: Iterable[str]) -> None:
    """Test suites only (their conftest): allow spawning exactly these programs (full paths or bare names), and let the
    doors take a test seam (a mock transport, an injected connect). Never called by production code."""
    _state["programs"] = frozenset(os.path.normcase(p) for p in programs)
    _state["test"] = True


def _test_mode() -> bool:
    return bool(_state["test"])


def _address_allowed(family: object, address: object) -> bool:
    if _UNIX is not None and family == _UNIX:
        return True
    if family not in _INET or not isinstance(address, tuple) or len(address) < 2:  # noqa: PLR2004
        return False  # fail closed: a family or address shape the gate cannot classify
    host, port = address[0], address[1]
    if not isinstance(host, str):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return (host, port) in _state["endpoints"]  # a host NAME: only the configured database name
    if ip.is_loopback or (isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None
                          and ip.ipv4_mapped.is_loopback):
        return True
    return (host, port) in _state["endpoints"]


def _first_token(line: str) -> str:
    if line.startswith('"'):
        return line[1:].split('"', 1)[0]
    return line.split(None, 1)[0] if line.split() else ""


def _program(args: tuple) -> str | None:
    """The program a ``subprocess.Popen`` event would run (on Windows ``args`` is already one command line)."""
    executable, argv = args[0], args[1]
    if executable:
        return os.fsdecode(executable)
    if isinstance(argv, (list, tuple)) and argv:
        return os.fsdecode(argv[0])
    if isinstance(argv, (str, bytes)) and sys.platform == "win32":
        return _first_token(os.fsdecode(argv)) or None
    return None  # a POSIX shell string or an unreadable shape: refused


def _spawn_allowed(event: str, args: tuple) -> bool:
    """Only in test mode, only a listed program. On Windows ``subprocess.Popen`` is followed by
    ``_winapi.CreateProcess`` (whose command line the audit event does not show): it is allowed once, right after an
    allowed Popen in the same thread, and refused otherwise."""
    programs = _state["programs"]
    if event == "_winapi.CreateProcess":
        pending, _PENDING.ok = getattr(_PENDING, "ok", False), False
        return bool(programs) and pending
    if not programs or event != "subprocess.Popen":
        return False
    program = _program(args)
    if program is None:
        return False
    name = os.path.normcase(program)
    _PENDING.ok = name in programs or os.path.basename(name) in programs
    return _PENDING.ok


def _hook(event: str, args: tuple) -> None:
    if event in _CONNECT_EVENTS:
        sock, address = args[0], args[1]
        if _in_door() or _address_allowed(getattr(sock, "family", None), address):
            return
        raise EgressRefused(f"{event} to {address!r} refused: only loopback, the database, or a Kite door after its "
                            "URL check may connect; nothing was sent")
    if event in _SPAWN_EVENTS and not _spawn_allowed(event, args):
        raise EgressRefused(f"{event} refused: the backend starts no process; nothing was started")


def install() -> None:
    """Install the hook once (idempotent). An audit hook cannot be removed."""
    if not _state["installed"]:
        sys.addaudithook(_hook)
        _state["installed"] = True


def installed() -> bool:
    return bool(_state["installed"])


__all__ = ["EgressRefused", "install", "installed"]
