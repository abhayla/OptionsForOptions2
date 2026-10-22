# W-1xx: Background workers that never place an order, and the one Notifier client (REQ-115, REQ-116)

Common brief: docs/process/builder-brief.md (read it first; this file is the item part only).

Core: a worker rebuilds every active strategy's monitor from the database within 60 s of a restart and a crash in the middle of a run never sends the same alert twice.
Proof: run the worker against the recorded replay with two tracked strategies, kill -9 it mid-run, restart, and read the job-run table: the monitors are rebuilt in under 60 s and the alert_event for the same (job, user, strategy, snapshot) exists once; then POST one P2 event with a derived dedupe key to a local stand-in HTTP server that checks the exact gateway request shape. Live window: one event to the real gateway under a silent-drill project (owner-provisioned, see Open).

Tier: A (a job that runs for every user's strategies and holds the Notifier key; PR 1 of 2 is the migration alone)

Spec basis:
REQ-115 AC-1: "run as worker jobs, not inside API requests"
REQ-115 AC-2: "No worker module can reach an order-placement or basket-send call"
REQ-115 AC-3: "On start, the workers rebuild every active strategy's monitor from the database"
REQ-115 AC-4: "While a strategy's inputs are stale or the feed is disconnected (ADR-015, REQ-114), its rule actions are paused"
REQ-115 AC-5: "Each job run is keyed (job, user, strategy, trading day or snapshot time) and stored"
REQ-115 AC-6: "When the workers are down or late (no heartbeat for 2 minutes)"
REQ-115 AC-8: "Schedules use the platform's IST clock and trading calendar (ADR-119)"
REQ-115 AC-9: "One job's failure is isolated"
REQ-116 AC-1: "One client module sends every outbound message (WhatsApp, email, push, Telegram) to the shared Notifier"
REQ-116 AC-2: "An alert is written to the database as an event in the same transaction as, or after, the record it reports"
REQ-116 AC-3: "The dedupe key is derived from the event (strategy, condition, trigger record id)"
REQ-116 AC-4: "The in-app alert is stored and shown whatever happens to the outside channels"
REQ-116 AC-6: "No generic outbound webhook to user-supplied URLs exists"
ADR-165 (6): "background monitoring"

Copy from: none for the worker (new); the existing script pattern backend/ofo_app/history_finalize.py (`python -m` entry, database clock) and backend/ofo_app/catalogue_load.py are the job shape to follow. Notifier thin client: the Notifier project's clients/notify.py (zero-dep, GLOBAL.md section 2 'Integrate a new app'); locate it with Glob under D:\Abhay; if absent write a stdlib urllib client of the same shape. Never copy a key.

Sensibull screens: no Sensibull equivalent in the study for background workers or the gateway; the visible alert behaviour of Sensibull in the study is the Conditional Exits / Alert Triggers feature (catalogue-raw.md 'What's New', Positions page): reference only, it is a Zerodha ATO order feature and out of scope.

Multi-broker review (read D:\Abhay\Ventures\competitors\multi-broker-architecture\2026-10-21\INDEX.md first): L9 (background jobs and reconciliation cadence) and trap T6 (an approval gate that fails open): a worker that cannot decide pauses, it never fires; trap T4 (fixed order tag): not applicable, no order tag is written.

## What to build
PR 1 of 2 (own PR, migration only): tables job_runs (job, user_id, strategy_id, day_or_snapshot, status, unique key on those four), alert_events (id, strategy_id, condition, trigger_record_id, type, created_at, payload limited to the type's allowlist), alert_deliveries (event id, channel, state in sent / not delivered / not attempted, attempts, last_at). Take the next free migration number; alembic guard `python scripts/alembic_migration_guard.py`.
PR 2 (this brief's code):
1. backend/ofo_app/workers/ (new package): scheduler on the platform IST clock and trading calendar (backend/ofo/market_calendar.py); non-trading day = job records 'skipped' (AC-8). Jobs: rule evaluation and status colours (REQ-041/043, built in D2), periodic reconciliation (REQ-060 AC-1 via backend/ofo/reconciliation/triggers.py plan_run), end-of-day history finalise (backend/ofo_app/history_finalize.py), the daily instrument refresh (callable from C4), alert dispatch. Entry `python -m ofo_app.workers.main`.
2. Rebuild on start from the database: definition, active version, rules, last evaluation, last alert per condition, within 60 s; a test stops the worker mid-session, restarts it and compares (AC-3).
3. Stale or disconnected inputs: rule actions paused, nothing fires, no alert claims a trigger, strategy shows 'Monitoring paused' (AC-4; text from backend/ofo/marketdata/disconnect.py). Heartbeat row every 30 s; no heartbeat for 2 minutes = every affected strategy shows 'Monitoring paused' (fail closed) and ONE alert to the platform owner (AC-6). Session expiry at 06:00 IST = monitors pause with 'Monitoring paused - reconnect Zerodha' and one reminder that trading morning (AC-7).
4. Idempotent runs: the unique key makes a re-run after a crash a no-op for alerts and results (AC-5). Exception in one strategy's evaluation is recorded with the strategy id and the others continue (AC-9).
5. Repo test: no module under workers/ imports the order door, the basket builder or any Execute/return route; allow-list of importable modules per worker, not a deny list (AC-2; REQ-115 AC-2 second sentence about the trigger door REQ-100/REQ-101 is out of scope: no trigger door exists).
6. Notifier client backend/ofo_app/notifier_client.py: one module; gateway address and key from GLOBAL.env via OFO_GLOBAL_ENV (same loader as scripts/orchestrator/db_run.py), never printed or logged, in-memory only; builds {project, severity, title, body, type, dedupeKey}; title/body from the reviewed catalogue, allowlist fields only, no token or Kite credential (AC-5); dedupe key = hash of (strategy, condition, trigger record id) (AC-3). Dispatcher job sends events not yet delivered, resend at most 3 times over 10 minutes with the same key; per-channel delivery state saved and shown in the alert's detail (AC-4). A repo scan: no outbound HTTP to a user-supplied URL (AC-6).

## AC status (main plus open PRs, 2026-10-21)
| AC | Status | Where |
|---|---|---|
| 115 AC-1..9 | missing | no worker, job or scheduler module exists (ls backend/ofo_app: none); REQ-115 not referenced anywhere |
| 116 AC-1..6 | missing | 'notifier' appears only in catalogue_load.py (a comment) and one test |
| evidence | none | evidence/ holds only README.md |

## Every answer state of each outside system
Notifier (POST /notify on the shared gateway, GLOBAL.md section 2 'Notifier gateway'; returns 202 at once, async dispatch with its own 3x retry, ~2 s client timeout, same dedupeKey inside the 30-minute cooldown is suppressed): 202 (stated) = sent, delivery state 'sent'. 4xx bad key or validation (failed, permanent) = never retried, delivery state 'not delivered', logged without the key. 5xx or timeout (failed, transient) = resend with the SAME dedupe key at most 3 times over 10 minutes, then 'not delivered'. Connection refused (gateway down) = 'not delivered'; the host app and the in-app alert are unaffected ('A dead gateway never breaks the host app'). Duplicate suppressed inside the cooldown (ambiguous: still 202) = counts as sent. Channel not configured for the project, or recipient not in the fail-closed allowedRecipients (absent / routed []) = 'not attempted'. Body over 4000 chars or title over 500 (invalid) = truncated by the catalogue template before sending, never by the gateway. Database: the alert event row is written first; a failed write sends nothing.
Worker inputs: Kite feed stale (failed) = paused; strategy with no rules (empty) = monitored for detections and health, no rule actions (D2/D3); tracked strategy deleted mid-run (not found) = job records the strategy missing and moves on; clock skew between worker and database (ambiguous) = database clock decides (finding request-clock-for-database-stamped-fact).

## Attack cases (reviewer: hands-on first)
- kill -9 between 'alert event written' and 'dispatch sent': after restart exactly one delivery attempt chain, one dedupe key.
- Two workers started at once (shared lock with the owner session recorded, run-discipline E2): the second refuses.
- Worker module imports ofo_app.routes.execute indirectly through a helper: the allow-list scan goes red.
- Notifier key appears in a log line, exception text, alert payload or openapi.json: red.
- Heartbeat stops for 119 s: no alert; 121 s: exactly one.
- Saturday and an exchange holiday: every job 'skipped', none runs.
- Alert body containing a rupee figure not on the type's allowlist: refused by the template.

Threat model: in scope: workers reaching an order call, duplicate alerts after a crash, a secret in a message, a stuck job silently freezing the monitors; out of scope: a hostile gateway, forged code objects (ADR-098), per-user WhatsApp recipients (launch scope).

Findings checked: fill-not-exactly-once, shared-inflight-marker-without-owner, liveness-from-a-file-nobody-deletes, request-clock-for-database-stamped-fact, wall-clock-assertion-flakes-under-load, secret-filter-by-key-name, state-with-no-working-exit, last-live-answer-kept-after-drop, guard-as-forbidden-list

Standing items: (a) applies: each job pass inside the worker's time window reuses a small per-job reservation cap, never the whole remaining window; a test shows the rule-evaluation pass still runs when the reconcile pass is slow. (b) applies: if the worker adds a non-builtin import to a CI step it runs after the install step. (c) applies: the worker import allow-list names the order door by import source, fails closed on re-exports, renamed imports and same-named local functions. (d) applies: Notifier and database states above.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Targeted tests: tests_app/test_workers_*.py (new), tests_app/test_notifier_client.py (new), tests/test_worker_import_allowlist.py (new), tests_app/test_history_finalize*.py, tests/reconciliation/test_triggers*.py, tests_app/test_catalogue_load_command.py
Rules: no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR (the one exception: a changed API model regenerates docs/api/openapi.json and is registered in tests_app/test_response_door.py, per builder-brief.md).
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Open
Open: business: the Notifier needs an `ofo2` project block in /root/notifier/config.yaml plus its key (provisioning is owner-only; GLOBAL.md: the validated key lives in the Notifier .env as NOTIFIER_KEY_<PROJECT>). Owner input: add the project (recommend a silent-drill project first, routed to [], then real routing) and put the key in GLOBAL.env. Until then the builder uses the local stand-in server.
Open: technical: the gateway is an owner-notification service (WhatsApp allowedRecipients is the owner's number only); end-user recipients are a launch-scope item. In this scope the only user is the owner, so the shared gateway is enough. Recorded, no question.
Open: technical: the 06:00 reminder (AC-7) and the owner alert (AC-6) use the same client; severity P1 for the owner alert, P2 for the reminder.
Live window needed: AC-7 reminder and one real Notifier event.
