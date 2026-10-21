# W-1xx: Alerts page and channels, alert-only rules, and the daily 'does Zerodha agree' report (REQ-062, REQ-042 alert part, REQ-110)

Common brief: docs/process/builder-brief.md (read it first; this file is the item part only).

Core: after market close a job compares the app's stored fills with Zerodha's trade book and positions for the day and writes one report per user: either every difference with both values, or 'Could not check today - <reason>', never 'Matches Zerodha' on a failed read.
Proof: on the recorded replay with a recorded real Zerodha trade book and positions reply (tests/fixtures/, a real fixture, not typed): one agreeing strategy and one with a one-lot difference; the report lists the difference with both quantities and the next action; then a recorded failed read: 'Could not check today'. Live window: run it once after a real close with the owner's session still valid.

Tier: A (REQ-110 compares Zerodha's quantities and prices; the Alerts page and channel matrix part is Tier B)

Spec basis:
REQ-062 AC-1: "V1 channels: in-app, push, email, WhatsApp."
REQ-062 AC-2: "Channels follow the ADR-028 matrix"
REQ-062 AC-3: "Repeated alerts for the same condition are not re-sent without a change"
REQ-062 AC-4: "Users can see active alerts, history and notification settings under Alerts."
REQ-042 AC-1: "When a rule condition is met, the platform does the rule's chosen action: alert only, or alert + prepare the exact multi-leg orders"
REQ-110 AC-1: "A background job (REQ-115) runs once per user per NSE trading day (ADR-119 calendar) after market close"
REQ-110 AC-3: "any difference that REQ-060 treats as a mismatch is also raised there (so it blocks as usual)"
REQ-110 AC-4: "When the run could not read Zerodha (no session that day, session ended, read failed or timed out)"
REQ-110 AC-5: "The report shows no rupee figure the platform computed"
REQ-110 AC-7: "Each run is stored with its time, the user, the strategies checked and the outcome per strategy"
ADR-165 (6): "background monitoring, the Opportunity panel with Before/After (REQ-046) and alerts"

Copy from: none - frontend/src/pages/AlertsPage.vue exists as honest empty states (W-117); reconciliation compare is backend/ofo/reconciliation/compare.py; reads are backend/ofo_app/kite_reads.py (fetch_trades, fetch_positions). Notifier client and workers come from D1.

Sensibull screens: no Sensibull equivalent in the study for an in-app alert centre, WhatsApp alerts or a daily Zerodha-agreement report (grep of catalogue-raw.md finds only the Conditional Exits / Alert Triggers order feature). Closest visible: Orders page tabs and Positions totals (050-053, 'Orders - /orders') for how Zerodha's own words are shown.

## What to build
Prerequisites: D1 (workers, Notifier client, alert_events tables) and C8 (reads, compare) merged; this brief stacks on them.
1. Alerts page (REQ-062 AC-4): replace the empty states in frontend/src/pages/AlertsPage.vue with Active, History and Notification settings backed by alert_events and alert_deliveries; each alert's detail shows each channel's delivery state (sent, not delivered, not attempted) (REQ-116 AC-4). Alerts for tracked strategies say 'Paper strategy' first (REQ-109 AC-8).
2. Channel matrix (ADR-028, AC-2): a table-driven map from alert type to channels, one home, e.g. adjustment opportunity -> in-app + push + WhatsApp (email optional); exit condition reached -> in-app + push + email + WhatsApp; daily summary -> in-app + email. Channels not yet available in this scope (push) are 'not attempted' with a plain reason. 'Order rejected/failed' rows of the matrix are out of scope (no orders).
3. No-repeat (AC-3): an alert for the same condition is not re-sent unless something changed (the dedupe key from D1 plus a change test).
4. REQ-042 alert part: a rule whose chosen action is 'Alert me' creates the alert; the 'prepare the exact multi-leg orders' half and AC-2/AC-4 (hold a stop at Zerodha) are out of scope; an attempt to configure them is refused while Execute is off.
5. REQ-110 daily check: job `daily_agreement` in the worker (D1): once per user per trading day at the configured time (default 16:00 IST) while the day's session is valid; reads trade book and positions in that run (read-only, no order call); compares by tag (ADR-105) the app's stored plans and fills with Zerodha's; per strategy one line per difference kind (list in REQ-110 AC-2: read the full AC); each difference names contract, both quantities or prices as Zerodha reports them (Decimal strings), next action; a REQ-060 mismatch is also raised (so it blocks, via C8's reconcile; the report itself never lifts or sets a block, Q222). No rupee figure the platform computed (AC-5). Failed/timed out/no session = 'Could not check today - <reason>', never retried in a loop (AC-4). Stored per run (AC-7). In-app under Alerts and email through the Notifier as the ADR-028 daily summary; a day with no strategy activity sends nothing (AC-6).
6. WhatsApp: see Open: business (template approval).

## AC status (main plus open PRs, 2026-10-21)
| AC | Status | Where |
|---|---|---|
| 062 AC-1,2 | missing | no channel code; AlertsPage.vue is empty states |
| 062 AC-3 | missing | |
| 062 AC-4 | partial | page shell only |
| 042 AC-1 (alert part) | missing | |
| 042 AC-2..4 | out of scope | order half |
| 110 AC-1..7 | missing | no REQ-110 reference anywhere in backend |

## Every answer state of each outside system
Notifier (POST /notify on the shared gateway, GLOBAL.md section 2 'Notifier gateway'; returns 202 at once, async dispatch with its own 3x retry, ~2 s client timeout, same dedupeKey inside the 30-minute cooldown is suppressed): 202 (stated) = sent, delivery state 'sent'. 4xx bad key or validation (failed, permanent) = never retried, delivery state 'not delivered', logged without the key. 5xx or timeout (failed, transient) = resend with the SAME dedupe key at most 3 times over 10 minutes, then 'not delivered'. Connection refused (gateway down) = 'not delivered'; the host app and the in-app alert are unaffected ('A dead gateway never breaks the host app'). Duplicate suppressed inside the cooldown (ambiguous: still 202) = counts as sent. Channel not configured for the project, or recipient not in the fail-closed allowedRecipients (absent / routed []) = 'not attempted'. Body over 4000 chars or title over 500 (invalid) = truncated by the catalogue template before sending, never by the gateway. Database: the alert event row is written first; a failed write sends nothing.
Zerodha trade book and positions (REQ-110): rows (stated) = compared. Empty both sides on a day with no activity (empty) = nothing sent. Zerodha has rows the app lacks, or the reverse (ambiguous) = difference line with both values. Failed/timeout/session ended (failed) = 'Could not check today - <reason>' (fail closed). Row for an unknown tag (absent) = labelled 'Placed outside this app'. Report run twice for one day (duplicate) = second run replaces nothing silently: both stored with times, the in-app list shows the latest.

## Attack cases (reviewer: hands-on first)
- A failed Zerodha read must never produce 'Matches Zerodha' (mutation: swap the failed branch for the empty branch and a test goes red).
- A non-trading day or after the 06:00 expiry: no run, recorded as skipped.
- Difference of one lot between app and Zerodha: reported with both quantities, and the strategy goes Reconciliation Required through C8.
- The report mentions a platform-computed rupee figure: red.
- Same alert twice in the cooldown: one delivery; changed condition: a second.
- WhatsApp body with a token, a client id or an unlisted field: template allowlist refuses.
- Alerts page shows another user's alert (single owner now, but the query takes the user from the session): test with two users.

Threat model: in scope: false 'agrees' on failed reads, duplicate alerts, secret leakage into messages, an alert page not scoped to the session user; out of scope: Notifier internals, Meta template approval outcome.

Findings checked: trust-broker-status-word, net-only-read-misses-roundtrip, fill-not-exactly-once, resolution-on-stale-broker-copy, secret-filter-by-key-name, rate-gate-on-success-path-only, held-without-platform-fill-invisible-to-ledger, last-live-answer-kept-after-drop

Standing items: (a) applies: the daily check is one job in the worker with its own small reservation; a test shows the monitor pass still runs while the check reads Zerodha. (b) n/a: no CI step added. (c) n/a: no static detector added beyond D1's import allow-list. (d) applies: Notifier and Zerodha states above, each tested.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Targeted tests: tests_app/test_daily_agreement.py (new), tests_app/test_alerts_*.py (new), tests/reconciliation/, tests_app/test_notifier_client.py (D1), frontend/tests for AlertsPage
Rules: no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR (the one exception: a changed API model regenerates docs/api/openapi.json and is registered in tests_app/test_response_door.py, per builder-brief.md).
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Open
Open: business: WhatsApp alerts need a Meta-approved UTILITY template (business-initiated sends) and its wording is what users read: owner approves the template text (use the wati-template-create-and-track and meta-utility-template-approval-probability skills; decision-support wording, ADR-003; Zerodha-AP compliance text from GLOBAL.md, never copied into the repo). Recommended: submit one generic 'Strategy alert: <title>. Open the app for details.' template. Why only the owner decides: it is user-facing wording and a Meta submission.
Open: business: push notifications (REQ-062 AC-1) need a push provider and user consent; not in this scope's 'web at desktop width' (ADR-165 (7)). Recommended: in-app + email + WhatsApp now, push later; owner to confirm.
Open: technical: the gateway sends to the owner only (allowedRecipients); per-user recipients are a launch item. Recorded.
Live window needed: the daily check after a real close, and one real WhatsApp/email alert.
