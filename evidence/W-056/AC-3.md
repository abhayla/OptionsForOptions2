---
work_item: W-056
ac: AC-3
requirement: REQ-054
ac_fp: "cc0e746c3391"
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (opus)"
date: '2026-10-02'
commands: "gh run list --branch build/W-056-broker-identity; gh run view 36992942967 --log | grep PROOF/passed; read REQ-054, tests_app/test_broker_instruments.py, alembic 0004_broker_instruments.py, catalogue_store.py"
---

AC: AC-3
result: pass
commands: gh run list --branch build/W-056-broker-identity; gh run view 36992942967 --log | grep PROOF/passed; read REQ-054, tests_app/test_broker_instruments.py, alembic 0004_broker_instruments.py, catalogue_store.py
observed: CI App tests run 36992942967 (head 1e5e9bf, success) and 36993389669 (final head 1e5d449, success, re-checked by the orchestrator): "475 passed, 3 skipped" with OFO_REQUIRE_DB_TESTS=1; the 3 skips are test_entitlement_store.py:198 (ENDED is only a trial's early end, ADR-039), unrelated. Real Zerodha file: W-056 PROOF file rows=39354 skipped_outside_v1=67883 in_scope=4970 catalogue=4970 zerodha_rows=4970. 1e5d449 differs from 1e5e9bf only in work/W-056.md (git diff --stat). NIFTY 20050 CE -> ('NSE_FO', 40559, 'zerodha', '10383106', 'NIFTY26O0620050CE'); SENSEX 75000 CE -> ('BSE_FO', 888931); NSE/1001 file rows=['NIFTY 50', '94SFL28-YL'] stored=0; missing broker row refused: upstox lookup raised MissingBrokerRef. catalogue_contracts unique on (exchange_segment, exchange_token) with CHECK in (NSE_FO, BSE_FO); exchange, instrument_token, tradingsymbol, segment, lot_size, tick_size dropped; broker_instruments CHECK broker IN ('zerodha'), unique (broker, broker_segment, broker_token) and (contract_id, broker), DELETE and identity change refused (OF006). Tests: information_schema finds token/symbol columns only in broker_instruments; 'upstox', 'dhan', 'Zerodha' lookups raise MissingBrokerRef; unknown broker code and segments 'NFO'/'NSE' refused by the database; allowlist block 8 flags a moved column on catalogue_contracts.
attack: instrument_token back on catalogue_contracts -> caught by the information_schema test and the allowlist; unknown broker code -> CHECK refuses; case variant 'Zerodha' -> refused; contract with no broker row -> load_catalogue raises 'NSE_FO:99999: has no zerodha row'; F-10 collision -> stored=0. Residual: the vocabulary holds one value, so 'one vocabulary' is exercised for one broker only. Deferred, outside this AC: execution layer by Zerodha symbol (#115), token reuse after expiry (#116).

Recorded by the orchestrator from the verifier's returned block.
