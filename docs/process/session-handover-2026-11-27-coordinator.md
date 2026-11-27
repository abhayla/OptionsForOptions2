# Session handover, 27 Nov 2026 (coordinator)

Standing rules are in `docs/process/session-handover-2026-11-26-coordinator.md`; read that first. This page only adds
what changed on 27 Nov.

## Owner rules added 27 Nov
- Prepare before execution: the plan, the PC message and the login are ready the evening before.
- The coordinator has full authority in live market hours, within the standing limits.
- Paper equals real; only a tag differs (ADR-330 (58)).
- Scan every lane every 30 minutes.
- The task picks the model.
- An unrelated task goes to a fresh lane; a finished lane reports SAFE TO CLOSE and the owner archives it.
- The weekend of 28 to 29 Nov runs day and night in rounds of build, PC test, fix (owner approved 27 Nov 17:15).
- No waste of tokens, time or money: small sessions, no duplicated work between lanes, and each lane has a list of
  the files it owns.
- Nothing is called approved until it passed on the owner's PC.
- The status page is updated every hour with every new, fixed and tested issue, no exceptions.

## Lanes started 27 Nov evening
| Lane | Branch | Work |
|---|---|---|
| K | fix/order-limits-1127 | lots limit and freeze at the order door |
| L | fix/pnl-totals-1127 | one P&L total and counts |
| O | fix/alert-screens-1127 | alert and plan sentences, quick usability |
| R2 | hotfix/plan-read-1127 | plan read-back |
| V | feat/plan-door-1127 | decisions 54, 55, 57 |
| N | fix/last-close-1127 | last close and after-close screens; migration 0059 approved (additive table last_close) |
| E | docs/paper-real-audit-1127 | paper versus real audit and one-exit-door design |
| X2 | docs/test-plan-weekend-1127 | weekend and Monday test plans |
| J | hotfix/loss-stop-1127 | plan-stop alerts and decision 47 |
| U | hotfix/index-quote-1127 | price door, Exit dialog, decisions 48 and 49 |
| Q1 | perf/route-profile-1127 | route profiling |
| Q2 | test/live-day-gaps-1127 | live-day test gaps |
| Z (not started) | integration/weekend-1127 | combined build |
| H (not started) | (not set) | speed fixes |

## Result of 27 Nov
77 planned checks: 24 pass, 13 fail, 24 in part, 7 not checked, 1 data, 8 after-close.
Triage: `docs/process/test-triage-2026-11-27.md`.

## Test rounds
- Sat 28 Nov 01:00
- Sat 28 Nov 10:00
- Sat 28 Nov 20:00
- Sun 29 Nov 13:00 (final)
- Build frozen Sun 29 Nov 20:00
- Monday 30 Nov: live from 09:15
