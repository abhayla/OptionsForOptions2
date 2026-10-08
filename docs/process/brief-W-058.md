# Builder brief: W-058 Kite login callback and encrypted broker-token storage

Core: a Kite request token from the owner's login becomes an access token that our callback stores only as
ciphertext, and the broker adapter decrypts it for an authenticated Kite call.
Proof (step 1, on fakes; the live owner-login proof is run by the orchestrator later): a test drives the real callback
route with a fake Kite exchange returning a known access token, then asserts (a) the stored row holds no byte
sequence equal to the access token, the request token or the checksum, (b) every captured log record from every
logger, the response body, headers and cookies contain none of the three, (c) the adapter returns the original token
from the stored row.

Why Opus: Tier A - secrets at rest, an auth flow and a database migration.
Budget: 60 min wall-clock, 80 tool calls. Do STAGE 1 (domain) fully and commit before STAGE 2; at budget stop after a
commit and report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`).
Tier: A.
Class: broker-token exposure - any path by which the Kite access token, the request token or the checksum is stored
in plaintext, logged, or sent to a browser.

## Spec basis
- REQ-015 AC-6: "The platform never asks for the user's Zerodha password, PIN or OTP; Zerodha authentication happens on Zerodha's
  side and is separate from platform login."
- REQ-015 AC-7: "Zerodha authorization is treated as temporary (about one day; re-authentication daily); its expiry never
  deletes identity, strategies or entitlements."
- REQ-015 AC-9: "Broker tokens are stored only through the official integration's secure token mechanism."
- REQ-063 AC-5 (token clause): "broker credentials are never stored beyond the official secure-token
  mechanism."
- spec/testing/core-invariants.md section 4: the access token is encrypted at rest and never logged (paraphrase).
- ADR-053: "When a user's Zerodha session has ended (it is logged out every day)" monitoring pauses visibly.
- Copy from: legacy-reuse row 9 (`app/api/routes/auth.py:60-175`, REFERENCE: the flow only, the legacy stored the token
  in plaintext) and `app/utils/encryption.py` (REFERENCE: use a dedicated key, not one derived from `JWT_SECRET`); pin
  `cryptography==46.0.3` from algochanakya@bf9faf7 `backend/requirements.txt` (ADR-047).
- Q210 is open (whether each user brings their own Kite app): the api key and secret come from ONE credentials source
  behind the adapter; V1 uses the platform's configured app (ADR-051).

## Start
- Your worktree starts from main. Copy `work/W-058.md` and the `W-058: 4a` line of
  `docs/process/coverage-stages.yaml` from the main checkout D:\Abhay\Ventures\OptionsForOptions2 (Read them) into
  your branch `build/W-058-kite-login` as your first commit.
- Read `backend/ofo_app/alembic/versions/0005_contract_lifecycle.py`, the allowlist chain helper it uses and
  `tests_app/test_alembic_migration_guard.py` before writing the migration; follow the same pattern.
- W-024 (in flight) adds a CI scan that forbids attribute assignment on anything except `self`/`cls` and forbids
  `setattr`/`vars`/`globals`/`__dict__` in backend/ofo: write W-058's backend/ofo code to that rule now.

## STAGE 1 - domain (backend/ofo/broker/, standard library only)
- `session.py`: a broker session's lifecycle - CONNECTED -> EXPIRED (Kite answered TokenException, or the expected
  expiry passed) or DISCONNECTED (user action). `expected_expiry(login_at)` = the next 06:00 IST after login, labelled
  in its docstring as an EXPECTATION to be confirmed by the 2026-10-09 measurement (F-32); Kite's own TokenException
  always wins. The lifecycle API takes and returns only session data: it has no parameter or import that reaches
  strategies, accounts or entitlements (a test asserts the module imports nothing from those packages).
- `kite_auth.py`: the adapter port - `login_url(api_key, state)` (`https://kite.zerodha.com/connect/login?v=3&api_key=..`
  plus `redirect_params` carrying the state), `checksum(api_key, request_token, api_secret)` = SHA-256 hex of the three
  concatenated (Kite docs; proven live 2026-10-07 in docs/research/kite-proof-2026-10-07/kite_core_proof.py), and a
  `KiteAuthPort` protocol with `exchange(request_token) -> access_token` that the app implements.
- Tests in tests/broker/ (AC-7): every transition; expiry never produces a call into any other store; expected_expiry
  across midnight, a login before 06:00, a weekend login.

## STAGE 2 - app (backend/ofo_app)
- Settings: `KITE_API_KEY`, `KITE_API_SECRET` (SecretStr), `KITE_REDIRECT_URL`, `BROKER_TOKEN_KEY` (SecretStr, 32 bytes,
  url-safe base64). The broker routes refuse to start without a valid key; never derive it from another secret.
- Migration `0006_broker_sessions` (down_revision 0005): id, user_ref TEXT, broker CHECK ('zerodha'), token_ciphertext
  BYTEA NULL, key_id TEXT, started_at (database clock), expected_expiry, ended_at NULL, end_reason CHECK in
  ('expired','disconnected','replaced'); at most one active row per (user_ref, broker) (partial unique index); app role
  SELECT, INSERT, UPDATE on (ended_at, end_reason, token_ciphertext) only, no DELETE. Ending a session sets
  token_ciphertext to NULL in the same statement (the token is destroyed, the row kept).
- Encryption: AES-256-GCM (`cryptography` AESGCM), 12-byte random nonce stored with the ciphertext, associated data
  = `user_ref|broker|session id`, so a ciphertext copied to another row fails to decrypt.
- Routes: `GET /broker/zerodha/login` -> 302 to Kite's login URL with a state value (random, single use, 10-minute life,
  kept server-side); `GET` on the path of `KITE_REDIRECT_URL` (`/kite/callback`) -> validates state, exchanges, stores,
  then 302 to a fixed frontend path with NO token or query in the URL. The access log must not record the callback's
  query string (a logging filter that drops it, tested by capturing uvicorn's access logger).
- Every Kite answer state and what it does (B4 d): status=success with request_token -> exchange; status missing or
  not "success" (the user cancelled) -> no row, fixed message "Zerodha login was not completed"; request_token missing ->
  same; state missing, unknown, reused or expired -> refused, no exchange call; exchange HTTP 200 with access_token ->
  store; HTTP 200 without access_token -> refused, nothing stored; 403 TokenException (expired request token) and 400
  InputException (bad checksum) -> refused, nothing stored, error code logged without the body; 5xx, timeout, network
  error -> refused, nothing stored, no automatic retry. A new successful login while a session is active ends the old
  one with end_reason 'replaced'. Each refusal is a fixed message keyed by a code (W-024's catalogue wires them later).
- Adapter read: `access_token_for(user_ref)` returns the decrypted token of the active session or None; a Kite
  TokenException on any call marks the session EXPIRED (ciphertext NULL).
- Tests in tests_app/ (real PostgreSQL in CI, skip with reason locally): `test_kite_login.py` (AC-6: the flow never
  asks for or accepts a password/PIN/OTP field - the routes take no such parameter; every answer state above),
  `test_broker_token_store.py` (AC-9: the step-1 byte search on the row, logs, body, headers, cookies; AAD binding;
  ciphertext NULL after expiry/disconnect/replace; strategies and entitlements rows unchanged after each end).

## Standing items (run-discipline B4) and reviewer checklist
- Mutation tests FIRST on each guard, each must go red: store plaintext instead of ciphertext; drop the AAD; allow a
  reused state; keep ciphertext after end; remove the access-log filter; derive the key from another secret.
- Fail closed: any error between exchange and commit stores nothing; an undecryptable row is treated as no session.
- Expected values from Kite's documented formats and the spec, never from running the code.
- Kit CI stays green: tests/ imports no app packages; no wall-clock asserts.

## Rules
- Do not edit kit files or spec/. Never write `evidence/`. No real secrets anywhere; tests use generated keys.
- Run the domain suite and `python -m pytest -c pytest-app.ini -q` before finishing (DB tests skip locally; say so).
  Long output to a log file, tail only.
- Commit; do not push. Report worktree path, branch, commits and the mutant table.
