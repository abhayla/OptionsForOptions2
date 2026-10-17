# Builder brief: W-105 A basket return on the shared redirect URL lands on a "Check with Zerodha" page, never a login error (Tier A: the login callback, auth)

Core: Kite returns the browser from a basket to the REGISTERED redirect URL, the same one login uses, "exactly like
login" (https://kite.trade/docs/connect/v3/basket/: "Once the user is done placing orders, the basket will redirect
back to your registered `redirect_login` along with a `request_key`, exactly like login."). Today
`kite_callback` (`backend/ofo_app/routes/broker.py`) consumes `state` first and, with none, redirects to the refusal
page `broker_state_invalid` - so an owner who just placed real orders sees a login error. Fix: a callback hit that
carries NO `state` query parameter at all is a basket return: redirect to `{frontend_origin}/execution/returned`
WITHOUT touching the state store, WITHOUT exchanging `request_token`, WITHOUT storing anything. A hit WITH a `state`
parameter keeps today's login path exactly (invalid state -> `broker_state_invalid`).
Proof: route tests with the callback's real query shapes: no-state `?status=success&request_token=abc&type=basket`
-> 303/307 to `/execution/returned`, the fake `KiteAuthPort.exchange` called 0 times, broker session rows unchanged,
the state store untouched; `?state=<forged>&status=success&request_token=abc` -> `broker_state_invalid` as today; a
real login round trip unchanged.

Tier: A. Model: opus.
Budget: 45 min wall-clock, 50 tool calls. HARD limit: at call 47 commit, push, report.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under 250 words, `git status --short` empty,
each new guard with its killing test (mutation-run).
Copy from: none - a branch at the top of the existing callback.
Findings checked: redirect-bare-path-lands-on-callback-host, caller-supplied-verdict-trusted, secret-filter-by-key-name, guard-without-killing-test
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py

## Spec basis
- REQ-073 AC-3: "When the user returns from Kite, the platform reads the actual order states and positions from Zerodha and
  reconciles them"
- ADR-097 (2): "no app code or assistant action sends an order" - the landing page never acts by itself.

## Build
1. `broker.py`: a module constant `BASKET_RETURN_FRONTEND_PATH = "/execution/returned"` beside
   `CONNECTED_FRONTEND_PATH`; at the top of `kite_callback`, `if state is None:` -> a typed redirect (the same
   `typed_redirect` helper and response model family the callback already uses; add a `BrokerRedirectOut` value if the
   model is a closed set) to `{frontend_origin}{BASKET_RETURN_FRONTEND_PATH}`. No query parameter of the incoming
   request is copied into that URL (the request_token must never travel to the browser's address bar or a log).
2. The callback log filter (`CallbackQueryFilter`) must still redact `request_token` on the new path - test it.
3. An empty string `state=` is NOT absent: it goes down the login path and is refused as today (test both).
4. Tests in the existing callback test file (find it: grep `tests_app/` for `kite_callback` or `broker_state_invalid`).

## Reviewer checklist (attack cases first)
- Attack: no-state hit with `request_token` -> exchange never called (count on the fake), no DB write (count rows).
- Attack: `?state=&request_token=x` -> refused `broker_state_invalid`, not the landing.
- Attack: the redirect target carries none of the incoming query (no token leaks into the URL).
- Attack: the frontend origin is the configured one, never a Host-header value (finding redirect-bare-path-lands-on-callback-host).
- A login with a valid state still connects (existing tests green).

## DB
Not the shared-DB holder (W-103 holds ofo_test). The callback tests that need the DB run in CI; locally run the
non-DB tests, the Tests line and `python scripts/ruff_ratchet.py`.

## Rules
- Branch `build/W-105-basket-return` from origin/main. Work card `work/W-105.md` (frontmatter shape of
  `work/W-100.md`; requirement_ids [REQ-073]; tier A; depends_on [W-095]; tests_required
  ['AC-3: <the callback test file you used>']) and `W-105: 4b` in `docs/process/coverage-stages.yaml`.
- The frontend page at `/execution/returned` is built by W-104 (another builder); you only redirect to it.
- Never copy .env; no PR. No kit or `spec/` edit, no `views/`, no `evidence/`. Common rules: `docs/process/builder-brief.md`.
