# Verifier brief: builder sequence rows 1-2 (REQ-001 / W-129, REQ-015 / W-130), one shared dispatch, Tier A

You are an independent, adversarial verifier ("how could this fail?"). You did not build any of this. READ-ONLY: never
edit, create, commit or delete a file in any checkout; scratch files only in
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\cdc8b776-da99-4858-844d-ba9899512551\scratchpad\verify-01-02`.

Code under test: the main checkout `D:\Abhay\Ventures\OptionsForOptions2` (branch main, head 235e1793; do not switch
branches). Spec: `spec/requirements/REQ-001.md`, `spec/requirements/REQ-015.md` and the ADRs they cite (ADR-001,
ADR-157, ADR-161, ADR-020, ADR-138, ADR-160). Kit files (`.claude/`, `tools/`, `factory/`, `.github/`) may be read
with Read/Grep/Glob only; a hook blocks any shell command naming them.

Both rows' starting state is "built". Old evidence (`evidence/W-0xx/`) is NOT trusted on its own: re-check every AC
against the code and a test or a run you perform now (example: evidence/W-075/AC-7.md proved a basis that ADR-167 later
reversed and nothing flagged it).

## Live system you may READ (owner's Kite session is live today, 2026-10-22)
A live API runs at http://127.0.0.1:8765 (ofo_dev, LIVE_MARKET=1, order path off). Allowed: GET requests (e.g.
`/health`, `/features`, `/api/broker/status`, `/api/market/indices`, `/api/catalogue/<U>/expiries`) and opening a
websocket to read pushes (`/api/market/indices/live`, send nothing). FORBIDDEN: any login/callback URL, Disconnect,
Reconnect, any POST/PUT/DELETE to broker routes, anything under execute/execution/orders. Never send an order. Never
stop the API process. If an AC can only be proven by dropping the live connection, mark it `live check pending` with
the exact check to run in a live window.

## Tests you may run
Domain: `python -m pytest -q -p no:cacheprovider tests/<file>.py` (from the main checkout). App/DB (shared test DB,
also serves another product's production: targeted files only, never the full suite):
`python scripts/orchestrator/db_run.py . python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/<file>.py`.
Frontend unit: in `frontend/`, `npx vitest run <file>`. A mutation check is a scratch copy of a module in your scratch
folder run against the tests through a temporary PYTHONPATH, never an edit in the checkout.

## Acceptance criteria and the points to attack

REQ-001 (row 1, Tier B row inside a Tier A group):
- AC-1: the BANKNIFTY/FINNIFTY part is DEFERRED to row 46 (REQ-090) by the contract; verify the rest: only NIFTY and
  SENSEX are selectable now, any other symbol (BANKNIFTY, FINNIFTY, a stock name, lower case 'nifty') is refused with
  a plain catalogue message on every route that takes an underlying (outcome, catalogue, save, chain, planned entry,
  indices, tracking) and on the screens' pickers; no stock option, screener or heatmap exists in routes or frontend.
  Report BANKNIFTY/FINNIFTY state as information only.
- AC-2: exactly six leg types (CE/PE buy/sell, FUT buy/sell): find every place a leg type is accepted (domain, request
  models, DB checks, frontend picker) and confirm the closed set; try a seventh shape (e.g. 'EQ', 'FUTSTK', an index
  leg) on each.
- AC-3: no other broker integration anywhere (grep routes, adapters, frontend, config for Angel/Upstox/Dhan/Groww/Paytm,
  'smartapi', 'dhanhq', 'upstox').
- AC-4: the underlying -> exchange mapping is recorded in ONE home and the model allows more exchanges; say exactly
  what is recorded for BANKNIFTY/FINNIFTY (pass if the data model carries them or can, with the mapping data-driven;
  fail if the NSE/BSE pairing is hard-coded in several places).

REQ-015 (row 2, Tier A):
- AC-1: connection is asked for only when a broker-dependent function is used: open the builder, outcome, catalogue,
  saved strategies without a session and confirm no login prompt; find where the prompt is triggered.
- AC-2: the exact prompt text, character for character, wherever it is shown.
- AC-3: the guided setup steps and both final lines, verbatim.
- AC-4: four separate statuses with Connected / Partially connected (naming the fix) / Disconnected (with the guide);
  Connected shows Last successful sync and Reconnect / Disconnect. ATTACK FIRST: before today's login the orchestrator
  saw `/api/broker/status` answer `live_market_data: connected` while `/api/market/indices` answered `NOT_CONNECTED`
  with no value; find the code each answer comes from and say whether the status can claim live data that is not
  flowing (e.g. state read from a stored session row rather than the running socket). Also: `last_successful_sync` was
  null while account_connection was connected - is that what AC-4 requires?
- AC-5: automatic reconnect inside a valid session, revalidate + resync, never places an order; cannot renew the daily
  session. Prove from code + tests; the live drop is `live check pending` unless a test fakes the drop faithfully.
- AC-6: no password/PIN/OTP field or request anywhere (frontend forms, request models, logs).
- AC-7: expiry of the Kite session never deletes identity, strategies or entitlements: find the expiry path and confirm
  it touches only the session/token rows.
- AC-8: Disconnect keeps strategies, history, entitlements, account; live data, positions, orders, margin, execution
  unavailable until reconnect. From code + tests ONLY (do not press Disconnect).
- AC-9: tokens stored only through the official mechanism, encrypted at rest; no token in logs, URLs, responses; check
  the token store and log calls.

Why Opus: Tier A group (REQ-015 auth/tokens); adversarial checks across backend, frontend and a live system.

## Return (this exact shape; the orchestrator writes the evidence files from it)
A JSON array, one object per AC: `{"row": 1|2, "req": "REQ-001", "ac": "AC-1", "result": "pass" | "fail" |
"partial" | "live check pending" | "deferred", "commands": "<exact commands/requests you ran>", "observed": "<what
came back, file:line>", "attack": "<what you tried to break and what happened>"}`. Then, under 250 words: every fail /
partial with the smallest fix (file:line), and anything you could not check and why. Each claim you make rests on a
command you ran in this session; say "unverified" where it does not.
Budget: 40 min wall-clock, 70 tool calls
Report: evidence-table
