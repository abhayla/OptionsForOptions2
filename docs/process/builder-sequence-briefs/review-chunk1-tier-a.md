# Chunk 1 close: the one Tier A review (ADR-178), split into three areas read in parallel

Why split: the chunk changes about 5,400 product lines (`git diff --shortstat origin/main...HEAD -- backend frontend/src`:
95 files, +5384/-428). ADR-106 rule 6 sizes a Tier A PR at about 1,000 product lines so one reviewer can read it end to
end; one reviewer over 5,400 lines would skim. The review stays ONE round; it is read by three fresh reviewers, one area
each (orchestrator's technical call, recorded here and in the chunk PR body).

Independent, adversarial reviewers; you built none of it. READ-ONLY: never edit, create, commit or delete a tracked
file. Scratch only in
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\5db71e90-61e3-4f1b-8a6c-a0ee38c54e11\scratchpad\review-a<N>`.
Code: worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`, head given in your
prompt. Diff: `git diff origin/main...HEAD -- <your files>`. Every row in this chunk was already verified on its own
(evidence/W-129..W-144). Your job is what per-row checks miss: interactions between rows, a guard one row added that
another row's code bypasses, a hard-rule break (CLAUDE.md "Hard rules"), and anything on the order path or money path.
Hands-on attacks first (scratch scripts against the real modules with fakes), reading second.

## Area 1: live feed and liveness
Files: backend/ofo_app/feed_bus.py, feed_main.py, kite_ws.py, live_market.py, catalogue_refresh.py,
backend/ofo/marketdata/shared_compute.py, backend/ofo/market_calendar.py, backend/ofo/marketdata/ (changed files),
frontend/src/composables/useStrategyLive.js, useIndexLive.js, frontend/src/lib/sharedStateText.js, dataHealthText.js.
Ask: can any screen show a price as live when its socket is silent, closed, or the market is closed (REQ-049, REQ-114,
ADR-015, ADR-177)? Can a reconnect storm happen (server: 60 s silence, capped back-off; browser: spread, never give up,
offline 5 s)? Does the periodic positions job (live_market.py) stop on disconnect / token refused / session end and
survive one bad tick? Can a stale index or forward feed a P&L number unlabelled (REQ-072)?

## Area 2: broker reads, limits, flags, account
Files: backend/ofo/broker/rate_limit.py, flags.py, kite_flags.py, backend/ofo_app/kite_broker_reader.py, kite_reads.py,
kite_period_reads.py, kite_http.py, routes/zerodha_account.py, routes/broker_status.py, order_limits_registry.py,
underlying.py, catalogue_picker.py, frontend/src/lib/brokerAccount.js, brokerCapabilities.js,
frontend/src/pages/BrokerSettingsPage.vue.
Ask: is there exactly one limiter and does the order path (Execute, return) always get its reads? Can a margin figure
ever be computed, defaulted or shown as 0 when Zerodha did not state it (ADR-016)? Does every capability flag fail closed
(REQ-117)? Can a token or user id leak to a log, a response or the browser (masking, ADR-012)? Is a memoised answer
ever shown with a fresh read time?

## Area 3: strategy versions, order path, engine inputs
Files: backend/ofo_app/strategy_store.py, execution_plan_store.py, routes/execute.py, routes/execution_return.py,
routes/strategies.py, alembic/versions/0022_strategy_versions.py, 0023_version_evidence.py, backend/ofo/outcome/service.py,
backend/ofo/strategy/ (changed files incl. catalogue.yaml), backend/ofo/errors/templates.py.
Ask: can an order be built from, or a version activated by, anything other than the broker-reconciled state (ADR-016..
ADR-019)? Can a strategy execute while its reconciliation flag is set (known latent gap #527 item 3: is it reachable
today)? Do the migrations' up/down and grants hold (ADR-048), and can the app role write a state the trigger should
refuse? Does every order still belong to a strategy (ADR-002)? Is any new catalogue template wording advice (ADR-003)?
Is money Decimal end to end (decimal-money-boundaries rule)?

Database: run NO database test locally (CI on PR #525 runs them; the orchestrator reads it). Kite: never call it live.
BINDING: never stop a process by name. Kit guard: a shell command naming spec/, tools/, .claude, factory, views or
.github is blocked; use Read/Grep/Glob.

Return findings as a JSON array `{"area": N, "severity": "CRITICAL|MAJOR|MINOR", "file": "path:line", "finding": "...",
"attack": "what you ran and what happened", "fix": "smallest fix"}` (empty array if none), then under 250 words: verdict
PASS (no CRITICAL/MAJOR) or FAIL, and anything you could not check.
Budget: 30 min wall-clock, 32 tool calls (the verifier's turn limit is 40; batch commands)
Report: evidence-table
