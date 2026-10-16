---
work_item: W-081
ac: AC-1
requirement: REQ-055
ac_fp: "72546cbc045d"
result: pass
verified_by: "verifier (Sonnet, independent, Tier B, 2026-10-17 GC-2b)"
builder: "builder (Opus/Sonnet, PR #337, 2026-10-17)"
date: '2026-10-17'
commands: "python -m pytest -q -p no:cacheprovider tests/execution/test_margin_gate.py tests/execution/test_kite_basket.py tests/test_margin_from_zerodha_only.py tests/errors/test_write_allowlist.py; FRONTEND_ORIGIN=http://127.0.0.1:4173 python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_kite_margin_client.py tests_app/test_checked_basket.py; python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py; python -B -c <attack script using tests_app/test_checked_basket helpers> (main d61fcfb)"
---

AC: AC-1
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/execution/test_margin_gate.py tests/execution/test_kite_basket.py tests/test_margin_from_zerodha_only.py tests/errors/test_write_allowlist.py; FRONTEND_ORIGIN=http://127.0.0.1:4173 python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_kite_margin_client.py tests_app/test_checked_basket.py; python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py; python -B -c <attack script using tests_app/test_checked_basket helpers> (main d61fcfb)
observed: 289 passed; 76 passed; 967 passed, 4 skipped. The scan fails on any backend file other than basket.py and checked_basket.py naming build_basket or KiteBasket. Funds 68498.85 against the real condor reply built 4 orders; real funds 671.50 refused; Zerodha unreadable (either call) refused with 'could not confirm'; direct KiteBasket(()) raised TypeError; build_basket with a hand-made MarginVerdict, None, object() or dict as margin_source refused; a float-returning source refused; a KiteMargin subclass or a duck-typed client raised TypeError.
attack: Forged/hand-made verdict, direct constructor, lying source, missing source, Zerodha unreadable, negative funds (-1), zero funds, null funds field: all refused. Funds 68498.845 builds (ADR-101 paisa rounding, documented). Funds 68498.85000000001 builds (float noise rounded away).

Recorded by the orchestrator from the verifier's returned block.
