# Session handover: GC-LIVE3 live-market day, Mon 2026-11-02

Contract: `docs/process/goal-contract-GC-LIVE3-2026-11-02.md`. Branch `feature/adjustments` in
`D:\Abhay\Ventures\OptionsForOptions2-OptionsForOptions2-settings`, local only until C3. Full run log with every time
and number: `D:\Abhay\scratch\gclive3\run-log.md`.

Written 13:15 IST, completed at C2 15:3x IST; the C3 result is added in C4.

## DONE

| Step | Result | Evidence |
|---|---|---|
| A0 | Preflight; owner Kite login 09:17; instrument list: NIFTY 3 Nov 208 contracts, SENSEX nearest 5 Nov 348 | run log A0 |
| A1 | Bus mode needed Redis 5 (this PC's service Redis is 3.0, no Streams). The owner approved a portable Redis 5 on 6380 (`D:\Abhay\tools\redis5`) | memory `dev-redis-5-portable` |
| A2 | Cold reads: #615 reproduced repeatedly (LIVE with 0 of 21 priced, wrong centre strike); builder spot shown within 5 s (#583 I-6 pass) | F-97 |
| D2 | Paper strategies 78 (NIFTY 9 Nov IC) and 79 (SENSEX 5 Nov strangle) at typed prices | run log D2 |
| D3 | PARTIAL, PARKED #636. The background role records opportunities on real ticks with no browser open (3 fixes: 7c804264, ba6f43dd, f7d2088b, after an independent review). Measured crossings: 0.09 s and 1.0-1.6 s. Owner then set 30 s (ADR-233, code 4e54c557, live-checked 12:11-12:15). | F-91, findings files `check-clock-read-once-per-batch`, `bus-consumer-holds-no-own-tokens`, `check-latency-bound-by-db-round-trips` |
| D4 | At most 14 recomputes per strategy per minute (limit 60); the valve flaps on DB wait | run log D4 |
| D5 | Compare on 78: no approach offered (F-92, both feed modes), "no plan maximum set" (F-93), paper book vs other screens max profit/loss (F-94, ADR-082 defect) | F-92..F-94 |
| B1/B2 | T3 NIFTY 9 Nov, 3 rounds: theta gap up to Rs 209 per lot per day (CE/PE split by a drifting carry term). Owner decided ADR-234: state theta like the reference. T3 3 Nov also measured | F-98, ADR-234 |
| C1 | REQ-078 AC-1: strikes 3/3 and base max loss to the paisa pass; p95 4,783 ms FAIL | `evidence/W-158/AC-1.md` |
| E1 | #583 I-1 futures shapes (716c6e75) and I-12 futures leg false "disconnected" (893b659b) fixed, proven live | F-95, F-96 |
| E2 | F-65, F-66, F-67, F-69 still fixed live; F-68 not testable (no expiry) | run log E2 |
| E3 | Live paper leg stop fired correctly; #614 "1 legs" still present | run log E3 |
| Extra | F-99: stopping a second feed process blanks the API chain for about a minute | F-99 |
| Study | Adjustment-alert frequency study; REQ-170 Draft (alert discipline) with 4 owner questions | `docs/research/adjustment-alert-frequency-2026-11-02.md`, REQ-170 |
| Afternoon builds (owner 13:00 "Start, including code fixes") | ADR-234 theta (b956910b; 9 Nov saved data worst gap Rs 27-35, was 172-209; engine 874 tests); F-92 Compare holds the position's own legs (366c6c35) and F-93 "used of max" (d45e9968) (103 tests); F-94 paper max profit/loss net of charges (1f20bc4a; route test 30 passed on a throwaway DB); #614 one-leg alert wording (7babdba9) + pins (3113d034) | commits; live proof after the 15:40 restart |
| Decisions | ADR-233 (30 s), ADR-234 (theta like reference) + (6) residual from per-side IV, logged-in T3 next trading day; ADR-235 (check speed per style 10 / 30 / 120 s); REQ-170 alert discipline Approved (Q-AD-1..4 answered) | spec |
| Research | IV is not in any feed we use (F-100); #636 push design reviewed: REVISE accepted (memory-only check, settings cache + count poll, no LISTEN/NOTIFY) | F-100, #636 comments |
| Live proofs 15:04-15:12 | F-92 Compare priced every leg, 5 approaches; F-93 "0 of 2"; F-94 paper 3,168.80 / -3,331.20 incl. Rs 289.20 charges (Compare 3,168.79: 1 paisa rounding difference left); ADR-234 chain theta CE = PE where IV equal (23300 -13.51) | run log |
| Regression found + fixed | #614 wording (7babdba9) made GET /paper/alerts answer 500 for every user; fixed 79db5597 (restore every stored form, one bad row never breaks the list); live 15:35:50: 200, 5 alerts, new one-leg text shown | run log, #614 |
| E4 close 15:29-15:32 | Option chain: 1 banner "Market closed. Prices are from 2 Nov 2026, 15:30:00 IST" PASS. Paper tab: no banner, "no implied volatility for this leg", Total P&L still moving after 15:30 (+20,404.40 -> +20,846.40) FAIL; GET /api/market/indices: market_closed true, values null FAIL -> #616 unchanged | run log |

## PENDING
- C3 BLOCKED: prepush --full on 828bd537 was stopped by the low-memory reaper at ~15:58 after ~21 min (3rd reaper kill of
  the gate in 3 days: 11-01, 11-02 08:34, 11-02 15:58). Owner chose to run it from the prompt:
  `! cd D:/Abhay/Ventures/OptionsForOptions2-OptionsForOptions2-settings && python scripts/orchestrator/prepush.py --full`
  Nothing pushed: ~30 commits are local only. FIRST STEP of the next session if not done tonight: run that command,
  push `feature/adjustments` on TOTAL PASS, then C4 clean-up (heavy slot release, -fix633 / -fix628 worktrees via wt-rm.ps1).
- #616 (Paper after close, indices null): not fixed; reproduced 2026-11-02.

## PARKED
- #636 background check latency: design reviewed and revised (comment 2026-11-02 ~13:20); round 4 not built.

## OWNER QUESTIONS
- None open: REQ-170 Q-AD-1..Q-AD-4 answered 14:15-14:18; ADR-234 (6) answered 14:04.
- To read (not blocking): new / changed texts marked "pending owner read" in tests/errors/template_pins.json
  (adjust_cmp_adjustments_of, paper_extremes_with_charges, paper_extremes_before_charges, paper_alert_body_one,
  paper_alert_body_one_named).

## NEXT
- FIRST: the C3 gate + push above.
- Owner approval of `docs/process/goal-contract-GC-ALERT1-DRAFT.md` (reviewed, FIX FIRST applied; one open owner question inside).
- Build REQ-170 (alert discipline) + ADR-235 (speed per style): goal contract first, core proof = strategy 66-style flapping on the saved scenario/live paper data gives 1 record, not 30.
- #636 round 4 per the reviewed design (merge base branch first, guard tests, record merge commit in #636).
- T3 re-run with the reference logged in (ADR-234 (6)), 9 Nov + an expiry-day chain; then the one-IV-per-strike decision.
- Live proofs of today's afternoon fixes if not done at the close.
- (C3 result filled at the close)
