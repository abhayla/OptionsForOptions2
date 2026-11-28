STATUS 17:58 | items 1, 2: Fixed, not tested in a browser; gate TOTAL PASS (prepush, ruff 0.15.12); frontend 396 files / 4253 tests | items 3-13 not started | next push after item 3 | blocker: none | link to coordinator was refused (elevated_session_untrusted_device) until the owner approved trust; works now. New from coordinator: Opus review of items 7+8 also covers the real Exit path in LiveStrategyCard (ADR-330 (64))

# RESULTS Lane FJ2 (frontend), branch fix/r3-frontend-2-1128, base origin/fix/r3-frontend-joins-1128 (ddd656805)

| Item | State | Red line (first) | Green |
|---|---|---|---|
| 1 paused sentence once, with as-of | Fixed, not tested in a browser | paper-paused-once-fj2-1128: the sentence printed 19 times on Positions with 8 strategies in state NOT_CONNECTED whose reason text says "prices not live" (2 of 2 red); home-paused-asof-fj2-1128: Home total had no ", as of" (1 of 2 red) | 4/4 and 2/2; full run 396 files / 4253 tests; Exit tests exit-market-closed-adr330-60 and exit-rule-all-doors-r3-fj still green |
| 2 server not_applicable_text | Fixed, not tested in a browser | not-applicable-text-fj2-1128: PaperStops and PlanEntry printed the constant over the server's text (2 of 3 red) | 3/3 |

Item 1 cause: the page-level scope rule (`priceScope`) counted only state PAUSED. With no broker session the server sends state NOT_CONNECTED but still words every reason "Paper P&L paused - prices not live" (TG D-TG-1/5), so no rule collapsed them: 19 prints. Fix at class level: NOT_CONNECTED counts as affected in the one scope rule; the page line is the paused sentence the server sent (with its time), else the not-connected sentence; a not-connected book's pause reason also carries the as-of time. Home (T1-20) and the Positions totals strip now use the answer's own time when the server's text has none (paperPnl.pnlFigure, PositionsTotals).
Not reproduced: 8 strategies in state PAUSED already printed once (test FJ2-1 green on the base).
Note: the first full run failed 66 files because my own edit read `pausedNow` before it was initialised (ReferenceError); fixed, rerun green.

## For the owner lane
- none yet

## Decided for the owner
- NOT_CONNECTED strategies are counted with PAUSED ones for the one-sentence rule.
- With the market-closed banner up (noticeUp) the list prints no paused sentence of its own (unchanged; existing test).

## Question for the owner
- none yet

## New wording for the owner to read
- none new (item 1 reuses "Paper P&L paused - prices not live, as of <time> IST")

## Environment note
- ruff ratchet needs the pinned ruff==0.15.12 (requirements-dev.txt); a newer ruff reports 3 rules above baseline with no Python changed.

## Not done
- items 3 to 13 (not started)
- Opus review incl. LiveStrategyCard real Exit path (coordinator 12:14 UTC): after items 7 and 8

## Tasks
| task | model | minutes |
|---|---|---|
| items 1-2 | Sonnet | 45 |
