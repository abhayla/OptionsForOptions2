# Builder brief: W-070 - response door part 2: minted headers, frozen send (#197, REQ-065 AC-2)

Core: a door response puts on the wire ONLY the body, header names AND values, and status the door minted; nothing
a route or an exception sets (after or at construction) reaches the wire.
Proof (your step 1, red first, committed as xfail-strict before any fix), through the real app (`create_app()`) on
main dbe0786: (a) a ClosedRoute endpoint returning `r = respond(model, 302); r.headers["location"] =
"https://evil.example/steal"` answers 302 to that host; (b) a ClosedRoute endpoint raising
`HTTPException(401, headers={"WWW-Authenticate": SENTENCE})` echoes the sentence. After the fix: (a) 500 internal
with no `location` header; (b) 401 whose `www-authenticate` equals the `WWW_AUTHENTICATE` constant.

Tier: A. Model: sonnet. Budget: 75 min wall-clock, 80 tool calls. Commit after each step; at budget stop after a commit
and report done / not done / next command. Report: evidence-table (`| Claim | Evidence (command run this turn) |`),
under ~300 words, plus the guard -> killing-test list.
Worktree: `C:\Abhay\Ventures\OptionsForOptions2-W-070`, branch `build/W-070-door-headers` (already created; work only
there; commit there; do NOT push).
Copy from: none - extends this project's own door (W-069); no legacy row covers a response serializer.

## LOAD CAP - this PC's PostgreSQL serves IPODhan PRODUCTION; free RAM is under 2 GB
- Targeted test files only, one at a time. The door files need no DB: `python -m pytest -q -p no:cacheprovider -c
  pytest-app.ini tests_app/<file>.py`. `test_kite_login.py` may need the DB: run it through
  `scripts/orchestrator/db_run.py` (copy `.env` in from the main checkout, delete it after). Never the full app suite,
  never npm/Playwright. Run the full ROOT suite once at the end (`python -m pytest -q -p no:cacheprovider` to a log
  file; read the last line) - the pricing scan lives there.

## Why this round exists (read first)
This is the THIRD round of one class (finding `sealed-object-mutable-after-seal`): round 1 left the body mutable,
round 2 checked header NAMES by predicate but not VALUES. An independent review (2026-10-11, read-only, a different
model) found the actual mechanism: Starlette's `Response.__call__` reads `self.status_code`, `self.raw_headers`,
`self.body` and runs `self.background` at send time (starlette/responses.py:155-167); the door mints only the body and
checks the rest by predicate. The orchestrator confirmed each point in the code:
- `_body` (errors.py:180) merges caller headers OVER the door's constant: `{**NO_LEAK_HEADERS, **extra, **(headers
  or {})}`; `_http_response` (errors.py:311) filters exception headers by NAME only, so the exception's value wins.
- `verify` is resolved on the instance (errors.py:142, 196): `r.verify = lambda: None` disables it.
- `_clear` / `set_cookie` change the response AFTER construction (errors.py:285-289, 334-336).

## Do (in order; every rule below is the review's proposal, accepted by the orchestrator)
1. Red tests (Proof above) plus, through `_run_wrapper` / a raw `Route` as the existing tests do: (i) every name in
   `_DOOR_HEADERS` set to SENTENCE after construction -> refused (parametrised); (ii) `status_code` changed -> refused;
   (iii) `r.background = BackgroundTask(set_flag)` -> refused and the flag stays unset; (iv) `r.verify = lambda: None`
   plus a mutated body -> still refused; (v) `r.init_headers({"x": SENTENCE})` -> refused; (vi) HTTPException(405,
   headers={"Allow": SENTENCE}) -> sentence absent from every header; (vii) `set_cookie` on a SealedRedirect after
   `typed_redirect` -> refused.
2. **Closed header table, minted at construction:** `content-type` fixed `application/json` (ClosedResponse);
   `content-length` = len(body); `cache-control` / `referrer-policy` the existing constants; `www-authenticate` always
   the `WWW_AUTHENTICATE` constant (an exception's value is discarded); `retry-after` digits only, from the door's own
   failure value; `allow` = method tokens re-joined (sorted), each in a fixed method set; `set-cookie` only built from a
   `RedirectCookie` (tighten its name/value to a token pattern; the nonce is hex); `location` only on `SealedRedirect`,
   never on `ClosedResponse`. `_body` and `_http_response` stop copying caller header values.
3. **Freeze and send the frozen copy:** at construction freeze `(status, tuple(raw_headers), body)`; at send require
   equality AND send the frozen copy from the door's own `__call__` (no `super().__call__`), so `background` never runs;
   refuse 3xx/204/304 on `ClosedResponse`.
4. **Verification as a module function** (`_verify(response)`), called at the wrapper and at the seal - never an
   instance method lookup.
5. **Cookies into the constructor:** `typed_redirect(..., cookie=...)` and the refusal path that clears the login-state
   cookie pass the cookie to the constructor; no "refresh snapshot" hook (that would be a new mutation door).
Keep green (parity): a real framework 405 (POST to a GET route) carries `Allow` with method tokens; the Kite login
redirect keeps its Location + nonce cookie; `handle_error`'s refusal still clears the cookie (Max-Age=0); every golden
body in `test_response_door.py` is unchanged.

## Spec basis (quoted verbatim)
- REQ-065 AC-2: "Every user-facing error states what happened, the impact, what is blocked and the next action."
- ADR-003 Q226: "every platform message comes from a
  fixed, reviewed template catalogue with typed slots."

## Reviewer checklist (Tier A; each mutation must turn a named test red)
Names-only compare restored; status left out of the freeze; send from `self.raw_headers` instead of the frozen copy;
background not pinned; `_http_response` copies header values; verify resolved on the instance; `location` allowed on
ClosedResponse; `allow` tokens unchecked; `www-authenticate` taken from the exception; cookie set after construction.
Also: the outside-host redirect and the exception-header sentence are refused through the REAL app, not only through
helpers.

## Out of scope
`_SEAL` being a readable module global (a raw route stamping the scope itself) - note it in your report, do not fix;
#148 MAJOR 2; the outcome route exemption (W-066).

## Checks before you report (each as its own plain command, from the worktree root)
- `python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_response_door.py` (then
  `test_error_boundary.py`, `test_error_boundary_scan.py`, `test_apimodel_closed.py`, `test_api_models.py`)
- `test_kite_login.py` through `db_run.py`; grep `tests_app/` for `typed_redirect`, `set_cookie`, `WWW_AUTHENTICATE`,
  `respond(` and run every hit (finding targeted-tests-miss-dependent-files)
- the full root suite once (log file, last line)
Never pipe a check into `tail`/`head` before a commit (the project hook refuses it).
