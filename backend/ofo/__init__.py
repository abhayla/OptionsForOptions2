"""OptionsForOptions2 backend (stack: ADR-043).

The runtime egress gate (REQ-073 AC-4, ``ofo.broker.egress``) is NOT installed by importing this package: the API
process installs it in ``ofo_app.main.create_app`` before the app is built (its lifespan refuses to start without it),
and the test suites' conftest installs it the same way. Migrations, scripts and dev programs that import ``ofo`` are
not gated, so they may run git, ruff or a database client.
"""
