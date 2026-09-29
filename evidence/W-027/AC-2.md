---
work_item: W-027
ac: AC-2
result: pass
verified_by: "verifier (sonnet, fresh context; round 2 at 7f283fe, regression test checked by orchestrator at efbd56e)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/strategy/test_modification_metrics.py; independent hand computation of the after-side payoff"
---

AC: AC-2
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/strategy/test_modification_metrics.py; independent hand computation of the after-side payoff
observed: before = 6825 / 8175 / (22909, 23491) / 1365.00, matching scenario-calculations.md s6; after = max profit 5625, max loss 9375, breakevens (22825, 23475), current P&L 727.50, re-derived by hand and matched exactly
attack: failing margin/charges providers give None with a reason on both sides, never 0; no LTPs give current_pnl None with a reason

Recorded by the orchestrator from the verifier's returned block.
