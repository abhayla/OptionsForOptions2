# Verifier brief: builder sequence row 2 (REQ-015 / W-130), Tier A

Independent, adversarial verifier; you did not build this. READ-ONLY: never edit, create, commit or delete a file in
any checkout (no in-place mutation); scratch and mutation copies only in
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\cdc8b776-da99-4858-844d-ba9899512551\scratchpad\verify-02`.

Code under test: worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`, head
af331fe4; the row-2 build is commits 3d9e5a4a and 008243e2 (diff c4802973..008243e2). Spec: `spec/requirements/REQ-015.md`
(AC-3 was rewritten by `spec/decisions/ADR-169.md`, owner 2026-10-22), ADR-020, ADR-138, ADR-160. Builder brief:
`docs/process/builder-sequence-briefs/row-02-REQ-015-connection.md`. A start-state verifier on main (2026-10-22) found:
AC-1, AC-6, AC-7, AC-8 pass; AC-2 fail; AC-3 fail (old text); AC-4, AC-5, AC-9 partial. Re-check ALL nine ACs.

## Live system (the owner's Kite session is live today)
The live API on http://127.0.0.1:8765 now runs THIS worktree's code (ofo_dev, LIVE_MARKET=1, order path off). Allowed:
GET requests and opening websockets to read pushes (`/api/market/indices/live`, `/api/strategies/live` with a body as
the builder screen sends). FORBIDDEN: login/callback URLs, Disconnect, Reconnect, any POST/PUT/DELETE to broker routes,
anything under execute/execution/orders; never stop the API; never send an order.
Orchestrator's live readings (11:44 IST): with no screen open the live row was `partial live_feed_waiting`; while an
index socket was held: NIFTY 22692.30 pushed every second and `connected`; 70 s after that socket closed: still
`connected`. ATTACK FIRST: decide from the code (and a live re-read if useful) whether the third reading is honest -
does the Kite socket keep receiving ticks after the last screen unsubscribes (which tokens stay subscribed?), and what
window turns `connected` into `live_feed_waiting` when ticks stop? If the row can say connected while no tick has
arrived for longer than the REQ-049 data-health window, that is a fail.

## Points to attack per AC
- AC-2: the exact sentence wherever a broker-dependent function asks for the connection (grep loosely; check the pin).
- AC-3 (new text): no screen asks for an API key, secret or developer app; connection only via the Zerodha login.
- AC-4: four separate statuses; each live-row state (waiting, reconnecting, session ended, connected) from a REAL
  provider state in a test, not a hand-set flag; the Settings page renders the fix texts.
- AC-5: the positions read runs once per RE-connect (not first connect), off the receive loop, no retry, never an order
  call (trace every call reachable from `on_reconnect`); the reconcile part is deferred (order path, REQ-060).
- AC-9: no token read from the environment anywhere (grep `KITE_ACCESS_TOKEN`, `access_token` env reads), none logged.
- AC-1, AC-6, AC-7, AC-8: re-check against the diff (no regression).

Tests: domain `python -m pytest -q -p no:cacheprovider tests/<file>.py`; app (targeted files only; the shared DB also
serves another product's production) `python D:/Abhay/Ventures/OptionsForOptions2/scripts/orchestrator/db_run.py D:/Abhay/Ventures/OptionsForOptions2-builder-reqs python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/<file>.py`;
frontend `npx vitest run <file>` in `frontend/`. Known environment issue: tests asserting an empty shared catalogue fail
(#497).

Why Opus: Tier A (auth/tokens, live-data liveness); adversarial across backend, frontend and a live system.

Return a JSON array, one object per AC: `{"row": 2, "req": "REQ-015", "ac": "AC-n", "result": "pass" | "fail" |
"partial" | "live check pending" | "deferred", "commands": "...", "observed": "... file:line", "attack": "..."}`, then
under 250 words: each fail/partial with the smallest fix, and anything not checked and why.
Budget: 40 min wall-clock, 70 tool calls
Report: evidence-table
