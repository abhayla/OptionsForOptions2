# Session handover - 2026-10-08 evening (read this first in the next session)

Previous: `docs/process/session-handover-2026-10-08.md` (morning). Plan: `docs/process/master-plan-2026-10-07.md` 4a.
The owner restarted the session so kit 1.7.0's hook, agents and settings load (#153 merged).

## 1. Merged today (main at 9f075f1)
- #146 / #147 docs: F-34, ADR-067 (one-minute history: live first, final from Kite's candles), ADR-068 (first-screen
  rules: planned entry captured when a leg is added; push at most 1/s; UX level per request; leg picker in 4a).
- #149 main repair: app CI now also runs on `backend/ofo/**` and `tests/fixtures/**`; migration **0006_index_segments**
  (NIFTY 50 / SENSEX index rows storable, identity pinned by CHECK).
- #150 **W-063** outcome API (`POST /api/strategies/outcome`). #152 **W-024** round 10 (redaction at the root, closed
  ApiModel, one error boundary; owner decision: review MAJORs deferred to #148; outcome route exempted by name, #151).
- #157 learning batch. #158 **W-062** one-minute history (store rules in one writer, session-clipped gaps).
- #153 **kit 1.7.0** (model-routing table, Explore agent, stricter agent_model_required hook, model_mix.py).

## 2. Test database (ADR-048) - exists now
- `ofo_test` + role `ofo_app` on the Windows VPS PostgreSQL, through the tunnel 127.0.0.1:5432; at revision **0007**
  (W-058's migration was applied by its builder; main is at 0006 - harmless, W-058 merges next).
- Admin = `GLOBAL.env` `WINDOWS_VPS_PG_ADMIN_USER/_PASSWORD` (now the working postgres credentials of its DATABASE_URL
  row). App role = project `.env` `TEST_DATABASE_URL`. Project `.env` also has `BROKER_TOKEN_KEY` (W-058).
- Run anything needing the DB with `python scripts/orchestrator/db_run.py <dir|agent:id> <command>` (secrets in memory
  only). Full app suite over the tunnel ~15 min; two timing tests can flake there (pass on rerun and in CI).

## 3. NEXT (in order)
1. **W-058 (PR #128, branch at 34b8346)** - live owner-login proof PASSED 2026-10-08 (session 82 stored encrypted, Kite
   profile + LTP 200 with the stored token, no token in output; record `docs/research/kite-proof-2026-10-07/
   w058-live-proof-2026-10-08.json`). Tier A review: merge yes, minors fixed in round 1 (statuses 429/502/503,
   catalogue codes kept in logs, redirect/cookie checks, cookie cleared on refusal, WWW-Authenticate).
   **Before merge:** (a) run mutation tests for the 5 new guards the builder did not mutate (off-site redirect,
   cookie `;`/CRLF, cookie cleared on refusal, 401 WWW-Authenticate, Retry-After) - Tier A rule; (b) owner reads the new
   `kite_busy` wording (BROKER_AUTHENTICATION_310) - pin pending; (c) update PR #128 body; merge with
   `python tools/merge_when_green.py 128`; then `merge_audit.py` is not needed (merge into main).
2. **W-061 (PR #134, stacked on W-058)** - only AFTER W-058 merges: merge main into it once, renumber its migration
   0007_strategy_store -> **0008** (down_revision 0007_broker_sessions), adapt to W-024 rules (ApiModel, one error door,
   write allowlist, producer inventory - no new exemption), DB tests via db_run, `merge_audit.py`, verify AC-5, merge.
3. **Status batch** on branch `docs/status-2026-10-08` (pushed; holds `evidence/W-060/AC-1.md`, verifier PASS on the
   real DB): set W-060, W-062, W-063, W-024 `status: done`; REQ-072 and REQ-065 to Verified if `trace_check` allows;
   add these helper scripts; PR + merge.
4. 4a step 6 remaining items (plan from the 2026-10-08 Plan agent, recorded in ADR-068): live feed in the app + push to
   the browser (Tier A, needs W-058), margin from Zerodha (Tier A), the **Strategy Builder screen** (incl. issue
   **#159**: the frontend must serve `/broker/connected` - today a good login lands on a 404), #151 (outcome text
   through the catalogue), #148 (W-024 MAJORs).
5. W-062 follow-up: PostgreSQL history store + migration + the after-close finalize job (add the store to
   `tests/history/test_store_contract.py` STORES).
6. Mechanisms due (second occurrences): #154 (owner: GitHub "require branches up to date"), #155 (hook: a failing
   step must stop commit/push). Daily instrument load intraday: issue 126.

## 4. Owner items open
- #154 GitHub setting; `kite_busy` wording; token-expiry watcher restart only when asked.

## 5. Traps learned today
- Merge order matters: every PR is merged with current main and both suites re-run before merge - branches green
  alone went red together 3 times (#154). Use `python scripts/orchestrator/merge_audit.py . <tip> <main> <head>` after
  each merge of main into a branch.
- A failing step must not be followed on the next line by commit/push (finding pipe-masks-gate-exit-code): run gates
  as their own tool call.
- `cd` outside the project does not persist in Bash; kit tools for another worktree need a runner that sets cwd.
- Evidence: use `scripts/orchestrator/record_evidence_fp.py` (writes `requirement` + `ac_fp`).
- Run app tests with `-c pytest-app.ini` (the root config has no asyncio mode - "async def not supported" = wrong ini).
