---
work_item: W-066
ac: AC-7
result: pass
verified_by: "verifier (Opus, independent, Tier A, 2026-10-15)"
builder: "builder (Opus, rounds 7-8, 2026-10-15)"
date: '2026-10-15'
commands: "strategy_outcome replay runs for shapes E/mixed/two-strike/#172 with own expiry_pnl_at scan; engine attack shapes A1,A1b,A1c,A2,A3,A3b,D1,D2; python -m pytest -q -p no:cacheprovider tests/engine ; tests/outcome ; tests/errors ; loss-region test files; db_run.py <worktree> python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_outcome_split_loss.py tests_app/test_outcome_catalogue.py tests_app/test_outcome_route.py tests_app/test_response_door.py; in-process mutations of 3 _loss_regions guards and 2 LevelRegions guards; python tools/ac_fp.py REQ-034 AC-7 --yaml"
---

AC: AC-7
result: pass
commands: strategy_outcome replay runs for shapes E/mixed/two-strike/#172 with own expiry_pnl_at scan; engine attack shapes A1,A1b,A1c,A2,A3,A3b,D1,D2; python -m pytest -q -p no:cacheprovider tests/engine ; tests/outcome ; tests/errors ; loss-region test files; db_run.py <worktree> python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_outcome_split_loss.py tests_app/test_outcome_catalogue.py tests_app/test_outcome_route.py tests_app/test_response_door.py; in-process mutations of 3 _loss_regions guards and 2 LevelRegions guards; python tools/ac_fp.py REQ-034 AC-7 --yaml
observed: E/mixed: 'At every level except exactly 22,400 at expiry.'; two-strike: 'If NIFTY ends below 22,783.33 (except exactly 22,400) at expiry.'; #172: 'between 22,000 and 22,800 (except exactly 22,400)'; 0 mismatches at 2-decimal levels; 659/41/677 domain passed, 492 loss-region passed (361 round-7 + 123 round-8 collected), 237 app passed; every mutation turned named tests red; ac_fp 5250eb0c6b9d
attack: edges printing 0.01 apart, exact half-even edges, two and three sub-paisa gaps, flat-zero gap (strikes must be 2-decimal; 0.01-apart strikes give two true regions), sub-paisa loss region ('at 22,400', true): all true at 2-decimal levels. Limit: 8 levels on a 0.001 grid (e.g. 22,399.996) are positive yet inside the claimed loss; accepted because index levels are 2-decimal. Covers the class: yes.

Recorded by the orchestrator from the verifier's returned block.
