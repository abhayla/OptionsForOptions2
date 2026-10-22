# Verifier brief: builder sequence row 7 (REQ-049 data health / W-135), Tier A

Independent, adversarial verifier; you did not build this. READ-ONLY: never edit, create, commit or delete a tracked
file in any checkout (no in-place mutation); scratch and mutation copies only in
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\cdc8b776-da99-4858-844d-ba9899512551\scratchpad\verify-07`.

Code under test: worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`, head
c908b5b0 (row-7 build = 4a8fe97e..c908b5b0). Spec: `spec/requirements/REQ-049.md` (every AC), ADR-015,
`spec/findings.md` F-32; issue #513 (`gh issue view 513`). Builder brief:
`docs/process/builder-sequence-briefs/row-07-REQ-049-data-health.md` - run every item of its `Attack list:` again,
with the variables of the CI job named on its `CI:` line.

Attack first: (1) the wanted-token check in `kite_provider.py`: a frame mixing one wanted and many unwanted ticks, a
token released between two frames, a token wanted by a second screen while the first releases it, the index tokens;
(2) `market_open` moved to `backend/ofo/timeutil.py`: is it truly the ONE check (grep for any other 09:15 / 15:30 / IST
open-close logic), does Execute's behaviour stay identical, and the boundaries 09:14:59 / 09:15:00 / 15:29:59 /
15:30:00 and a Saturday; (3) after hours, can any row still say Reconnect, and does a session Zerodha ended still say
log in again; (4) the log line in `get_kite_session`: no token, no exception message, exactly one line; (5) AC-3: the
trigger path refuses on STALE and UNAVAILABLE quotes (existing tests in `tests/marketdata/test_rule_health.py`) - check
it is the real trigger path, not a helper; (6) run the frontend unit tests that cover `BrokerSettingsPage.vue`
(`npx vitest run <the broker-settings test file>` in `frontend/`).

Known failing, not this build: `tests/test_edit_lint_hook.py::test_real_eslint_run_flags_unused_variable` (fails on
main too, local ESLint environment). DB tests through the throwaway-database runner:
`python D:/Abhay/scratch/ofo2-builder-sequence/fresh_launch.py D:/Abhay/Ventures/OptionsForOptions2-builder-reqs python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/<file>.py`
(creates and drops its own database only).

Why Opus: Tier A (live-data liveness and the status a user trusts before acting).

Return a JSON array, one object per AC: `{"row": 7, "req": "REQ-049", "ac": "AC-n", "result": "pass" | "fail" |
"partial" | "deferred", "commands": "...", "observed": "... file:line", "attack": "..."}`, then under 250 words: each
fail/partial with the smallest fix, and anything not checked and why.
Budget: 40 min wall-clock, 70 tool calls
Report: evidence-table
