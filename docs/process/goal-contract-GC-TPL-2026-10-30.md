# Goal contract GC-TPL: live-market proofs of the paper-trading goal (2026-10-30, market hours)

Written 2026-10-29 ~17:05 IST, session 2 of GC-TP, on the owner's instruction: "There should be a separate contract,
goal contract, which requires the live market data, and I will run that at 9:15 tomorrow. So separate both things out."
This contract holds ONLY the work that needs live NSE/BSE prices. Everything buildable after hours stays in GC-TP
(`docs/process/goal-contract-GC-TP-2026-10-29.md`, same run tree), which finishes tonight. The owner starts this one with
/goal in a FRESH session at 09:15 on Friday 30 Oct 2026.

## Before 09:15 (the one owner step)

Log in to Kite once in a PRIVATE browser window at http://127.0.0.1:8765/broker/zerodha/login (the token expires 06:00
IST). If the API is not on 8765, the session starts it first (see "Running the app") and then asks for the login.

## Where the run works

- Run tree `D:\Abhay\Ventures\OptionsForOptions2-gctp-run`, branch `build/gctp` (local only, NO upstream). Read the GC-TP
  contract's "SESSION 2 HANDOVER" block first: it lists what tonight merged and the head commit.
- Lock: write `.run-active.lock` with this session's token at the run tree root; remove it on any stop.
- ofo_dev is the database (migration head 0030, or 0031 if the GC-TP handover says so). Never ofo_test for live runs.

## Rules for the run (kept from GC-TP)

- **No push, PR, draft PR, GitHub Actions, `ci_local.py`, `prepush.py`, `land.py` or `merge.py`.** Local commits only
  (`GC-TPL: ...`), at least every 30 minutes; nothing uncommitted at the end of a turn.
- **Orders never reach Zerodha.** Paper only (ADR-165, ADR-201, ADR-207). The session never presses Execute, never clicks
  inside any order panel, never sells holdings (memories real-order-guardrails, no-clicks-inside-order-panels).
- Browser: the owner's VISIBLE Chrome via Claude-in-Chrome, 1536 x 864, one tab per task, closed when done; never
  headless. If the extension is not connected, stop and tell the owner.
- Sensibull first: any question or gap about a screen -> grep `D:\Abhay\Ventures\competitors\sensibull\2026-10-21`
  (catalogue-raw.md, bundle-findings.md, screenshots) before deciding or asking; a `Sensibull:` line beside `Spec basis:`
  in every owner question (finding R-21).
- Technical calls are the session's own; only business forks (user-visible words, money shown, scope) go to the owner,
  one question per call, with `Business call:`, `Spec basis:` and `Sensibull:` lines. Owner away: write the question to
  `docs/process/owner-questions-2026-10-30.md` and continue.
- Every time written into a file is read from the clock in the same step (memory stamp-times-from-clock).
- Evidence table at every done claim (command run that turn + its result line). A worker's report is a claim.
- At most 2 rounds per defect, then park (Parked table) and continue. A defect found here follows the defect-fix
  contract (RCA, class, failing test first, class fix, one real-data proof, detection change); a fix is built in a
  sub-worktree of `build/gctp` and merged locally, never on a live screen by hand.
- Market closes 15:30 IST: anything not proven by then is PARKED with what is left; the session does not wait for the
  next day.

## Running the app

Check ports 8765 / 5174 first (`Get-NetTCPConnection -State Listen -LocalPort 8765,5174`); stop only recorded PIDs.
API: `python scripts/orchestrator/dev_run.py` from the run tree on ofo_dev with LIVE_MARKET=1 (as in the GC-UI contract's
"Running the app", run tree path). Vite: from `frontend`, `OFO_API_TARGET=http://127.0.0.1:8765 npx vite --port 5174
--strictPort`.

## Items (in this order)

| Step | Time | What | Proof | Status |
|---|---|---|---|---|
| L0 | 09:00-09:15 | Preflight: read the GC-TP SESSION 2 HANDOVER; servers up on the run tree head; Kite session valid (`GET /user/profile` via the app's broker status route, no order door) | status lines recorded here | Not started |
| L1 | 09:15-09:20 | bseindia.com (logged out) SENSEX "Previous Close" must read **74,151.04** (the value the 29 Oct settlement used for strategies 52, 60, 61). If it differs: STOP L-steps that depend on it, record both values, and build a correcting `settle` order path in a sub-worktree (orders are append-only; never edit rows) | screenshot in `D:\Abhay\scratch\gctpl\`, value + time | Not started |
| L2 | 09:20-11:30 | Expert-trader walk end to end, live prices: build a NIFTY short iron condor, a SENSEX short strangle and a NIFTY calendar; Add to Paper at TYPED prices; watch each on Positions -> Paper (prices moving, Total / Booked / Unbooked / Decay / Charges); in Drafts Mode: roll one leg, partial exit (1 of 2+ lots), add a hedge leg; set a conditional exit 5 points beyond spot on a 1-lot strategy and see it fire once (bell + Alerts page, `stop` orders at the tick LTP); the R-19 screens (Target sliders below the graph with move % and projected badge; Breakeven / Max / Greeks on paper cards) and the "Add Booked P&L" switch (ADR-209) checked live | walk lines with times; `python scripts/checks/ui_data_check.py --paper-orders <id>` on 5 strategies (NIFTY + SENSEX; single expiry + calendar; one with a roll, one with a partial exit): every figure matches, 0 mismatches; target mode (`--target-level/--target-at --booked`) on 2 of them | Not started |
| L3 | during L2 | Re-test findings F-65, F-66, F-67, F-68, F-69, F-70 live, each against its text in `spec/findings.md`; mark each fixed there with the date and the proof line (F-71 stays deferred). Re-run the checker with PYTHONIOENCODING unset (R-1 re-test) | one line per finding | Not started |
| L4 | after L3 | Move `knowledge/findings/paper-plan-diverges-from-position.json` to `guarded`, naming the checker check (`--paper-orders`) and the Drafts Mode diff test; regenerate its index with the repo's regen script | file diff + regen exit 0 | Not started |
| L5 | before 15:30 | Handover: DONE / PENDING / BLOCKED / PARKED / OWED-AT-LAND / NEXT appended to this file and to GC-TP's handover; memory note; lock removed | commit on build/gctp | Not started |

Owed after this contract (not in it): NIFTY 3 Nov expiry settlement proof (after 15:45 Mon 3 Nov: each settle price =
intrinsic from NSE's published close, checked by the checker); migration 0031 (drop the 0021 / 0027 tracking tables) and
the removal of the 11 merged session-1 worktrees (`wt-rm.ps1` refuses until the work is on origin/main) at land; land
itself is the owner's call.

## Definition of Done

- [ ] L1 recorded (equal, or the correcting path built and proven).
- [ ] L2: the checker matches every figure for 5 real strategies (NIFTY + SENSEX; single expiry + calendar; a roll and
      a partial exit), 0 mismatches; the conditional exit fired once and did not refire after an API restart.
- [ ] L3: F-65..F-70 each re-tested live and marked fixed in `spec/findings.md` (or PARKED with evidence).
- [ ] L4: the defect class file is `guarded`.
- [ ] No push, no PR, no CI (`git rev-parse @{u}` on `build/gctp` reports no upstream).
- [ ] L5 handover committed.

## Found during the run

| F | Step | What failed (seen) | Class / RCA | Fix commit | Re-test |
|---|---|---|---|---|---|

## Parked

| Row / item | Why (evidence) | What is left |
|---|---|---|
