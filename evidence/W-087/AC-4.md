---
work_item: W-087
ac: AC-4
requirement: REQ-001
ac_fp: "245cb722071f"
result: pass
verified_by: "verifier (sonnet/high, fresh context, docs/gc-1-closeout b643356)"
builder: "none (verify-only card; code on main)"
date: '2026-10-16'
commands: "python -m pytest -q -p no:cacheprovider tests/instruments/test_exchange_segment.py::test_segment_vocabulary_is_closed_and_zerodha_exchange_maps_into_it tests/instruments/test_exchange_segment.py::test_fixture_slice_maps_nfo_and_bfo_rows_to_their_segments; python tools/ac_fp.py REQ-001 AC-4 --yaml; python -c (SUPPORTED_UNDERLYINGS; parser rows)"
---

AC: AC-4
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/instruments/test_exchange_segment.py::test_segment_vocabulary_is_closed_and_zerodha_exchange_maps_into_it tests/instruments/test_exchange_segment.py::test_fixture_slice_maps_nfo_and_bfo_rows_to_their_segments; python tools/ac_fp.py REQ-001 AC-4 --yaml; python -c (SUPPORTED_UNDERLYINGS; parser rows)
observed: both passed within the 175; EXCHANGE_SEGMENTS == {NSE_FO,BSE_FO,NSE_INDEX,BSE_INDEX}; ZERODHA_EXCHANGE_TO_SEGMENT == {NFO:NSE_FO, BFO:BSE_FO}; SUPPORTED_UNDERLYINGS == {'NIFTY':'NSE_FO','SENSEX':'BSE_FO'}; parsed SENSEX row got exchange_segment BSE_FO, NIFTY got NSE_FO
attack: Raw exchange names 'NFO','BFO','NSE','nse_fo','',None are refused as InstrumentId segments (ValueError). Contract carries exchange_segment, not a hard-coded exchange, so more exchanges need only a new vocabulary entry. 'Allows more exchanges later' is a design property supported by the closed-but-extendable vocabulary, not directly exercised by a test.

Recorded by the orchestrator from the verifier's returned block.
