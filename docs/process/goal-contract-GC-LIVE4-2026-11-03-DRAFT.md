# Goal contract GC-LIVE4 (DRAFT): live market check of alert discipline, plus other live checks ready that day

Core: on a live market day the background worker raises ONE adjustment suggestion per real crossing (REQ-170 AC-1),
not one per wobble. Proof (step 1): three fresh paper strategies (intraday / weekly / monthly) run with the background
role on and no app tab; records per strategy per hour are counted from the database and compared with the 2026-11-02
baseline (103 records 09:30-11:50, 75 lapsed; strategy 66 T-07: 30 records in 31 min).

Status: DRAFT, written 2026-11-03 00:39 IST on the owner's instruction (chat: "for market hour testing, create a
separate contract, separate goal contract, and we will run it during that market hours. Maybe we will combine other
live market hours testing along with this one"). Needs the owner's approval and the owner's Kite login before it runs.
Runs after GC-ALERT1 closes (build + gate + push). Paper only; no real orders.

DATES: every time written in a record comes from `date` in the same step. NIFTY expiry Tue 2026-11-03 (expiry day:
0 days left = intraday preset for 3 Nov strategies); next NIFTY weekly 2026-11-10; SENSEX nearest per the instrument list.

## Session start
1. `git -C D:\Abhay\Ventures\OptionsForOptions2-OptionsForOptions2-settings log --oneline -5`, `git status`; branch
   `feature/adjustments`; the GC-ALERT1 handover (`docs/process/session-handover-2026-11-03-gcalert1.md`).
2. REQ-170, ADR-235, ADR-236, ADR-237; memory notes `dev-redis-5-portable`, `kill-processes-for-memory`,
   `no-clicks-inside-order-panels`, `browser-always-visible`, `db-tests-use-db-run-fresh`.
3. Free memory at least 3.0 GB before starting the API, background, feed, Redis and vite.

## Owner inputs (collected first)
- Kite login in a private window at or after 09:15 (the only owner-only step).
- Approval of this contract and of which "other checks" (section B) are in.

## A. Alert discipline live (the core)
| # | What | Done when (evidence) |
|---|---|---|
| A0 | Preflight: portable Redis 5 on 6380, FEED_MODE=bus, API + background + feed on ofo_dev (migrated to head: 0036 on 2026-11-02 23:4x), owner's visible Chrome | process list + /health + Redis INFO version line |
| A1 | Three fresh paper strategies at typed prices: one 3 Nov NIFTY (intraday preset on expiry day), one 10 Nov NIFTY (weekly), one monthly; record each style the worker reports (GET /api/strategies/{id}/alert-style) | three ids + in_force styles |
| A2 | Background on, no app tab, 09:30-11:50: count suggestion records, held rows and lapses per strategy per hour from the DB (read-only queries) | counts table vs the 2026-11-02 baseline, written into REQ-170 as a finding (F-id) |
| A3 | Dismiss one open suggestion; watch the same level stay quiet for its cool-down; if a stage-worse crossing happens, see "Worse than the one you dismissed" | inbox lines with times |
| A4 | Check speed per style from the worker's minute lines (10 s / 30 s / 120 s) | minute lines |
| A5 | Stop-loss not delayed (AC-5): a paper stop on one strategy fires on the live price while its adjustment rule is gated | paper order line with time |
| A6 | Inbox renders worker records (the group-key defect fixed 2026-11-03) and the Preferences tab / alert-style picker at 390 px + desktop (not seen on 2026-11-02: window would not resize) | screenshots in the owner's Chrome |

## B. Other live checks (owner picks; each only if its build is merged by then)
| # | What | Source |
|---|---|---|
| B1 | T3 theta re-run with the reference logged in, 10 Nov + the expiry-day chain (ADR-234 (6)) | GC-LIVE3 handover NEXT |
| B2 | F-68 (expiry-day behaviour, not testable on 2 Nov) on the 3 Nov expiry | GC-LIVE3 E2 |
| B3 | #616 paper screen after the 15:30 close (banner, P&L frozen, indices not null) if a fix is merged | #616 |
| B4 | #624 drawer liquidity flags on a live chain (built 2026-11-02, S1) | GC-ALERT1 S1 |
| B5 | Any other item merged into feature/adjustments by 09:15 that needs live prices | added by the owner |

## Rules
- Paper only; never click inside a live order panel; every browser step in the owner's visible Chrome.
- Read-only database queries for counts; no test suites against the VPS database host during market hours beyond one
  targeted file at a time (it also serves another app's production).
- Under 3.0 GB free: stop processes by PID (named), never this session.
- A failure is recorded with its output and becomes an issue (`gh_issue.py app ... --stage`); 2 rounds per class, then park.

## Definition of Done
- [ ] A0-A6 done with evidence, counts written into REQ-170 (finding + decision row if a preset should change).
- [ ] Each chosen B item done, or parked with its reason.
- [ ] Handover `docs/process/session-handover-2026-11-03-gclive4.md`; memory; nothing on main.
