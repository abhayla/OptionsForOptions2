---
work_item: W-060
ac: AC-3
requirement: REQ-072
ac_fp: "6b17eb3d7798"
result: pass
verified_by: "verifier (opus, fresh context)"
builder: "builder (opus round 3, sonnet round 4)"
date: '2026-10-08'
commands: "python r3s/attack.py <wt>; inline python (AVAILABLE/DELAYED x parity/fallback); python -m pytest -q -p no:cacheprovider tests/marketdata/test_parity_forward.py"
---

AC: AC-3
result: pass
commands: python r3s/attack.py <wt>; inline python (AVAILABLE/DELAYED x parity/fallback); python -m pytest -q -p no:cacheprovider tests/marketdata/test_parity_forward.py
observed: current=spot 23047, range 22000-24000; q 0.0776 parity / 0 fallback with 'estimated from spot' on model/IV/Greeks/scenario; spot_at on outputs; Hull CE23400 delta 0.158709 gamma 0.00067915 theta -4.1746 vega 9.2259 = engine; Estimated Now 901.5 = 901.50; per-expiry q 0.0300 on second expiry
attack: forward far from spot did not move CURRENT/range; hand Hull yield Greeks match engine

Recorded by the orchestrator from the verifier's returned block.
Recorded 2026-10-08. Verified at PR #135 head f654d39; the only code change since (to 43919f1) is tests/engine/test_pricing_scan.py (git diff --stat f654d39 43919f1 -- backend tests: 1 file), so the backend checked is unchanged.
