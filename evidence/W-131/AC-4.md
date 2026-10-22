---
work_item: W-131
ac: AC-4
requirement: REQ-054
ac_fp: "739ca370dc58"
result: pass
verified_by: "independent verifier (Opus, fresh context, round 1 on 4e701769)"
builder: "builder (Sonnet, builder sequence row 3)"
date: '2026-10-22'
commands: "same as AC-3 (test_freeze_store.py: the same 5 failures on main, #497); start-state measure (0004 lines 417-419, 0013_exchange_freeze_limits.py, freeze_store.py, ofo/instruments/freeze_file.py; test_broker_instruments.py::test_ac4_*, test_m4_a_zerodha_load_never_clears_a_stored_freeze_limit, test_freeze_store.py::test_a_file_dated_after_today_is_refused)"
---

AC: AC-4
result: pass
commands: same as AC-3 (test_freeze_store.py: the same 5 failures on main, #497); start-state measure (0004 lines 417-419, 0013_exchange_freeze_limits.py, freeze_store.py, ofo/instruments/freeze_file.py; test_broker_instruments.py::test_ac4_*, test_m4_a_zerodha_load_never_clears_a_stored_freeze_limit, test_freeze_store.py::test_a_file_dated_after_today_is_refused)
observed: built on main and untouched by the diff: lot, tick and freeze limit per broker with the list's date; freeze limit from NSE MaxTradQty with the file's own date; a list without a value leaves it; a future-dated file refused; DB layer verified in CI at the chunk PR (#497 locally)
attack: regression compare only

Recorded by the orchestrator from the verifier's returned block.
