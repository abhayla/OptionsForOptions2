---
work_item: W-080
ac: AC-1
requirement: REQ-073
ac_fp: "ad9b88fb2d53"
result: pass
verified_by: "verifier (opus, fresh context)"
builder: "builder (opus/sonnet, worktree agents, rounds 1-10 + integration)"
date: '2026-10-16'
commands: "pytest tests/execution/test_kite_basket.py tests/execution/test_basket_tags.py tests/test_no_order_placement.py tests/test_door_names_private.py tests/test_egress_gate.py tests/broker tests/errors/test_write_allowlist.py (at 26eff25); Read backend/ofo/execution/basket.py:96-215"
---

AC: AC-1
result: pass
commands: the pytest run above at 26eff25; Read backend/ofo/execution/basket.py:96-215
observed: 560 passed in 10.04s. KiteOrder fixes order_type="LIMIT" and readonly=True; build_basket never overrides them. _resolve returns exactly one row per leg in plan.legs order, or raises. Live (orchestrator, 2026-10-16): Kite accepted this basket format for the real order 261016170576173 (BUY NIFTY26O1923650CE 65 LIMIT 5.45, filled 5.10) and the exit 261016170858845.
attack: zip(strict=False) cannot drop a leg because _resolve raises on any leg it cannot resolve; a non-positive price is refused by _number before either gate runs.

Recorded by the orchestrator from the verifier's returned block.
