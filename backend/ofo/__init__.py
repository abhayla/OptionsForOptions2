"""OptionsForOptions2 backend (stack: ADR-043).

The runtime egress gate (REQ-073 AC-4, ``ofo.broker.egress``) is NOT installed by importing this package. It is
installed by the API's ``ofo_app.main.create_app`` (its lifespan refuses to start without it), by importing any Kite
door module (so every process that can reach Kite is gated), and by the test suites' conftest. Migrations, scripts
and dev programs that load no door are not gated, so they may run git, ruff or a database client.
"""
