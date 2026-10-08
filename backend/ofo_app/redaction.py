"""Log redaction for the API boundary (W-024 round 9 part 6 fix round, review MAJOR-3: never log request values).

Two rules, applied to the fully formatted record (message, arguments and traceback) before any handler sees it:
- key-based: the value after a secret-named key (`access_token=...`, `"password": "..."`) is replaced. The key list is
  the brief's (W-058's key-based redaction idea, written new here: W-058 is not on main yet).
- shape-based: any run of 20 or more token characters (letters, digits, `+ = _ -`) that holds both a letter and a
  digit, the shape of an API key, access token, checksum or base64/hex secret.
`RedactingFilter` rewrites the record in place: `msg` becomes the redacted text, `args` are dropped and the traceback
is formatted, redacted and stored as `exc_text` with `exc_info` cleared, so no later formatter can re-render a raw
value from the exception object.
"""

from __future__ import annotations

import logging
import re

SECRET_KEYS: tuple[str, ...] = (
    "access_token", "request_token", "refresh_token", "api_secret", "api_key", "password", "passwd", "pin", "otp",
    "totp", "checksum", "secret", "authorization", "enctoken",
)
REDACTED = "[REDACTED]"

_KEYED = re.compile(
    r"(?i)(?P<key>\b(?:" + "|".join(SECRET_KEYS) + r")\b)(?P<sep>['\"]?\s*[:=]\s*(?:bearer\s+|token\s+)?['\"]?)"
    r"(?P<value>[^\s'\",;&}\])]+)"
)
_RUN = re.compile(r"[A-Za-z0-9+=_\-]{20,}")


def _shape(match: re.Match[str]) -> str:
    run = match.group(0)
    return REDACTED if re.search(r"[A-Za-z]", run) and re.search(r"[0-9]", run) else run


def redact(text: str) -> str:
    """`text` with every secret-keyed value and every token-shaped run replaced by `[REDACTED]`."""
    text = _KEYED.sub(lambda m: m.group("key") + m.group("sep") + REDACTED, text)
    return _RUN.sub(_shape, text)


class RedactingFilter(logging.Filter):
    """Redacts a record's message, arguments and traceback in place; never drops a record."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # a broken format string: keep the template only, never the arguments
            message = str(record.msg)
        exc_text = record.exc_text
        if record.exc_info:
            exc_text = logging.Formatter().formatException(record.exc_info)
        record.msg = redact(message)
        record.args = ()
        record.exc_info = None
        record.exc_text = redact(exc_text) if exc_text else None
        if record.stack_info:
            record.stack_info = redact(record.stack_info)
        return True


#: Loggers that can carry a request's exception: the boundary's own, and the server's (uvicorn logs any exception
#: that escapes the app; the boundary middleware stops that, and the filter is the second layer).
GUARDED_LOGGERS: tuple[str, ...] = ("ofo_app.main", "ofo_app", "uvicorn.error", "uvicorn.access", "fastapi")


def install_redaction() -> None:
    for name in GUARDED_LOGGERS:
        logger = logging.getLogger(name)
        if not any(isinstance(f, RedactingFilter) for f in logger.filters):
            logger.addFilter(RedactingFilter())
