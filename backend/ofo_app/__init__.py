"""API and database layer (ADR-043 stack). The domain package `ofo` never imports this package."""

# W-024 round 10: importing the app package installs the redacting log-record factory for every logger.
# W-080 round 7 (REQ-073 AC-4): the runtime egress gate allows the database endpoints named in the environment, set
# once here, before any engine is built (``ofo.broker.egress``; every later call is refused).
import os as _os

from ofo.broker import egress as _egress

from ofo_app import redaction as _redaction  # noqa: F401

_DB_URL_VARS = ("DATABASE_URL", "TEST_DATABASE_URL", "TEST_ADMIN_DATABASE_URL", "ALEMBIC_DATABASE_URL",
                "DEV_DATABASE_URL")
_egress._allow_endpoints(v for v in (_os.environ.get(n, "") for n in _DB_URL_VARS) if v.strip())
