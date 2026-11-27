"""One INFO line per HTTP request: method, route template, status, milliseconds (request start to response start).

Pure ASGI (not BaseHTTPMiddleware): the body is never buffered, so streaming/SSE responses are logged at their
response start. WebSocket and lifespan scopes pass through untouched. The route is the matched template
(scope["route"].path, e.g. /api/paper/strategies/{strategy_id}), so no ids, query strings or tokens reach the log;
without a matched route the raw path is logged with no query string. No await on I/O; one logging call.
"""

from __future__ import annotations

import logging
import sys
import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ofo_app import step_timing

log = logging.getLogger("ofo_app.request")


def _install_handler() -> None:
    """The API runs under `uvicorn --factory` with no logging config, so the root stays at WARNING and an INFO record
    would be dropped. This one logger gets its own stderr handler (once) and does not propagate (no double print)."""
    log.setLevel(logging.INFO)
    log.propagate = False
    if not any(getattr(h, "_ofo_request_log", False) for h in log.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        handler._ofo_request_log = True  # type: ignore[attr-defined]
        log.addHandler(handler)


_install_handler()


def _steps_text(elapsed_ms: float) -> str:
    """` db=120.3ms/14q price=5000.1ms margin=800.0ms compute=276.6ms`; absent steps are omitted (a request with no
    step at all adds nothing, so the old line is unchanged). compute = total - db - price - margin, floored at 0:
    gathered steps can overlap, so the parts may add up to more than the total."""
    snap = step_timing.snapshot()
    if not snap:
        return ""
    parts = []
    if "db" in snap:
        parts.append(f"db={snap['db'][0]:.1f}ms/{snap['db'][1]}q")
    parts.extend(f"{name}={snap[name][0]:.1f}ms" for name in ("price", "margin") if name in snap)
    spent_ms = sum(snap[name][0] for name in snap)
    rest_ms = max(0.0, elapsed_ms - spent_ms)
    parts.append(f"compute={rest_ms:.1f}ms")
    return " " + " ".join(parts)


class RequestLog:
    def __init__(self, app: ASGIApp) -> None:
        self.inner = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.inner(scope, receive, send)
            return
        t0 = time.perf_counter()
        logged = False
        token = step_timing.start()

        def emit(status: int) -> None:
            nonlocal logged
            if logged:
                return
            logged = True
            route = scope.get("route")
            path = getattr(route, "path", None) or scope.get("path", "")
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            # the step text joins the format string (no % in it), so the args stay (method, path, status, ms)
            fmt = "request %s %s %d %.1fms" + _steps_text(elapsed_ms)
            log.info(fmt, scope.get("method", ""), path, status, elapsed_ms)

        async def logging_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                emit(int(message["status"]))
            await send(message)

        try:
            await self.inner(scope, receive, logging_send)
        except Exception:
            emit(500)
            raise
        finally:
            step_timing.stop(token)
