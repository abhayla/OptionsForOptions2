---
work_item: W-131
ac: AC-1
requirement: REQ-054
ac_fp: "7bd2f8004431"
result: pass
verified_by: "independent verifier (Opus, fresh context, round 1 on 4e701769)"
builder: "builder (Sonnet, builder sequence row 3)"
date: '2026-10-22'
commands: "Tier A verifier (Opus) on 4e701769: db_run pytest tests_app/test_kite_broker_reader.py test_kite_reads.py test_kite_quote_bands.py test_kite_http_guard.py (422 passed, 0 skipped); mutation script mut.py (M1-M16 killed, M17 survived); check_call probe; inspect.signature vs BrokerReader. Orchestrator core proof: record_profile_door.py on the owner's live session 2026-10-22 (HTTP 200)"
---

AC: AC-1
result: pass
commands: Tier A verifier (Opus) on 4e701769: db_run pytest tests_app/test_kite_broker_reader.py test_kite_reads.py test_kite_quote_bands.py test_kite_http_guard.py (422 passed, 0 skipped); mutation script mut.py (M1-M16 killed, M17 survived); check_call probe; inspect.signature vs BrokerReader. Orchestrator core proof: record_profile_door.py on the owner's live session 2026-10-22 (HTTP 200)
observed: READ parts only (the basket and reconcile parts are order-path scope, deferred by ADR-165): authenticate unchanged (kite_auth.py, kite_client.py); account = GET /user/profile through the door keeping exactly broker, exchanges, products, order_types, user_id (user_id out of repr), proven on the real reply (ZERODHA; MF/BFO/BSE/NSE/NFO; CNC/NRML/MIS/BO/CO; MARKET/LIMIT/SL/SL-M); margin delegates to KiteMargin; positions via positions_from_reply; orders one GET /orders with an allow-listed status vocabulary; order status from the ONE /orders list, absent id -> None, duplicates -> bad_reply, /orders/{id} refused; KiteBrokerReader matches all four BrokerReader signatures
attack: PII (email, name, avatar, meta) absent from value, repr, logs, errors; all 5 Kite exception types, 429, timeout, junk JSON, missing data -> the door's code with 1 call, no retry. MINORs (deferred issue): a failed profile read can still mark the sync fresh (M17 survived); a bare string id is split into characters

Recorded by the orchestrator from the verifier's returned block.
