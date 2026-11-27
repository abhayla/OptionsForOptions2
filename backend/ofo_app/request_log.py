"""One INFO line per HTTP request: method, route template, status, milliseconds (request start to response start).

Pure ASGI (not BaseHTTPMiddleware): the body is never buffered, so streaming/SSE responses are logged at their
response start. WebSocket and lifespan scopes pass through untouched. The route is the matched template
(scope["route"].path, e.g. /api/paper/strategies/{strategy_id}), so no ids, query strings or tokens reach the log;
without a matched route the raw path is logged with no query string. No await on I/O; one logging call.
"""

from __future__ import annotations

import logging
import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

log = logging.getLogger("ofo_app.request")


class RequestLog:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        t0 = time.perf_counter()
        logged = False

        def emit(status: int) -> None:
            nonlocal logged
            if logged:
                return
            logged = True
            route = scope.get("route")
            path = getattr(route, "path", None) or scope.get("path", "")
            log.info("request %s %s %d %.1fms", scope.get("method", ""), path, status,
                     (time.perf_counter() - t0) * 1000.0)

        async def logging_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                emit(int(message["status"]))
            await send(message)

        try:
            await self.app(scope, receive, logging_send)
        except Exception:
            emit(500)
            raise
