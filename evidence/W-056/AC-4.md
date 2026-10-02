---
work_item: W-056
ac: AC-4
requirement: REQ-054
ac_fp: "739ca370dc58"
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (opus)"
date: '2026-10-02'
commands: "same CI log grep; read the test file, the 0004 guard SQL and the catalogue_store UPDATE statements"
---

AC: AC-4
result: pass
commands: same CI log grep; read the test file, the 0004 guard SQL and the catalogue_store UPDATE statements
observed: CI App tests run 36992942967 (head 1e5e9bf, success) and 36993389669 (final head 1e5d449, success, re-checked by the orchestrator): "475 passed, 3 skipped" with OFO_REQUIRE_DB_TESTS=1; the 3 skips are test_entitlement_store.py:198 (ENDED is only a trial's early end, ADR-039), unrelated. Real Zerodha file: W-056 PROOF file rows=39354 skipped_outside_v1=67883 in_scope=4970 catalogue=4970 zerodha_rows=4970. 1e5d449 differs from 1e5e9bf only in work/W-056.md (git diff --stat). W-056 PROOF revise zerodha 12468226 lot 65->75 seen_on=2026-10-02 history=[('NSE_FO', 48704, 'zerodha', 'lot_size', '65', '75')]. broker_instruments: lot_size INTEGER NOT NULL >0, tick_size NUMERIC(10,4) >0, freeze_limit INTEGER nullable >0, seen_on DATE NOT NULL; the guard sets seen_on to the IST date from clock_timestamp() on INSERT and UPDATE; app role has no column grant on seen_on/first_seen_at/last_seen_at; loader uses COALESCE for freeze_limit. Tests: lot, tick, freeze revisions each write one dated history row; test_m4_a_zerodha_load_never_clears_a_stored_freeze_limit (1800 kept, revised == 0, 0 history rows); test_m1_owner_cannot_backdate_a_broker_rows_stamps (2000-01-01 overridden to today IST).
attack: seen_on caller-controllable -> not via the app role (no privilege), and the owner's 2000-01-01 is overridden by the trigger (tested); daily load clearing freeze_limit -> COALESCE keeps it, no 1800 -> NULL history row (tested). Limitation, consistent with REQ-054: freeze_limit cannot be cleared back to NULL by the load path; seen_on moves on every load of a present contract (the load day).

Recorded by the orchestrator from the verifier's returned block.
