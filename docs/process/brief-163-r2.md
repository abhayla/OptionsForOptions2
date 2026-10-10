# Builder brief: #163 round 2 - log every refusal by its code (Tier A review, 2026-10-10)

Core: every refusal of the Kite login callback writes one log record naming its closed refusal code (and nothing else
from the request or from Kite), as the error boundary did before #163 moved refusals to a redirect.
Proof (step 1, red first against adfa0d8): a tests_app test where Kite answers busy (`KiteExchangeError("kite_busy")`)
asserts a log record containing `kite_busy` and the callback path, and none containing the request token, the access
token, the API key/secret or Kite's own message - red today (the review captured only two redacted HTTP lines).

Tier: A. Model: sonnet/medium. Budget: 20 min wall-clock, 30 tool calls. Commit; at budget stop after a commit, report.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~200 words.
Copy from: none.

## RCA and Class
- RCA: refusals used to reach the error boundary, which logged `user-facing error <code> on GET /kite/callback`
  (`backend/ofo_app/errors.py:212`); round 1 answered them with `_refused_redirect` directly, so nothing logs them.
- Class: every `raise`/return of a refusal in `kite_callback` (each code in REFUSAL_CODES). Before: 0 logged. After: each
  logs exactly one record with its code, at the level the boundary used for that refusal's category.
- Detection: a parametrized test over every refusal path asserting the record (and the absence of secrets).

## Do
1. In `_refused_redirect` (`backend/ofo_app/routes/broker.py`), log the closed code in the same shape and level as the
   error boundary's `user-facing error <code> on <method> <path>` (reuse its helper if one exists); never the Kite text.
2. Tests: the parametrized log test above over every refusal path; plus the two behaviour tests the review found
   missing: an UNKNOWN `KiteExchangeError` code -> redirect with `kite_refused` (not the raw code); a generic exception
   from the token exchange -> redirect with `kite_unavailable`.
3. Mutation (must go red): drop the log call; log Kite's message instead of the code.

## Spec basis
- REQ-065 AC-2: "Every user-facing error states what happened, the impact, what is blocked and the next action."

## Rules (this PC also serves IPODhan production's database)
- From `C:\Abhay\Ventures\OptionsForOptions2`: `python scripts/orchestrator/db_run.py C:\Abhay\Ventures\OptionsForOptions2-163 python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_kite_login.py tests_app/test_error_logging.py tests_app/test_error_boundary_scan.py`;
  CI mirror `python C:\Abhay\Ventures\OptionsForOptions2\scripts\orchestrator\atool.py C:\Abhay\Ventures\OptionsForOptions2-163 163 --no-tests`.
  First `git fetch origin` and `git merge origin/main` (main gained coverage rows); commit the merge alone.
- Kit guard: shell text must not name .claude, tools/, spec/requirements, .github or views. Do not edit kit files or
  `spec/`. Never write `evidence/`. Push `fix/163-refusal-redirect`.
