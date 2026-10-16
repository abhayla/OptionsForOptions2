"""OptionsForOptions2 backend (stack: ADR-043).

Importing the package installs the runtime egress gate (REQ-073 AC-4, ``ofo.broker.egress``) once, before any other
backend code runs: from then on only loopback, the configured database, and the Kite doors may connect.
"""
from ofo.broker import egress as _egress

_egress.install()
