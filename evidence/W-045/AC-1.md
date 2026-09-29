---
work_item: W-045
ac: AC-1
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "Round 1 (d17c224): pytest tests/adjustment; independent regex parse of the spec table vs the registry; full suite. Round 2 (05114a5): python -m pytest -q -p no:cacheprovider tests/adjustment; independent parse of git show origin/main:spec/technical-design/adjustment-data-contract.md vs metric_registry.json; in-memory removal of the bool-id guard; full suite"
---

AC: AC-1
result: pass
commands: Round 1 (d17c224): pytest tests/adjustment; independent regex parse of the spec table vs the registry; full suite. Round 2 (05114a5): python -m pytest -q -p no:cacheprovider tests/adjustment; independent parse of git show origin/main:spec/technical-design/adjustment-data-contract.md vs metric_registry.json; in-memory removal of the bool-id guard; full suite
observed: Round 1: 11 passed, 30 rows x 7 cells, 0 mismatches; flagged rows 4/26 stale in the spec (fixed by owner Q248). Round 2: 13 passed; 30 rows equal to the spec on origin/main; bool id refused by real code, accepted by the mutated copy; owner_reading for rows 4/26/28 cites Q248/Q246 consistent with the spec; full suite 1379 passed
attack: Independent parser and hand verdict map; tampered JSON (unknown key, bad word, dup id, reorder, missing key, null item, out-of-V1 marked pass, bool id) refused. Residual: a JSON row changed to 'pass' only fails via the spec-parsing test in CI.

Recorded by the orchestrator from the verifier's returned block.
