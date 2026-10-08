"""API and database layer (ADR-043 stack). The domain package `ofo` never imports this package."""

# W-024 round 10: importing the app package installs the redacting log-record factory for every logger.
from ofo_app import redaction as _redaction  # noqa: E402,F401
