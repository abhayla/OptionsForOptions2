---
work_item: W-139
ac: AC-7
requirement: REQ-114
ac_fp: "0df96a1aed55"
result: fail
verified_by: "independent verifiers (Opus, fresh context; round 1 on b04d47f0, round 2 on 0e574b58)"
builder: "builders (Sonnet/Opus, builder sequence row 11: build, fix 1)"
date: '2026-10-23'
commands: "round 2 on 0e574b58: mutation_gate.py M1 (feed_phase market_open=True) and M3 (route market_open=True) both killed; pytest tests/marketdata 237 passed"
---

AC: AC-7
result: fail
commands: round 2 on 0e574b58: mutation_gate.py M1 (feed_phase market_open=True) and M3 (route market_open=True) both killed; pytest tests/marketdata 237 passed
observed: live_market.py:306-307 uses the injected clock + is_market_open; broker_status.py:81,95-98 reads a closed market as closed in every phase but ended; Sat 2026-10-24, holiday 2026-10-20, Wed 08:00/16:00, 2027 no-data all closed; Wed 10:00 reconnecting; one ADR-177 wording templates.py:457 = disconnect.py:37,41 = sharedStateText.js:3-4
attack: forced market_open=True in two places: both killed; date beyond calendar data reads closed (fail-closed)

Recorded by the orchestrator from the verifier's returned block.

Re-verdict: Chunk 1 Tier A review area 1 (Opus, fresh, on 29d2dece): FAIL on the screens users reach. The calendar is read only by the Settings card (live_market.feed_phase, broker_status); quote health ignores it (backend/ofo/marketdata/feed_health.py:115), so on Saturday 2026-10-24 10:00 IST with Kite heartbeats the quotes read 'available' and the index strip 'Index values are live'; no screen mounts MarketClosedBanner. The earlier pass covered the Settings card only.
