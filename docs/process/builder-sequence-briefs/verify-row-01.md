# Verifier brief: builder sequence row 1 (REQ-001 / W-129), Tier B

You are an independent, adversarial verifier. You did not build this. READ-ONLY: never edit, create, commit or delete a
file in any checkout (no in-place mutation either); scratch files and mutation copies only in
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\cdc8b776-da99-4858-844d-ba9899512551\scratchpad\verify-01b`.

Code under test: worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`, head
7067d229 (diff from d9f64419 = the row-1 build). Spec: `spec/requirements/REQ-001.md`. The builder brief is
`docs/process/builder-sequence-briefs/row-01-REQ-001-underlyings.md` (read it; its findings list is what was to be
fixed). Kit folders may be read with Read/Grep/Glob only.

Scope: AC-1 (the BANKNIFTY/FINNIFTY part is DEFERRED to row 46; check only NIFTY/SENSEX selectable and every other
value refused with the same plain catalogue message on every route and socket that takes an underlying, the symbol
echoed exactly as typed, a non-symbol never echoed; no stock option/screener/heatmap), AC-2 (exactly six leg types;
an INDEX catalogue row used as a leg is refused on save and on outcome, never a 500), AC-3 (no other broker), AC-4
(the underlying set and its exchange pairing live in one home; no route, socket or frontend list retypes it).

Attack first: find any route, websocket, request model or frontend picker that still accepts or retypes an underlying
outside the home (grep loosely: quotes, f-strings, `in (`, enum classes, `.vue` options); post `BANKNIFTY`, `nifty`,
`NIFTY ` (trailing space), `` (empty) and `N1FTY` to outcome, save, chain, planned entry, tracking and catalogue; check
the save route over HTTP with an INDEX row id. Run the new tests and a mutation of your own in scratch for one guard.

Tests you may run (from the worktree root): domain `python -m pytest -q -p no:cacheprovider tests/<file>.py`; app
`python D:/Abhay/Ventures/OptionsForOptions2/scripts/orchestrator/db_run.py D:/Abhay/Ventures/OptionsForOptions2-builder-reqs python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/<file>.py`
(targeted files only, the DB also serves another product's production); frontend `npx vitest run <file>` in
`frontend/`. You may start your own API from the worktree on port 8790 (APP_ENV=test, no LIVE_MARKET) for HTTP checks
and must stop it.

Return a JSON array, one object per AC: `{"row": 1, "req": "REQ-001", "ac": "AC-n", "result": "pass" | "fail" |
"partial" | "deferred", "commands": "...", "observed": "... file:line", "attack": "..."}`, then under 200 words: each
fail/partial with the smallest fix. Every claim rests on a command run in this session.
Budget: 25 min wall-clock, 45 tool calls
Report: evidence-table
