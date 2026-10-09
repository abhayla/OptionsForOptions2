# Session handover - 2026-10-09 (read first on the next PC)

Previous: `session-handover-2026-10-08b.md` (evening), `session-handover-2026-10-08.md` (morning).
Plan: `docs/process/master-plan-2026-10-07.md` Stage 4a. Kit 1.7.0 (model routing, Explore agent, stricter hook).

## 1. Merged since the 2026-10-08 evening handover (main after this check-in)
- #153 kit upgrade 1.7.0; #160 status batch; #161 W-064 work item.
- #128 **W-058** Kite login callback + encrypted token store (live owner-login proof PASS 2026-10-08, session 82;
  Tier A review merge yes; mutation proof on all five new guards; 15 broker message wordings owner-read).
- #162 **W-064** Strategy Builder screen, first slice: the API's single table (sticky columns, current level
  highlighted), payoff chart and summary copied from algochanakya per ADR-047, Advanced Details (bid/ask) only at
  Advanced, the not-live states, `/broker/connected` (#159). Verifier PASS REQ-035 AC-3 and AC-5.
- #164 test fix: the live-file catalogue test failed every day after an expiry (expected counts now drop expired rows).
- Requirements Verified: REQ-065, REQ-072. Work items done: W-024, W-058, W-060, W-062, W-063, W-064.

## 2. PARKED - first thing next session
- **W-061 Save Draft (PR #134, branch `build/W-061-save-draft` at 3f14653)** - issue **#165** holds the three Tier A
  defects and the fix order (ADR-069 enforced at the value type, a database CHECK for the closed definition shape,
  typed history summaries rendered by catalogue templates - never repr). ADR-069 (owner, 2026-10-09: settings values are
  identifiers or numbers) and its REQ-038 pin live on that branch and merge with it. 13 W-061 templates are pending
  owner read. Bring the branch onto main first, run `scripts/orchestrator/merge_audit.py`.

## 3. NEXT after W-061
1. 4a step 6 remaining: live feed in the app + push to the browser (REQ-035 AC-4, Tier A), margin from Zerodha (Tier A),
   the leg picker (ADR-068 item 4) and the Save Draft button (after W-061), #163 (login refusals redirect to
   `/broker/refused`), #151 (outcome text through the catalogue), #148 (W-024 MAJORs).
2. W-062 follow-up: the PostgreSQL history store + after-close finalize job (add it to `tests/history/test_store_contract.py`).
3. Mechanisms due: #154 (owner: GitHub "require branches up to date" - three green-alone/red-together merges), #155
   (hook: a failing step must stop commit/push).

## 4. Setting up the other PC (not in git on purpose)
- **Project `.env`** (gitignored) holds `KITE_API_KEY`, `KITE_API_SECRET`, `KITE_REDIRECT_URL`, `KITE_EXPECTED_USER_ID`,
  `ZERODHA_CLIENT_ID`, `KITE_TOKEN_CACHE_KEY`, `TEST_DATABASE_URL` (the `ofo_app` role) and `BROKER_TOKEN_KEY`
  (created 2026-10-08). Copy it to the other PC by a private channel; never commit it.
- **`D:\Abhay\GLOBAL.env`**: the Windows VPS copy was synced 2026-10-09 for the two Postgres admin keys (byte-exact,
  backup `C:\Abhay\GLOBAL.env.bak-20261009` on the VPS). `NOTIFIER_URL` differs per machine on purpose.
- **Test database**: `ofo_test` on the Windows VPS PostgreSQL through an SSH tunnel to 127.0.0.1:5432 (key
  `~/.ssh/ipodhan_vps`, user Administrator@103.118.16.189). At revision 0008 (W-061's migration applied by its builder;
  main is at 0007 - harmless; W-061 brings 0008). Run DB work with `python scripts/orchestrator/db_run.py <dir> <cmd>`.
- **Kite**: one owner login a day; `kite_core_proof.py session_token()` caches the token encrypted at
  `D:\Abhay\Ventures\ofo-kite-ticks\token.cache` (per machine). Raw tick recordings stay in
  `D:\Abhay\Ventures\ofo-kite-ticks\2026-10-08\` on THIS PC only; the tests use the small real fixtures in
  `tests/fixtures/kite_ws/` and `tests/fixtures/kite_history/`.

## 5. Owner items open
- #154 GitHub setting; the 13 W-061 message templates (when W-061 is fixed).
- Two leftover scratch folders on this PC (`...\scratchpad\verify\W-064` and `W-064b` under the 2026-10-08/09 session
  temp folders) could not be deleted: long paths, and the production gate's governed marker points at one of them.
  Harmless; delete by hand or ignore.

## 6. Traps learned (also in `knowledge/findings/`)
- Merge main into a branch and re-run both suites before merging; check with `merge_audit.py` (nothing lost).
- A failing step must not be followed on the next line by commit/push (pipe-masks-gate-exit-code).
- Never edit a remote file through the remote shell's `type`/`cat`: it re-encodes (remote-shell-read-transcodes-file);
  move files with scp both ways and verify by an scp read-back.
- Builders started preview/API servers and left them running for 5 h: briefs require stopping every started process.
- App tests need `-c pytest-app.ini`; the live-file catalogue test is a network test.
