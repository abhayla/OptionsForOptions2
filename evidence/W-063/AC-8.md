---
work_item: W-063
ac: AC-8
requirement: REQ-034
ac_fp: "2ad88bee15c9"
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (opus)"
date: '2026-10-08'
commands: "python -m pytest -q -p no:cacheprovider tests/outcome; read service.py build_outcome; ad-hoc script posting view=at_expiry and view=estimated_now"
---

AC: AC-8
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/outcome; read service.py build_outcome; ad-hoc script posting view=at_expiry and view=estimated_now
observed: 54 passed (tests/outcome + execution guard + route). scenario_values called once; table and payoff_points both derive from that ScenarioValues; test_one_engine_computation_feeds_table_and_payoff counts exactly 1 scenario_grid call; payoff levels equal the scenario levels and pnl equals the TOTAL row cells; all 24 points equal the independent formula
attack: Looked for a second engine path for the payoff: none in code, and the counting monkeypatch would read 2 if one existed. Changed the planned entry by +10 on one SELL leg: every shared level moves by exactly 10 x 65, so the payoff follows the planned entry rather than the live LTP. estimated_now view returns COMPUTED with 24 points, no error.

Recorded by the orchestrator from the verifier's returned block.
