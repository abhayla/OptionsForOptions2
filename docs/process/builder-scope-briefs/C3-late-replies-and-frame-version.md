# W-1xx: Late replies and old-version live frames never draw over a newer edit (REQ-119, REQ-133)

Common brief: docs/process/builder-brief.md (read it first; this file is the item part only).

Core: an older answer never replaces a newer one: request 1 then request 2, answered 2 then 1, the screen still shows reply 2; and a live frame for strategy version 2 is dropped while version 3 is on screen.
Proof: frontend unit test plus one backend test with two out-of-order requests against the real outcome route on the recorded replay; then the same ordering on the live websocket frames in a test (REQ-133 AC-4).

Tier: A (live frames carry P&L numbers; the sequence rule gates what numbers a screen shows)

Spec basis:
REQ-119 AC-1: "carries a sequence id that increases per screen; the server echoes it unchanged in the reply"
REQ-119 AC-2: "an older reply is dropped and logged at debug level"
REQ-119 AC-3: "the older in-flight request of the same kind is cancelled in the browser"
REQ-133 AC-2: "The same rule holds on the live socket: a frame computed for an older strategy version than the one on screen is dropped"
REQ-133 AC-4: "Tests cover both defects as classes"
ADR-165 (1): "the Place order / Execute action may be replaced"

Copy from: none - new small module (a sequence-id echo and a monotonic apply rule); legacy has no equivalent.

Sensibull screens: no Sensibull equivalent in the study for request ordering; the visible behaviour is the builder recalculating on every edit: Strategy Builder 010-039 and BUILDER PASS 2 (price-changed marker, screens 209-211) in catalogue-raw.md.

## What to build
1. Backend: outcome, table, margin routes (backend/ofo_app/routes/outcome.py, strategies.py, and the margin read in backend/ofo_app/outcome_margin.py) accept an optional `seq` request field and echo it unchanged in every reply, including error replies. New ApiModel fields: regenerate docs/api/openapi.json, register in tests_app/test_response_door.py (REQ-119 AC-1).
2. Frontend: one small helper (frontend/src/lib/latestWins.js) per request kind: a per-screen increasing id, apply a reply only if its id is higher than the last applied (AC-2), abort the older in-flight request with AbortController, a cancelled request never toasts an error (AC-3). Numbers show 'updating' while the latest request has no reply (AC-4).
3. Live frames: backend/ofo_app/live_push.py StrategyPush stamps each frame with the strategy version it was computed for; frontend/src/composables/useStrategyLive.js drops a frame whose version differs from the one on screen (REQ-133 AC-2). Test with frames out of order (AC-4).
4. REQ-119 AC-5 (Execute refuses a stale version): out of scope, Execute is off (ADR-165). Mark it 'deferred: order path off' in the PR body; the server-side version check for the tracking route belongs to the tracking brief (C7).
5. 'Waiting for the first live price' (REQ-133 AC-3) is built in C1; do not duplicate it.

## AC status (main plus open PRs, 2026-10-21)
| AC | Status | Where |
|---|---|---|
| 119 AC-1 | missing | grep for sequence_id/seq_id in backend and frontend/src: no hits |
| 119 AC-2 | missing | |
| 119 AC-3 | missing | |
| 119 AC-4 | partial | the table has 'unavailable' cells; no 'updating' state |
| 119 AC-5 | out of scope | Execute off (ADR-165) |
| 133 AC-1 | covered by 119 | |
| 133 AC-2 | missing | live_push.py has no version stamp |
| 133 AC-3 | in C1 | |
| 133 AC-4 | missing | |

## Every answer state of each outside system
Server reply to a request with a seq (stated) = echoed. No seq sent (absent) = reply without seq, the browser treats it as the next id for that kind. Seq lower than one already answered (ambiguous: the server is stateless) = still answered and echoed; the browser drops it. Request fails (failed): the error reply carries the seq, and an older failure never overwrites a newer success. Empty strategy (empty) = normal empty reply with seq. Live socket: frame with no version (absent) = dropped, never drawn.

## Attack cases (reviewer: hands-on first)
- Reply 2 then reply 1 for outcome, table and margin (three kinds): each kind has its own last-applied id, a margin reply cannot block an outcome reply.
- Seq is a string, a float, negative, or 2**63: refused with the typed error, not a 500.
- Frame for version 2 arrives after the user edited to version 3 and before the reply for 3: dropped, number shows 'updating'.
- Aborted request: no toast, no console error, no state change.
- Page reload resets ids: first reply after reload is applied.

Threat model: in scope: out-of-order replies and frames; out of scope: a malicious client forging ids (it can only hurt itself).

Findings checked: last-live-answer-kept-after-drop, state-read-after-await, client-message-resets-rate-limit, sealed-object-mutable-after-seal

Standing items: (a) n/a: no time-budgeted job. (b) n/a: no CI step added. (c) n/a: no static detector added. (d) applies: reply states above, each tested.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Targeted tests: tests_app/test_outcome_*.py (grep), tests_app/test_response_door.py, tests_app/test_live_push*.py, frontend/tests/ for the new helper and useStrategyLive, frontend/e2e if a spec names a changed screen text
Rules: no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR (the one exception: a changed API model regenerates docs/api/openapi.json and is registered in tests_app/test_response_door.py, per builder-brief.md).
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Open
Open: technical: seq is optional so existing callers keep working; proposal: a request without seq is applied in arrival order. No business questions. No live window needed (recorded replay is enough).
