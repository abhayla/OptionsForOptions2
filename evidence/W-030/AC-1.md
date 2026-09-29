---
work_item: W-030
ac: AC-1
result: pass
verified_by: "verifier (sonnet, fresh context; second check W-030b)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/test_fixture_symbols.py; python -m pytest -q -p no:cacheprovider; _pairing_violations on 5 attack shapes (verifier W-030b)"
---

AC: AC-1
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/test_fixture_symbols.py; python -m pytest -q -p no:cacheprovider; _pairing_violations on 5 attack shapes (verifier W-030b)
observed: 6 passed; full suite 1218 passed; the finding's example NIFTY26OCT23400CE/2026-10-06 and a SENSEX symbol not in the catalogue are caught; a real catalogue symbol paired with a wrong expiry is caught in the same-call keyword form and through module-level constants (including Leg(contract=SYM, expiry=EXP) when the file has one date constant); 7 files corrected with symbol text only; allowlist entries each carry a reason and a staleness test; 3 out-of-scope literals filed as #51
attack: round 1 failed: a real symbol with a wrong separately-declared expiry passed and the docstring overclaimed. Round 2: positional-argument calls, keyword-built dates and function-local names are not paired, and the docstring says so (honest limits, not claimed)

Recorded by the orchestrator from the verifier's returned block.
