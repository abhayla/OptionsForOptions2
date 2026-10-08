---
work_item: W-059
ac: AC-3
requirement: REQ-048
ac_fp: "1d9648a7b038"
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (sonnet)"
date: '2026-10-08'
commands: "python tools/ac_fp.py REQ-048 AC-3 --yaml; python -m pytest -q -p no:cacheprovider tests/marketdata/test_provider_replaceable.py; Grep 'kite_(frames|provider|ws)|import websockets' over backend"
---

AC: AC-3
result: pass
commands: python tools/ac_fp.py REQ-048 AC-3 --yaml; python -m pytest -q -p no:cacheprovider tests/marketdata/test_provider_replaceable.py; Grep 'kite_(frames|provider|ws)|import websockets' over backend
observed: A FakeProvider (second MarketDataProvider) runs FanOut and QuoteBook/FeedState unchanged; one vendor subscribe for two subscribers; the 61 s health rule holds. The AST scan of backend/**/*.py finds no importer of kite_* outside kite_frames, kite_provider and kite_ws. Grep confirms the only importer is ofo_app/kite_ws.py, which is an adapter file.
attack: Looked for a Kite import leaking into domain code. The grep shows none. The AST scan is sound: test_the_import_scan_would_catch_a_leak checks the detection predicate on a planted leak. That check exercises the predicate on a sample import, not the scan itself, which is a minor weakness.

Recorded by the orchestrator from the verifier's returned block.
Recorded 2026-10-08 at PR #131 head c75e776. Review: Tier B diff review, 1 round, MAJOR findings fixed (see AC-2.md).
