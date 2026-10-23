# Row 6: REQ-048 Market-data pipeline (W-134, builder sequence chunk 1, Tier A, size S: ~5 files)

Common brief: docs/process/builder-brief.md (Budget hard stop; scratch-copy mutations; full changed test files; fix
lint as you go). Expected (row-review): ~60 min / ~350k tokens (measure 2 + build 30 + verify 20 + orchestrator 10).

Core: a price reaches a screen only through the server's stages, and no browser asset or server reply carries a
vendor host, key or token.
Proof: step 1 is the bundle scan run on a real `npm run build` output of this branch (frontend/dist) plus the recorded
frames replay (`tests/fixtures/kite_ws/frames-2026-10-08-092000-10s.bin.gz`) through the stages to a socket push; the
scan must find zero vendor hosts/keys today, and a planted one must turn it red.

Spec basis: REQ-048 AC-1: "Data flows Vendor → Market Data Gateway → Normalization → fast cache → internal event stream
→ Option Chain / Strategy / Adjustment engines → platform WebSocket → browser." REQ-048 AC-5: "Browsers never connect to
a vendor, never hold vendor credentials, never own authoritative business rules and never decide execution
eligibility (T1 #176)." AC-2, AC-3, AC-4 are built (measure 2026-10-22: `provider.py:33-69`,
`test_provider_replaceable.py`, `test_fanout_replay.py`) and are re-verified, not changed.
Copy from: legacy-reuse map rows for REQ-048, appended below by copy_from_check.py (act on each).

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`. Commit with
`git add <paths>` (never `-A`); do NOT push. DB tests (if any) through
`python D:/Abhay/scratch/ofo2-builder-sequence/fresh_launch.py D:/Abhay/Ventures/OptionsForOptions2-builder-reqs python -m pytest ...`
(a throwaway database). Scratch:
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\cdc8b776-da99-4858-844d-ba9899512551\scratchpad\row06`.

## Measured starting state (2026-10-22, head 11e5546f)
Stages exist: provider (`ofo/marketdata/kite_provider.py`, `provider.py`), normalisation (`quote.py`, `kite_frames.py`),
latest-quote store (`feed_health.py:130`, in-process - the "fast cache" stage while one process serves; row 9 REQ-113
moves the feed to its own process and owns the shared cache), event stream (`fanout.py`), pushes (`ofo_app/live_push.py`,
`routes/chain.py`, `routes/indices.py`) behind the response door (`errors.py:436`). Vendor-host lint
(`frontend/eslint.config.js:9`, `frontend/tests/vendor-host-lint.test.js`); same-origin socket URL tested. Missing: a
test naming the stage order; a scan of the BUILT bundle and of server replies for keys/tokens; a test that the server
ignores a browser's own "eligible/executable" claim.

## What to build (orchestrator decisions, technical)
1. `tests/marketdata/test_pipeline_stages.py`: the recorded frames go provider -> normalised quote -> latest-quote
   store -> fan-out -> a subscriber, asserting each stage's output type and that no stage is skipped (a subscriber
   cannot read the provider directly: import-graph check as an allow-list of which module may import which stage).
2. Bundle + reply scan, as an allow-list (finding guard-as-forbidden-list, row-review R8): `frontend/dist` after
   `npm run build` (in CI the app job builds it; locally build once) and the JSON of every `/api` response model in
   `docs/api/openapi.json` may contain only hosts on an allow-list (this site's own origin, the Kite basket/login pages
   the order path and login need - name each with its reason); any other vendor host, and any value shaped like a Kite
   api key / access token / secret field name, is a finding.
3. Execution eligibility: a test that every request model that leads to an execution decision has `extra="forbid"`
   (or equivalent) so a browser-sent `eligible`, `executable`, `tradable` field is refused, and that the decision comes
   from the server's gate.

Attack list: (each names its test file)
1. A planted vendor host (`wss://ws.kite.trade`, `api.kite.trade`) or an `api_key=...` in a built bundle file -> red
   (`frontend/tests/bundle-secret-scan.test.js` or `tests/test_bundle_secret_scan.py`).
2. A planted `access_token` field in a response model -> red; the real openapi -> green (same file).
3. A browser request carrying `eligible: true` to the execute and planned-entry routes -> refused, decision unchanged
   (`tests_app/test_browser_never_decides_eligibility.py`).
4. A module outside the allow-list importing the provider directly to feed a screen -> red
   (`tests/marketdata/test_pipeline_stages.py`).
5. The recorded frames through every stage reach one subscriber with the same LTP the frame carried
   (`tests/marketdata/test_pipeline_stages.py`).
6. A second provider behind the adapter -> identical subscriber output (`tests/marketdata/test_provider_replaceable.py`, re-run).

Standing items: (a) n/a: no time-budgeted job; (b) the bundle scan needs `npm run build` output: in CI it runs after
the frontend build step, and the test skips with a named reason (not silently) when `frontend/dist` is absent locally;
(c) both scans are allow-lists, discover files and fail closed on a file they cannot read; (d) n/a: no other system's
answer is decided on.
Threat model: in scope - vendor host/credential in a browser, browser-decided eligibility, a screen fed around the stages; out of scope - a compromised CDN.
Findings checked: guard-as-forbidden-list, caller-supplied-verdict-trusted
Reviewer checklist: allow-lists with a reason per entry; planted cases red; the stage test uses the real recorded
frames; extra-field refusal on every execution-decision model; every changed test file in full; scratch-copy mutation
list; no new duplicated literal; reuse the existing helper; ruff baseline must not rise; targeted tests only; no
regenerated files (except openapi.json if a model changes).

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 30 min wall-clock, 40 tool calls
Report: evidence-table

## Legacy map rows (copy_from_check.py)
Rows of the legacy-reuse map that name this brief's requirements. Act on each:
COPY/ADAPT -> use it (provenance header) or write in the report why not; REFERENCE -> read
before designing; SKIP -> do not re-survey.

| `app/websocket/manager.py` (520), `routes.py` (181) | REFERENCE | connection manager pattern; `ticker/router.py` is the better base | REQ-048 |
| `ticker/adapter_base.py` (273), `ticker/router.py` (377) | ADAPT | row 1; router gets auth + entitlement checks | REQ-048 |
| `ticker/pool.py` (414) | ADAPT | row 1; drop `can_auto_refresh`/`refresh_broker_token` (`:23-24`) and platform credentials | REQ-048, REQ-050 |
| `market_data/market_data_base.py` (520) | ADAPT | trim to Zerodha, behind our gateway | REQ-048 |
| `market_data/kite_adapter.py` (440) | ADAPT | user's own session token only, server-side | REQ-048, REQ-053 |
| `src/composables/autopilot/useWebSocket.js` (505) + test (832) | ADAPT (P3b) | token off the query string (`:53`); decouple from autopilot | REQ-043, REQ-048 |
