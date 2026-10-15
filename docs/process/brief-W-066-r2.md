# Builder brief: W-066 round 2 - close the free-token slots (Tier A review, 2026-10-09)

Core: no outcome text slot accepts a free token: every slot used by an outcome / table / summary template is a CLOSED
type (an enum Literal, `InstrumentId`, a trading-symbol pattern, the money/points/number string types in plain
notation), and `scenario_estimated_unavailable` no longer uses the untyped legacy slot.
Proof (step 1, red first against 8e80d82): `render_explanation("cell_text", value="₹8,245.25")`,
`render_explanation("summary_lose_unlimited", index="you-should-exit")` and
`render_explanation("scenario_estimated_unavailable", legs="Buy now, this is the best trade")` all RENDER today
(reproduced by the orchestrator); a test asserting each is refused, and the review's surviving mutation M2a (money
cells rendered as `cell_text(format_rupees(v))` in `backend/ofo/table/model.py` `_money`) turning a test red.

Tier: A. Model: sonnet/medium (kit routing: builder, always).
Budget: 45 min wall-clock, 70 tool calls. Commit after each numbered step; at budget stop after a commit and report.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~300 words.
Copy from: none.

## RCA and Class
- RCA: round 1 moved every text into templates but gave several templates an open `Recorded` slot (any token <= 64
  chars, no spaces) and left one on the untyped legacy slot, so the template is closed but its slots are not - the
  same "guard as an open list" class as W-061's (finding `jsonpath-check-lax-mode-unwraps-arrays`, wider shape).
- Class: every slot of every template the outcome API renders. Before: `cell_text`, `leg_label_symbol`,
  `outcome_problem_leg`, `summary_*_unlimited` and four more take `Recorded`; `scenario_estimated_unavailable` takes
  `LegacyRecorded`; `Amount`/`SignedAmount` print exponent form (`1E+3`, `+1E+2%`). After: none.
- Detection: a test that enumerates every template the outcome path can render (from the catalogue, not a hand list)
  and asserts no slot type is `Recorded` / `LegacyRecorded` / free `str`.

## Spec basis
- REQ-034 AC-7: "Outcome numbers appear in plain language first"
- ADR-003 decision: "every platform message comes from a
  fixed, reviewed template catalogue with typed slots."

## Start
- Worktree `C:\Abhay\Ventures\OptionsForOptions2-W-066`, branch `build/W-066-on-main` at 8e80d82.
- FIRST `git fetch origin` and `git merge origin/main` (PR #170 is CONFLICTING: `docs/process/coverage-stages.yaml`
  - keep main's version AND W-066's `W-066: 4a` work-item row; regenerate generated files with
  `python C:\Abhay\Ventures\OptionsForOptions2\scripts\orchestrator\regen.py C:\Abhay\Ventures\OptionsForOptions2-W-066`
  and `python C:\Abhay\Ventures\OptionsForOptions2\scripts\orchestrator\coverage.py C:\Abhay\Ventures\OptionsForOptions2-W-066 --write`).
  Commit the merge alone, then from the main checkout run
  `python scripts/orchestrator/merge_audit.py C:/Abhay/Ventures/OptionsForOptions2-W-066 8e80d82 origin/main HEAD`.
- Read `backend/ofo/errors/explanations.py` (slot types, `Recorded`, `LegacyRecorded`, `Amount`, `SignedAmount`),
  `templates.py`, `backend/ofo/table/model.py`, `backend/ofo/scenario/views.py:86-95`, the outcome service.

## What to fix
1. Closed slot types for every outcome template: `cell_text` only for enum/date/health values (closed Literal or
   date type); `leg_label_symbol` a trading-symbol pattern (e.g. `^[A-Z0-9]{1,40}$`, check real NFO/BFO symbols from
   the fixture CSV); `outcome_problem_leg` takes `InstrumentId`; `summary_*_unlimited` takes the underlying as a closed
   Literal (NIFTY 50 / SENSEX names as the catalogue holds them); the four other `Recorded` users likewise.
2. `scenario_estimated_unavailable`: legs as a closed list type (each an `InstrumentId` or the leg label type), not
   `LegacyRecorded`; test it through `view=estimated_now` with a leg lacking IV (the W-066 tests never request it).
3. `Amount` / `SignedAmount` print plain notation (no exponent), matching the response's `Money`; tests with
   `Decimal("1E+3")` and `Decimal("1E+2")`.
4. `outcome_margin_pending` wording: "Margin from Zerodha is not shown yet; it needs your Kite login." (no internal
   work-item name); `outcome_problem_leg` must not produce a double colon (render the id inside the sentence so it
   reads e.g. "Instrument NSE_FO:44624 is not in the instrument list").
5. In `docs/process/w024-templates-for-owner.md`, a short "Behaviour changes" note: the zero-max-loss sentence changed
   from the old "cannot lose" promise (forbidden by the wording rules) to the at-most-zero sentence; the max-loss /
   max-profit wording is pending an owner question about charges (do not change those templates now).
6. The detection test from the Class section.

## Reviewer checklist (each must turn a test red)
- M2a (money cells via `cell_text(format_rupees(v))`); a free token in each formerly-`Recorded` slot; a sentence in
  `scenario_estimated_unavailable`; `Decimal("1E+3")` in `cell_number`; the slot-type detection test with one
  template switched back to `Recorded`.

## Rules (this PC also serves IPODhan production's database - owner decision 2026-10-09)
- Targeted tests only, from `C:\Abhay\Ventures\OptionsForOptions2`:
  `python scripts/orchestrator/db_run.py C:\Abhay\Ventures\OptionsForOptions2-W-066 python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_outcome_catalogue.py tests_app/test_outcome_route.py tests_app/test_api_models.py tests_app/test_error_boundary_scan.py tests_app/test_replay_mode.py tests_app/test_apimodel_closed.py`;
  domain from the worktree: `python -m pytest -q -p no:cacheprovider tests/outcome tests/errors tests/table tests/scenario tests/marketdata`.
  CI mirror: `python C:\Abhay\Ventures\OptionsForOptions2\scripts\orchestrator\atool.py C:\Abhay\Ventures\OptionsForOptions2-W-066 W-066 --no-tests` (all steps rc 0).
  No full app suite, Playwright, npm, ci_local or alembic.
- Kit guard: shell text must not name .claude, tools/, spec/requirements, .github or views; read them with Read/Grep.
- Do not edit kit files or `spec/`. Never write `evidence/`. Never mark anything verified. Push `build/W-066-on-main`.
