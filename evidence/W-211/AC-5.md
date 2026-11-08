---
work_item: W-211
requirement: REQ-167
ac: AC-5
result: fail
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "d06109d5947a"
commands: "python registry group/key dump of backend/ofo/settings/registry.json; read tests/test_settings_literal_guard.py KNOWN_LEFTOVERS; grep Decimal/time literals in backend/ofo and backend/ofo_app"
---
Groups present: Scenarios, Adjustment defaults, Alert discipline, Limits, Speeds, Pricing, Exchange and broker facts (4 keys), Detection, Billing, Data, Other; Charges from its table. Not settings although the AC lists them (KNOWN_LEFTOVERS): market hours and expiry close (backend/ofo/timeutil.py:27-34), the Kite 06:00 expiry (migration 0007 trigger), preset constants (alert_gate.py:40-42); no key for freeze units and batch, Zerodha rate and feed limits, quote limit; the tick 0.05 is typed (approaches.py:255, orderbook.py:51).

Partial by design (ADR-222 (11): groups moved a few at a time).

Recorded by the orchestrator from the verifier's returned block.
