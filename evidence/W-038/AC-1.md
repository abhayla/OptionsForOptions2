---
work_item: W-038
ac: AC-1
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/test_fixture_symbols.py tests/test_no_wall_clock_asserts.py; python -m pytest -q -p no:cacheprovider (full); python -c probes of wall_clock_asserts and _fstring_strike_violations on snippets"
---

AC: AC-1
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/test_fixture_symbols.py tests/test_no_wall_clock_asserts.py; python -m pytest -q -p no:cacheprovider (full); python -c probes of wall_clock_asserts and _fstring_strike_violations on snippets
observed: 10 passed (both guards); full suite 1297 passed in 140s; timeit/datetime-diff/alias/pc/constant shapes -> flagged; year<3000, len<LIMIT, obj.timeit -> []; unlisted strike 20000 flagged, 23400 passes
attack: look-alikes (datetime.now().year<3000, len(x)<LIMIT, two-now compare, unrelated alias) not flagged; f-string param and wrong head left unchecked as documented; local-constant threshold not flagged (documented gap); over-approximations (K+100 flags 100 as a strike; datetime.now()-d flagged without a clock d) affect no real test; synthetic allowlist functions confirmed to build their own Catalogue and never read the CSV

Recorded by the orchestrator from the verifier's returned block.
