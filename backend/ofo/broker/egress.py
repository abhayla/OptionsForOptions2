"""The runtime egress gate (REQ-073 AC-4, W-080 round 7; run-discipline B8: a structural guarantee, not a scan).

One ``sys.addaudithook`` hook, installed once by the API process's entry point (``ofo_app.main.create_app``, before
the app is built and so before the first request; the lifespan refuses to start without it) and by the test suites'
conftest the same way, and by importing ANY Kite door module (``NETWORK_DOORS``), so every process that can reach Kite
is gated (``python -m ofo_app.history_finalize`` included). It sees every socket connect and every process spawn that
Python code makes, whatever library or spelling made it. Importing ``ofo`` alone does NOT install it: migrations,
scripts and dev programs that load no door are not gated (W-080 integration). The API has no switch to skip it: ``create_app``
calls ``install()`` unconditionally, and an audit hook cannot be removed. It decides on the CALLER, not the
host (a ``socket.connect`` event carries only the resolved IP; measured on Python 3.13):

==========================================  ==========================================================================
connection kind                             what the gate does
==========================================  ==========================================================================
loopback (127.0.0.0/8, ::1, ::ffff:127.x)   allowed (local test fakes, a database tunnel, the dev servers)
unix socket (AF_UNIX)                       allowed (local only)
the configured database endpoint            allowed: ``_allow_endpoints`` is called ONCE by ``ofo_app`` at import with
                                            the database URLs from the environment (resolved once); later calls refused
inside a Kite door, after its URL check     allowed only for the door's own call chain: the door's permission is a
                                            token (thread, asyncio task, nonce, door frame) live only around the send;
                                            the connect must come from that thread and task, the nonce must be live,
                                            and every frame between the connect and the door must be a trusted
                                            library (W-080 round 9), so caller code run inside it (a callback, a log
                                            handler, a trace function, a copied context, a task or thread started
                                            inside) gets nothing
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

import asyncio
import contextlib
import contextvars
import inspect
import ipaddress
import os
import selectors
import socket
import sys
import threading
from collections.abc import Iterable
from types import FrameType, ModuleType
from typing import Final, NamedTuple
from urllib.parse import urlsplit


class EgressRefused(RuntimeError):
    """A connection or process the egress gate does not allow; nothing was sent or started.

    A RuntimeError, not an OSError, so no network library maps it to a retryable connect error."""


class _Token(NamedTuple):
    thread: int
    task: object
    nonce: object
    frame: FrameType


_DOOR: Final = contextvars.ContextVar("ofo_egress_door", default=None)
_LIVE: Final[set[object]] = set()  # the nonces of the doors open right now; a nonce dies when its door closes
_MAX_DEPTH: Final = 400

_CONNECT_EVENTS: Final = frozenset({"socket.connect", "socket.sendto", "socket.sendmsg"})
_SPAWN_EVENTS: Final = frozenset({"subprocess.Popen", "os.system", "os.exec", "os.spawn", "os.posix_spawn",
                                  "os.fork", "os.forkpty", "os.startfile", "_winapi.CreateProcess"})
_INET: Final = frozenset({socket.AF_INET, socket.AF_INET6})
_UNIX: Final = getattr(socket, "AF_UNIX", None)
_PENDING: Final[dict[int, bool]] = {}  # test mode only, per thread id: one allowed Popen -> its one CreateProcess

_state: dict[str, object] = {"installed": False, "endpoints": frozenset(), "sealed": False, "programs": frozenset(),
                             "test": False}
#: files and package folders whose frames may sit between a door and its connect (the standard library's network
#: modules here; the doors add their own HTTP / websocket packages with ``_trust_modules`` at their import)
_TRUSTED: Final[set[str]] = set()


def _current_task() -> object:
    try:
        return asyncio.current_task()
    except RuntimeError:  # no running event loop in this thread
        return None


class _Door:
    """Door permission, for the Kite doors only, AFTER their URL check and only around the send/connect itself.

    The permission is bound to the frame that entered it (``with _egress._door():`` in a door function), the thread,
    the asyncio task, and a fresh nonce that dies on exit; nothing copied from it (a context, a task) is a door."""

    __slots__ = ("_reset", "_token")

    def __enter__(self) -> None:
        frame = inspect.currentframe().f_back  # the door function's frame, running the with statement
        token = _Token(threading.get_ident(), _current_task(), object(), frame)
        _LIVE.add(token.nonce)
        self._token = token
        self._reset = _DOOR.set(token)

    def __exit__(self, *exc: object) -> None:
        _LIVE.discard(self._token.nonce)
        _DOOR.reset(self._reset)
        del self._token


def _door() -> _Door:
    return _Door()


def _token_holds(token: object) -> bool:
    return (isinstance(token, _Token) and token.nonce in _LIVE and token.thread == threading.get_ident()
            and token.task is _current_task())


def _in_door() -> bool:
    return _token_holds(_DOOR.get())


def _trusted_file(filename: str) -> bool:
    name = os.path.normcase(os.path.abspath(filename))
    return any(name == t or name.startswith(t + os.sep) for t in _TRUSTED)


def _trust_modules(*modules: ModuleType | str) -> None:
    """Called by the doors at import with the library modules their sends run through (a package: its folder; a
    ``str``: that one file, the door's own ``__file__``)."""
    for module in modules:
        if isinstance(module, str):
            _TRUSTED.add(os.path.normcase(os.path.abspath(module)))
            continue
        path = os.path.normcase(os.path.abspath(module.__file__ or ""))
        _TRUSTED.add(os.path.dirname(path) if hasattr(module, "__path__") else path)


def _door_permits(frame: FrameType | None) -> bool:
    """True only when the live door token's own frame is reached from ``frame`` through trusted-library frames alone:
    no caller code (a callback, a log handler, a trace function, a ``__str__``) sits between the door and the connect,
    and the connect runs in the door's own thread and task (another task's or thread's stack never reaches it)."""
    token = _DOOR.get()
    if not _token_holds(token):
        return False
    for _ in range(_MAX_DEPTH):
        if frame is None:
            return False
        if frame is token.frame:
            return True
        if not _trusted_file(frame.f_code.co_filename):
            return False
        frame = frame.f_back
    return False


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
    thread = threading.get_ident()
    if event == "_winapi.CreateProcess":
        pending = _PENDING.pop(thread, False)  # consumed: a second CreateProcess needs a new allowed Popen
        return bool(programs) and pending
    _PENDING.pop(thread, None)  # every other spawn event clears this thread's entry: nothing stale survives it
    if not programs or event != "subprocess.Popen":
        return False
    program = _program(args)
    name = os.path.normcase(program) if program is not None else None
    allowed = name is not None and (name in programs or os.path.basename(name) in programs)
    if allowed:
        _PENDING[thread] = True
    return allowed


def _hook(event: str, args: tuple) -> None:
    if event in _CONNECT_EVENTS:
        sock, address = args[0], args[1]
        if _address_allowed(getattr(sock, "family", None), address) or _door_permits(inspect.currentframe().f_back):
            return
        raise EgressRefused(f"{event} to {address!r} refused: only loopback, the database, or a Kite door after its "
                            "URL check may connect; nothing was sent")
    if event in _SPAWN_EVENTS and not _spawn_allowed(event, args):
        raise EgressRefused(f"{event} refused: the backend starts no process; nothing was started")


def install() -> None:
    """Install the hook once (idempotent). An audit hook cannot be removed. Called by ``ofo_app.main.create_app`` (the
    API process), by every Kite door module at its import, and by the test suites' conftest; importing ``ofo`` alone
    does not call it."""
    if not _state["installed"]:
        _trust_modules(asyncio, contextlib, selectors, socket, __file__)  # the doors add their libraries
        sys.addaudithook(_hook)
        _state["installed"] = True


def installed() -> bool:
    return bool(_state["installed"])


__all__ = ["EgressRefused", "install", "installed"]
