# Verifier brief: builder sequence row 6 (REQ-048 market-data pipeline / W-134), Tier A

Independent, adversarial verifier; you did not build this. READ-ONLY: never edit, create, commit or delete a file in
any checkout (no in-place mutation); scratch and mutation copies only in
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\cdc8b776-da99-4858-844d-ba9899512551\scratchpad\verify-06`.

Code under test: worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`, head
73212d26; the row-6 build is df254516 + 73212d26 (diff 218be62d..73212d26). Spec: `spec/requirements/REQ-048.md`
(AC-1..AC-5) and its ADRs (ADR-012, ADR-053, ADR-153, ADR-162). Builder brief:
`docs/process/builder-sequence-briefs/row-06-REQ-048-pipeline.md` - run every item of its `Attack list:` again.

Orchestrator decisions to judge: (1) the in-process latest-quote store is AC-1's "fast cache" while one process
serves; row 9 (REQ-113) owns the cross-process cache; (2) the Kite Publisher basket form legitimately carries the
app's PUBLIC `api_key` (ADR-054), allow-listed with a reason - check that no access token, secret or session value can
reach a bundle or a reply; (3) the bundle scan skips with a named reason when `frontend/dist` is absent locally - check
that CI's app job builds the frontend before this test runs (read `.github/workflows/app-tests.yml` with Read only), or
the scan never runs anywhere.

Attack first: (a) the 15 `# noqa: PLC0415` directives the builder added in bulk with `ruff --add-noqa`: list them and
say whether any hides a real problem; (b) the allow-lists (hosts, import graph): does every entry have a reason and is
any entry wider than needed (e.g. `localhost` in a production bundle, `vuejs.org`/`www.w3.org` as hosts)? (c) planted
cases the builder did not list (a host split across string concatenation, base64 of a token, a `wss://` built at run
time).

Known failing, not this build: `tests/test_edit_lint_hook.py::test_real_eslint_run_flags_unused_variable` fails
identically on main 3ccc8439 (local ESLint environment). DB tests run in a throwaway database:
`python D:/Abhay/scratch/ofo2-builder-sequence/fresh_launch.py D:/Abhay/Ventures/OptionsForOptions2-builder-reqs python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/<file>.py`
(creates and drops its own database only). To build the frontend locally for the bundle scan: `npm run build` in
`frontend/` of the worktree writes `frontend/dist` (an untracked build output; allowed).

Why Opus: Tier A (live-data path and credential exposure to the browser).

Return a JSON array, one object per AC: `{"row": 6, "req": "REQ-048", "ac": "AC-n", "result": "pass" | "fail" |
"partial" | "deferred", "commands": "...", "observed": "... file:line", "attack": "..."}`, then under 250 words: each
fail/partial with the smallest fix, and anything not checked and why.
Budget: 40 min wall-clock, 70 tool calls
Report: evidence-table
