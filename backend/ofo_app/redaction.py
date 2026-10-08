"""Log redaction at the ROOT of logging (W-024 round 10 item 1; issue 30 round-9 MAJOR 1: never log a secret).

The structural door is the log-record factory. `install_redaction()` sets `logging.setLogRecordFactory(RedactedRecord)`,
so every record built by any logger - any name, a child created later, one that does not propagate, one with its own
handler, and `logging.makeLogRecord` - IS a `RedactedRecord`. Round 9 filtered a fixed list of logger names, and a
logger filter does not apply to child loggers, so `ofo.execution.safety` logged raw tokens; there is no list here.

A `RedactedRecord` redacts every value written into it, whatever the path:
- at construction: each argument (a `str` is redacted; an `int`/`float`/`bool`/`None` stays; anything else becomes its
  redacted `str`), the message template, and the exception (formatted, redacted, stored as `exc_text`; `exc_info`
  cleared so no formatter can re-render the exception object);
- afterwards: attribute writes (`record.x = ...`) AND writes straight into `record.__dict__` (how `extra=` and
  `makeLogRecord` fill a record) go through the same redaction, because the record's `__dict__` is a redacting dict;
- formatting that raises (`"%d" % "text"`) returns the marker, never the raw arguments (fail closed).

What is redacted, by VALUE and by shape (`redact`):
- every secret value the process holds: those read from configuration at start-up (`SECRET_SETTINGS`) and those
  registered at run time (`register_secret`, e.g. the Kite access token handed to the market-data socket);
- the value after a secret-named key (`access_token=...`, `"password": "..."`);
- any run of 20 or more token characters holding both a letter and a digit: the shape of a Kite access token (32
  letters and digits), an api key, a checksum or a base64/hex secret.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from collections.abc import Mapping
from decimal import Decimal

SECRET_KEYS: tuple[str, ...] = (
    "access_token", "request_token", "refresh_token", "api_secret", "api_key", "password", "passwd", "pin", "otp",
    "totp", "checksum", "secret", "authorization", "enctoken",
)
REDACTED = "[REDACTED]"
#: Configuration entries whose VALUES are secrets; each one set in the environment is held from start-up.
SECRET_SETTINGS: tuple[str, ...] = (
    "KITE_API_KEY", "KITE_API_SECRET", "KITE_ACCESS_TOKEN", "KITE_TOKEN_CACHE_KEY", "DATABASE_URL",
    "TEST_DATABASE_URL", "TEST_ADMIN_DATABASE_URL",
)
#: A held value shorter than this is not used for value redaction (it would blank ordinary words); the shape and key
#: rules still apply. Every real Kite secret is 16 or more characters.
MIN_HELD_LENGTH = 6

_KEYED = re.compile(
    r"(?i)(?P<key>\b(?:" + "|".join(SECRET_KEYS) + r")\b)(?P<sep>['\"]?\s*[:=]\s*(?:bearer\s+|token\s+)?['\"]?)"
    r"(?P<value>[^\s'\",;&}\])]+)"
)
_RUN = re.compile(r"[A-Za-z0-9+=_\-]{20,}")

_held: tuple[str, ...] = ()
_held_lock = threading.Lock()


def register_secret(value: object) -> None:
    """Hold `value` as a secret: from now on it is redacted wherever it appears in a log record."""
    global _held
    if not isinstance(value, str) or len(value) < MIN_HELD_LENGTH:
        return
    with _held_lock:
        if value not in _held:
            _held = tuple(sorted((*_held, value), key=len, reverse=True))  # longest first: no partial overlap


def _shape(match: re.Match[str]) -> str:
    run = match.group(0)
    return REDACTED if re.search(r"[A-Za-z]", run) and re.search(r"[0-9]", run) else run


def redact(text: str) -> str:
    """`text` with every held secret value, every secret-keyed value and every token-shaped run replaced."""
    for value in _held:
        text = text.replace(value, REDACTED)
    text = _KEYED.sub(lambda m: m.group("key") + m.group("sep") + REDACTED, text)
    return _RUN.sub(_shape, text)


def _safe_str(value: object) -> str:
    try:
        return redact(str(value))
    except Exception:  # an object whose __str__ raises: never its repr
        return REDACTED


def _redact_arg(value: object) -> object:
    if value is None or type(value) in (int, float, bool, Decimal):
        return value
    return _safe_str(value)


def _redact_args(args: object) -> object:
    if isinstance(args, Mapping):
        return {k: _redact_arg(v) for k, v in args.items()}
    if isinstance(args, tuple):
        return tuple(_redact_arg(a) for a in args)
    return () if args is None else (_redact_arg(args),)


#: Record fields taken from the source code's location, never from data; left as they are so logs stay readable.
_CODE_FIELDS = frozenset({"pathname", "filename", "module", "funcName", "levelname", "levelno", "lineno", "created",
                          "msecs", "relativeCreated", "thread", "process"})


def _clean(key: object, value: object) -> object:
    """The value as it may be stored in a record under `key`."""
    if key in _CODE_FIELDS:
        return value
    if key == "args":
        return _redact_args(value)
    if key == "exc_info":
        return None  # converted to exc_text by RedactedRecord before it is stored
    if key == "msg":
        return _safe_str(value)
    if isinstance(value, str):
        return redact(value)
    return _redact_arg(value)


class _RedactingDict(dict):
    """A record's `__dict__`: every write, including `extra=` and `makeLogRecord`'s `__dict__.update`, is redacted."""

    def __setitem__(self, key, value):  # noqa: ANN001, ANN204
        if key == "exc_info" and value:
            dict.__setitem__(self, "exc_text", _format_exception(value))
        dict.__setitem__(self, key, _clean(key, value))

    def update(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN201
        for key, value in dict(*args, **kwargs).items():
            self[key] = value

    def setdefault(self, key, value=None):  # noqa: ANN001, ANN201
        if key not in self:
            self[key] = value
        return self[key]


def _format_exception(exc_info: object) -> str:
    try:
        if exc_info is True:
            return REDACTED
        if isinstance(exc_info, BaseException):
            exc_info = (type(exc_info), exc_info, exc_info.__traceback__)
        return redact(logging.Formatter().formatException(exc_info))  # type: ignore[arg-type]
    except Exception:
        return REDACTED


class RedactedRecord(logging.LogRecord):
    """Every log record of the process (installed as the record factory). See the module docstring."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        object.__setattr__(self, "__dict__", _RedactingDict())
        exc_info = args[6] if len(args) > 6 else kwargs.get("exc_info")
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        if exc_info:  # LogRecord.__init__ resets exc_text to None after storing exc_info
            dict.__setitem__(self.__dict__, "exc_text", _format_exception(exc_info))

    def __setattr__(self, name: str, value: object) -> None:
        self.__dict__[name] = value  # through the redacting dict

    def __setstate__(self, state: dict) -> None:  # copy/pickle (QueueHandler.prepare copies records)
        object.__setattr__(self, "__dict__", _RedactingDict())
        self.__dict__.update(state)

    def getMessage(self) -> str:  # noqa: N802 (logging's name)
        try:
            return redact(super().getMessage())
        except Exception:  # a broken format: the marker, never the arguments
            return f"{REDACTED} (log message could not be formatted)"


redacting_record_factory = RedactedRecord


def install_redaction() -> None:
    """Make every log record of the process a `RedactedRecord`, and hold the configured secret values. Idempotent."""
    for name in SECRET_SETTINGS:
        register_secret(os.environ.get(name))
    if logging.getLogRecordFactory() is not redacting_record_factory:
        logging.setLogRecordFactory(redacting_record_factory)


install_redaction()  # importing ofo_app (its package __init__ imports this module) is enough
