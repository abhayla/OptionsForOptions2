---
work_item: W-081
ac: AC-3
requirement: REQ-055
ac_fp: "c798814d614e"
result: pass
verified_by: "verifier (Sonnet, independent, Tier B, 2026-10-17 GC-2b)"
builder: "builder (Opus/Sonnet, PR #337, 2026-10-17)"
date: '2026-10-17'
commands: "python -m pytest -q -p no:cacheprovider tests/test_margin_from_zerodha_only.py tests/execution/test_margin_gate.py tests/execution/test_complete.py; grep for planning estimate / margin_estimate_from / .margin_required in backend and frontend/src (main d61fcfb)"
---

AC: AC-3
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/test_margin_from_zerodha_only.py tests/execution/test_margin_gate.py tests/execution/test_complete.py; grep for planning estimate / margin_estimate_from / .margin_required in backend and frontend/src (main d61fcfb)
observed: All pass. test_ac3_zerodhas_figure_alone_decides and the scans (no estimate helper fills margin_required; planner .required_margin( calls counted per file) pass. test_273_planner_below_funds_but_zerodha_above_blocks: planner 1000.00, funds 1200.00, Zerodha 1200.01 -> MARGIN_INSUFFICIENT, nothing prepared. test_273_planner_above_funds_but_zerodha_below_is_not_blocked passes. The partial re-check reads Zerodha's figure via reader.fetch_required_margin (partial.py:701). Nothing in ofo_app references the estimate.
attack: Estimate below funds but Zerodha above: blocked by one paisa; estimate far above funds but Zerodha equal: not blocked; unusable Zerodha figures (NaN, negative, float, string, None, raised error) block; a planted planner call in partial.py is caught by the scan. CAVEAT: the clause 'shown as a planning estimate' has no test and no renderer yet (ExecutionReview.margin_required is an unlabelled field; no UI shows a platform margin); passed on the authority half, the labelling clause carried to GC-2c with the review screen.

Recorded by the orchestrator from the verifier's returned block.
