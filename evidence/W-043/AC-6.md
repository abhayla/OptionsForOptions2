---
work_item: W-043
ac: AC-6
result: pass
verified_by: "verifier (opus, fresh context)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/execution/test_complete_refusals.py tests/execution/test_complete_slices.py tests/execution/test_close_refusals.py; python - (stdin probe, real instruments_slice.csv); python -m pytest -q -p no:cacheprovider"
---

AC: AC-6
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/execution/test_complete_refusals.py tests/execution/test_complete_slices.py tests/execution/test_close_refusals.py; python - (stdin probe, real instruments_slice.csv); python -m pytest -q -p no:cacheprovider
observed: 56 passed; full 1359 passed; Complete+Retry with freeze 64(NIFTY)/19(SENSEX)/0/-65/True/65.0/1 -> ready False, orders 0, gate None, no live prep, Close marker None, book 4->4, reason 'Nothing prepared: ...'; freeze 130 afterwards -> 5x130
attack: freeze below one lot/zero/non-int and non-whole-lot missing -> refusal, no state change; unknown Retry leg still raises ValueError; delisted contract still raises REQ-036 AC-3 ValueError (grounding is outside the try); red-on-main exec probe inconclusive (harness error); the removed pytest.raises tests show main raised

Recorded by the orchestrator from the verifier's returned block.
