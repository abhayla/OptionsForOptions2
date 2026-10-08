# Session handover - 2026-10-08 (read this first in the next session)

## 1. Where the work stands (main at 289d9db)
- **Plan:** `docs/process/master-plan-2026-10-07.md`, Stage 4a. ADR-060 (owner): build the whole core on the owner's
  own Kite app until a production-ready demo exists; Zerodha wants a demo first (F-31, ticket 403947 auto-closed
  2026-10-01 - reopen or file a new one when applying).
- **Merged today:**
  - W-059 Kite WebSocket adapter + provider interface + fan-out (REQ-048 AC-2/3/4; staleness follows the feed).
  - W-060 index spot, health and per-expiry parity forward (REQ-072 AC-2/AC-3; AC-1 waits for a database migration).
  - Decisions ADR-060 (build on own Kite app), ADR-061 (Greeks on the parity forward), ADR-062 (Save Draft),
    ADR-063 (engine owns the dividend yield), ADR-064 (closed names for risk limits/preferences), ADR-065 (pricing
    guards stop accidental misuse only), ADR-066 (Kite historical candles internal use only).
  - Findings F-31 (Zerodha reply), F-32 (live checks), F-33 (afternoon capture).
- **Phase-0 checks (ADR-030):** live ticks, chain rebuild, reconnect, stale flag (live at 14:51), history file,
  fan-out to 1,000 (replay, W-059) - PASS; Greeks vs Kite - not possible (Kite has none), internal check PASS;
  licence recorded (F-23, F-31); next-morning token expiry - NOT measured (see 3).

## 2. NEXT (in order)
1. **Merge W-058 (PR #128)** after its live proof: owner logs in once through the app's own login link; the callback
   stores the token encrypted; one real Kite call with it. Needs the test database (below). Then **merge W-061
   (PR #134, stacked)** - Save Draft, verified AC-5. Merge main into each first (branch protection needs up to date).
2. **Test database (ADR-048):** the admin user is `postgres` (`D:\Abhay\GLOBAL.env` line 214); the password on line 215
   is wrong for it (InvalidPasswordError). Owner provides the right one, or explicitly OKs a reset on the VPS. Then
   create `ofo_test` + limited `ofo_app` (ADR-048) and set `TEST_DATABASE_URL` in the project `.env`.
3. **W-060 AC-1:** migration 0008 adding NSE_INDEX/BSE_INDEX to the catalogue CHECK (after 0006/0007 merge), then verify.
4. **4a step 7 (history recording)** and **step 6 (first screen)**; restart **W-024** (issue 30, parked twice) with
   the screen - its recipe is in the 2026-10-08 park comment (root-handler redaction, ApiModel back doors closed).
5. Daily instrument load also during market hours (F-33, issue 126, registry `daily-load-misses-intraday-additions`).

## 3. Open / owner
- Token expiry time: both overnight watchers died (the first on a network drop, the second killed by Claude Code for
  low memory). Restart `docs/research/kite-proof-2026-10-07/kite_token_watch.py` only when the owner says so; it uses
  the encrypted token cache. If not restarted, probe the cached token first thing next morning.
- Expiry-close timing: SENSEX options traded until 15:39 vs index 15:29 on 2026-10-08 (F-33) - check BSE session times.
- W-058 deferred issue 129 (anonymous login lockout - fix with platform login, Stage 5); W-061 deferred issue 138.

## 4. Tools and traps learned today
- **Kite login once a day:** `session_token(env)` in `kite_core_proof.py` caches the token AES-GCM encrypted in
  `D:\Abhay\Ventures\ofo-kite-ticks\token.cache` until 06:00 IST (key `KITE_TOKEN_CACHE_KEY` in `.env`; owner OK).
- Raw tick recordings stay outside the repo: `D:\Abhay\Ventures\ofo-kite-ticks\2026-10-08\` (morning 108 MB, afternoon
  152 MB); real 10 s fixture in `tests/fixtures/kite_ws/`.
- `.git/info/exclude` now ignores `.claude/worktrees/`, so `git add -A` is safe in the main checkout.
- The kit guard blocks Bash text containing `spec`, `tools/` etc.: write PR bodies to a file (`--body-file`); edit spec
  files with Read/Edit; run kit tools as bare commands from the checkout root.
- A new ADR that amends/refines/extends another needs pins in every requirement citing the older one - run
  `python tools/ci_local.py`, read the PIN lines, add them, regenerate the digest.
- A closed GitHub issue must leave `docs/process/coverage-stages.yaml` (coverage CI checks open issues live).
- Lesson of the day: every guard built as a list of bad things (words, names, code shapes, call sites) failed review;
  every fix that held was structural (one door, closed lists, typed values).
