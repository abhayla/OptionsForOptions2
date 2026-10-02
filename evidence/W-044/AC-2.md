---
work_item: W-044
ac: AC-2
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/instruments; python -m pytest -q -p no:cacheprovider (full); python probe on tests/fixtures/instruments/instruments_slice.csv (10 refusal variants, 1 accepted force, AuditLog subclass whose append raises); 3 mutation runs on tests/instruments/test_catalogue.py, each restored"
---

AC: AC-2
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/instruments; python -m pytest -q -p no:cacheprovider (full); python probe on tests/fixtures/instruments/instruments_slice.csv (10 refusal variants, 1 accepted force, AuditLog subclass whose append raises); 3 mutation runs on tests/instruments/test_catalogue.py, each restored
observed: 39 passed (instruments); 1358 passed (full). Refusals all ValueError with 0 events and 1085/1085 still listed. Force accepted: newly_unlisted=1, one ADMIN_CHANGE_RECORDED, payload tokens (221330181,) symbols ('SENSEX26OCTFUT',), actor stripped, timestamp==as_of, verify().ok True. Mutations: 3, 1, 1 failing tests.
attack: Whitespace/None reason, whitespace actor, missing audit_log, reason/actor/audit_log without force, append raising (catalogue unchanged, event written before mutation), non-force refusal writes no event: all as required. Gap: no test for the append-raises atomicity; actor/audit_log guards not mutation-checked.

Recorded by the orchestrator from the verifier's returned block.
