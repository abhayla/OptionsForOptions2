# Brief: GC-MU step 2 - #517 / REQ-048 AC-5 redesign: reply-field inventory, reviewed build inputs, value canaries, exact-URL scan

Core: a checked-in inventory of every reply field path, generated from the live app's routes and sockets, asserted equal both ways - so a new field cannot leave the server without a reviewed line.
Proof: step 1 of this brief - the generator runs on `create_app()` and the both-ways test is green; adding a planted reply field `token` makes it red.
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Class: guard-as-forbidden-list (5th occurrence) - credential guards written as name lists; before: 13 round-2 escapes pass (reply fields token, auth_token, secret, kite_session; bundle enc_token, kite_session, Authorization header concat, secret:value; URLs http://127.0.0.1:8000, https://[::1], kite prefix traversal; any 8-char chunk suffix); after: each escape is a planted failing test that the new guards turn red, and the primary guards are allow-lists (inventory, reviewed VITE list, exact URLs).
Round: 1/2
Findings checked: guard-as-forbidden-list, privilege-guard-as-denylist
Spec quote: REQ-048 AC-5 "Browsers never connect to a vendor, never hold vendor credentials, never own authoritative business rules and never decide execution eligibility"
Threat model: in scope - a developer mistake that adds a reply field, header, cookie, build variable or literal URL; a credential reaching the browser through a reply, a header/cookie or the build. Out of scope - deliberate encoding (base64, computed strings), a compromised dependency, browser extensions; navigation to Kite's own pages (login redirect, offsite basket form POST with the PUBLIC api_key) is allowed by ADR-054 and is not a connection.
Sensibull: n/a - security guard, no screen.
Reference: none - searched reply inventory, bundle scan (no screen in the study)
Copy from: not used - the response door and scans were built new in chunk 1 (#525); the REQ-048 map rows `app/websocket/manager.py` (520), `ticker/adapter_base.py` (273), `ticker/pool.py` (414), `market_data/market_data_base.py` (520), `market_data/kite_adapter.py` (440), `src/composables/autopilot/useWebSocket.js` (505) cover the feed/socket layers, not the reply inventory or bundle scan this brief changes.
Tier: A (fresh Opus verifier follows; mutation tests required).

## Design (independent designer review 2026-11-01, Opus, before build)
Already in place, keep: one serializer `emit` refusing aliases/extra fields (`backend/ofo_app/api_models.py:18-21, :347`); every route a `ClosedRoute` with an `ApiModel`, sockets `ClosedWebSocketRoute` (`tests_app/test_api_models.py:22-35`); dicts and raw Responses refused (`backend/ofo_app/errors.py:319-336`); closed header list (`errors.py:109-110`); `APP_MODELS` both-ways (`tests_app/test_response_door.py:335, :510-518`). The designer found the real leak path is a VALUE, not a field name: `Identifier` allows up to 64 letters and digits (`api_models.py:10`), so a 32-character token fits any reviewed field - hence the value canaries (item 3).

Decisions taken (technical, recorded here; none changes what a user sees):
- D1 `PlaybookBody` (`playbook_body_out.py:33`, `dict[str, Any]`): kept as a reviewed opaque leaf in the inventory, with a reviewer note; the value canary covers it. Not closing its key set (would refuse user-saved playbook keys).
- D2 `VITE_ZERODHA_OPEN_ACCOUNT_URL` (`frontend/src/lib/connectHelp.js:13`): stays a build input on the reviewed VITE list; the exact-URL allow-list gets one reviewed entry for the account-opening page (exact scheme+host+path, query allowed) - a link is navigation, not a connection.
- D3 Content-Security-Policy `connect-src 'self'`: not in this step (depends on how production serves the frontend); file a `deferred` issue with this evidence via `python scripts/orchestrator/gh_issue.py app ... --stage <stage>`.
- D4 navigation to Kite (login redirect, basket POST with the public api_key): settled by ADR-054; keep the existing `ExecuteOut.basket.api_key` path exemption.
- Latent failure `KITE_ORDER_BOOK_URL = 'https://kite.zerodha.com/orders'` (`frontend/src/lib/execute.js:40`, used by `TwoBasketStepper.vue:21`): add it as a reviewed exact URL (a link to Kite's order book) so the scan does not fail the day the stepper is imported; test it is the exact URL.

## Where
Worktree `D:\Abhay\Ventures\OptionsForOptions2-gcmu-door`, branch `build/gcmu-door` (from `build/gcmu`). Commit there only. Never push. `frontend/node_modules` is a junction: never delete it, never run `npm ci`/`npm install`. No `npm run build` (heavy, shared machine): use a tiny planted fixture dist for unit tests; if a real build is needed, say so in the report.

## Do, in order
1. CORE: generator `scripts/reply_inventory.py` walks `create_app().routes`: each route `METHOD path -> Model`, each socket's message models; recurse annotations as `_model_tree` / `_field_type` do; paths like `Model.a[].b{}.c` with leaf type; expand `BasketPost` to its own keys (`basket_post.py:91`: url, api_key, data), the error body to its parts, every header name and every cookie name. Output `tests_app/reply_inventory.py` (checked in); a test asserts equality both ways; every string-capable leaf (Identifier, InstrumentId, CatalogueText, sealed leaves, PlaybookBody) carries a reviewer note. Planted test: a model gaining `token: Identifier` fails until listed.
2. Bundle inputs: `envPrefix: 'VITE_'` set explicitly in `frontend/vite.config.js`; a test asserts every `import.meta.env.*` use in `frontend/src` is on the reviewed list plus Vite built-ins, `process.env` never appears in `src`, no `define`/`loadEnv` in the vite config, no `.env*` file tracked.
3. Value canaries: (a) set the token store to a canary value, run every route and socket through the existing sample harness, assert the canary is absent from every body and header; (b) a bundle check that, given a dist built with non-VITE canary values for every backend credential variable, finds none of them (unit-test it on a planted dist; wire the real build into the existing frontend CI scan step `.github/workflows/app-tests.yml:345` by setting canary env values there).
4. Text scan second layer (`tests/test_bundle_secret_scan.py`): URLs compared exactly on parsed scheme, host, port, path (no prefixes); any `scheme://` token is a URL whatever its host; IPv4/IPv6 literals, userinfo, `..` and `%` in a path refused; the chunk exemption pinned to its source module, not a name regex.
5. One planted failing test per round-2 escape (13, listed in Class) - each red under the new guards. Then guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan`, the changed test files in full (app tests needing a DB via `python scripts/orchestrator/db_run_fresh.py . python -m pytest -c pytest-app.ini tests_app/<file>.py`, one file at a time), ruff on changed files, `python scripts/ruff_ratchet.py`. Logs to a file, tail only.

## Standing items
- One test per item above; a skipped test counts as not run; every changed test file run in full.
- Answer states of the inventory generator: model route, socket route, sealed leaf, opaque leaf, header, cookie, a route type it does not know (fail closed: the generator raises).
- Tier A: at most 5 mutants on a scratch copy (drop one inventory line; widen an exact URL to a prefix; drop the IP-literal refusal; remove the canary check; let the generator skip unknown route types) - each turns a test red.
- Known bypasses (deliberate encoding etc.) in the scan module docstring.
- No new duplicated literal; ruff/mypy baselines must not rise; the inventory file is generated by the script and checked in.
- Commit after each item passes. End the report with the final commit sha on build/gcmu-door.
