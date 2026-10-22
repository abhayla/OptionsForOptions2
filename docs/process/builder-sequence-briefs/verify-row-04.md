# Verifier brief: builder sequence row 4 (REQ-117 broker capability flags / W-132), Tier A

Independent, adversarial verifier; you did not build this. READ-ONLY: never edit, create, commit or delete a file in
any checkout (no in-place mutation); scratch and mutation copies only in
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\cdc8b776-da99-4858-844d-ba9899512551\scratchpad\verify-04`.

Code under test: worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`, head
2e0cea66; the row-4 build is commits 22939820 and 2e0cea66 (diff f7e994c7..2e0cea66, ignoring the docs-only commit
e4ac1283). Spec: `spec/requirements/REQ-117.md` (AC-1..AC-5) and the ADRs it cites. Builder brief:
`docs/process/builder-sequence-briefs/row-04-REQ-117-capability-flags.md` (its What to build lists the orchestrator's
technical decisions) - run every item of its `Attack list:` again.

Scope notes: the features REQ-100 (stop at Zerodha), REQ-102 (MIS) and REQ-103 (Orders page, funds view) do not exist
yet; AC-3's "hidden with a plain reason" is proven on the one real consumer, the builder's margin line
(`basket_margin_quote`), and the three future features bind their flags when built: report AC-3's feature part for
them as `deferred`, the repo-test part must pass now. Check each Zerodha flag value carries a source and a date and
that the source is real (a repo path that exists, or a Kite docs URL; `intraday_product` rests on
`tests/fixtures/kite_replies/user-profile-2026-10-22-redacted.json`).

Known failing tests, not this build (do not re-prove): any test asserting an empty shared catalogue in ofo_test
(#497: `tests_app/test_catalogue_picker_api.py` count==0 cases, `test_freeze_store.py`, the catalogue/instrument DB
tests - they fail identically on main 3ccc8439).

Tests: domain `python -m pytest -q -p no:cacheprovider tests/<file>.py`; app (targeted files only; the shared DB also
serves another product's production) `python D:/Abhay/Ventures/OptionsForOptions2/scripts/orchestrator/db_run.py D:/Abhay/Ventures/OptionsForOptions2-builder-reqs python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/<file>.py`
(a skipped DB test counts as NOT run); frontend `npx vitest run <file>` in `frontend/`.

Why Opus: Tier A (broker flags feed what the order path may offer; a safety-gate interaction); adversarial checks on
fail-closed loading, the broker-name scan and the gates.

Return a JSON array, one object per AC: `{"row": 4, "req": "REQ-117", "ac": "AC-n", "result": "pass" | "fail" |
"partial" | "deferred", "commands": "...", "observed": "... file:line", "attack": "..."}`, then under 250 words: each
fail/partial with the smallest fix, and anything not checked and why.
Budget: 40 min wall-clock, 70 tool calls
Report: evidence-table
