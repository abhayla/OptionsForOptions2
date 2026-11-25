# Parked: Phase 6 B2 (`execute_plan.exit_legs` through `open_legs_to_close`)

Parked 26 Nov 2026, about 03:00 IST, Lane A (unattended run). F7 and F8 of Phase 6 are done; only B2 is parked.

## Why

The plan's design (section 5.6: "`execute_plan` gains one import of the stdlib-only `ofo.tracking.closing`") breaks an
existing spec guard: `tests_app/test_strategy_tracking_imports.py::test_ac1_no_order_path_module_imports_the_tracking_code`
(REQ-109 AC-1 / AC-2: no module of the order path imports `ofo.tracking` or `ofo_app.paper_store`, so a paper entry can
never be read into an order). Evidence, prepush preflight on `a4c2e7b1`:

```
FAILED tests_app/test_strategy_tracking_imports.py::test_ac1_no_order_path_module_imports_the_tracking_code
Left contains one more item: 'backend/ofo_app/execute_plan.py: from ofo.tracking.closing import open_legs_to_close'
```

The guard is a spec rule, not a style check, so it is not edited. Neither the builder's gates (ci_local does not run
`-m repo_scan tests_app`) nor the Tier A review caught it.

## What was done

`git revert` of `bc4d8df1` (TypeError pin test) and `2e5a6e96` (the B2 code). `execute_plan.py`,
`ofo/execution/**` and `routes/execute.py` are byte-identical to the Phase 4 head `87a446bf` (`git diff 87a446bf HEAD
--stat -- ...` empty). Kept as guards (they pass on the old body): `tests_app/test_exit_legs_oracle.py` (12 rows) and
`tests_app/test_exit_basket_golden.py` (whole Kite basket repr). Check after the revert:
`pytest -c pytest-app.ini tests_app/test_strategy_tracking_imports.py tests_app/test_exit_legs_oracle.py
tests_app/test_exit_basket_golden.py tests_app/test_checked_basket.py`: `62 passed`.

## What is left (two options, a technical choice; no owner question)

1. Move the pure close-list step out of `ofo.tracking` to a neutral package both sides may import (for example
   `ofo/engine/closing.py`, stdlib only), update `paper_exit.py`, `PAPER_MODULES` in `tests_app/test_paper_order_door.py`
   and `tests/tracking/test_closing.py`; then re-apply B2 (the reverted commit) with the oracle and golden unchanged, and
   a fresh Tier A review. Cost: moves a reviewed Phase 4 file.
2. Leave B2 out for good: the real path keeps its own two-line close list; the saving is one line (plan 2.2 already says
   "the real path must not move for a one-line saving" about `partial.py`).

Recommendation: 2, unless Phase 8's guard G2 needs one home for the close rule; then 1 in its own round.
