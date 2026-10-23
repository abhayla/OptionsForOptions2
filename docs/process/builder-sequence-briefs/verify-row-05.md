# Verifier brief: builder sequence row 5 (REQ-053 read part / W-133), Tier A

Independent, adversarial verifier; you did not build this. READ-ONLY: never edit, create, commit or delete a file in
any checkout (no in-place mutation); scratch and mutation copies only in
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\cdc8b776-da99-4858-844d-ba9899512551\scratchpad\verify-05`.

Code under test: worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`; the row-5
build is commits 03a9f377, 93c6097f, ed1daf9c (diff 8cc92664..ed1daf9c, code files only). Other agents may commit
process tooling (`scripts/orchestrator/db_run_fresh.py`, `reset_test_catalogue.py`) meanwhile: judge only the W-133
diff. Spec: `spec/requirements/REQ-053.md` (AC-1..AC-5, owner decisions and findings F-33 in its body). Briefs:
`row-05-REQ-053-eligibility.md` (What to build = the orchestrator's technical decisions), `row-05-finish.md` (the
staleness rule was changed to "loaded at or after 08:00 IST of the most recent weekday session"), `row-05-finish-2.md`.
Run every Attack list item of all three again.

Scope: AC-3 read part (the before-execution repeat is order-path scope, deferred; but `routes/execute.py` `_list_health`
was changed to the new staleness rule - check it changes nothing else in the order path). AC-5 as a registry
allow-list (`backend/ofo_app/order_limits_registry.py`, `tests_app/test_zerodha_rules_cited.py`); its entries say
`verified=False` - judge whether "cites a current Zerodha source and date" holds. AC-1, AC-2, AC-4: built on main,
re-check against the diff.

Attack first: (1) the test-only "pinned date judged at 12:00 IST" seam: can it apply in production? (2) the scheduler in
the app lifespan: can a slow or failing load block start-up, the live feed or a request? (3) the weekend / pre-08:00 /
no-holiday-calendar edges of the staleness rule. (4) does any eligibility read still use the old "loaded today" rule?

Known failing tests, not this build (do not re-prove): in `tests_app/test_catalogue_picker_api.py` and
`tests_app/test_contract_identity_lifecycle.py`, 15 tests fail identically on main 3ccc8439 and on ed1daf9c (shared
ofo_test catalogue, #497; the orchestrator diffed the two failure lists: no difference). The five tests in
`tests_app/test_catalogue_refresh.py` that load the slice (twice-loaded list, term change, truncated, empty, old list)
also need an empty catalogue: they get a throwaway-database run by the orchestrator later; read them for correctness.

Tests: domain `python -m pytest -q -p no:cacheprovider tests/<file>.py`; app (targeted files only)
`python D:/Abhay/Ventures/OptionsForOptions2/scripts/orchestrator/db_run.py D:/Abhay/Ventures/OptionsForOptions2-builder-reqs python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/<file>.py`.

Why Opus: Tier A (eligibility gates which contracts a user may add; a scheduler in the live process; a change in an
order-path module).

Return a JSON array, one object per AC: `{"row": 5, "req": "REQ-053", "ac": "AC-n", "result": "pass" | "fail" |
"partial" | "deferred", "commands": "...", "observed": "... file:line", "attack": "..."}`, then under 250 words: each
fail/partial with the smallest fix, and anything not checked and why.
Budget: 40 min wall-clock, 70 tool calls
Report: evidence-table
