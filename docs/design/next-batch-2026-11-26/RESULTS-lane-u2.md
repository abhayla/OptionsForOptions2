STATUS 19:50 | item 1: gate 2 running (push after TOTAL PASS) | items 2, 3: built, Opus round 1 fixed, push after item 1 | next push 20:40 | blocker: none (send_message refused: untrusted device; this line is the report)

# Lane U2 results (branch fix/exit-all-1127, from f61f7935)

Highest status of everything below: **Fixed, not tested** (owner PC).

## Item 1: an exit whose outcome is unknown is never sent twice (ADR-017, ADR-016..019)

Core / Proof: tests/exit-unknown-resend-adr017.test.js CORE, run red on the old code (the second Confirm was enabled after the 5 s hold, so a second POST), then green.

| | |
|---|---|
| RCA | The builder's dialog had no `locked` and its own 5 s hold timer lapsed, so a second Confirm re-sent; Cancel kept the exit as a staged edit and Review and add re-sent it. |
| Class | Any post that carries an exit row and ends unknown (503 / no answer / superseded) in the builder: before, unlocked after 5 s; after, locked until a good re-read decides it. |
| Fix | `exitUnknown` lock set on every unknown outcome of a post with an exit row; it blocks Confirm, per-leg Exit, Exit all and Review and add through the one gate (`usePaperExit` `unresolved`, panel prop `exitUnresolved`). One sentence: "The first exit's outcome is being checked; no second exit is sent until the book has been read." (pending owner read). An automatic re-read decides: stored / changed / not stored. "Not stored" is accepted only from a read taken 5 s or more after the reply; an older read answer never replaces a newer one. A not-stored exit is never kept as a staged edit; only a fresh Exit click sends it. |
| Tests | 8 new (exit-unknown-resend-adr017); exit-pending-adr330-49 (3 tests now hold the re-read open); related exit tests 81 passed. |
| Review | Opus Tier A round 1: REVISE (1 BLOCKER: lock only when the click came from Exit; 2 MAJOR: a stale Orderbook read could reopen a leg, early "not stored"; untested restoreStaged branch). All fixed in 800f872. Round 2 not run (the listed items below are inferences the review itself marked as needing a server key). |

### To file as deferred issues

| Title | Evidence | Spec basis | Done when |
|---|---|---|---|
| Paper orders route has no idempotency key | Opus: routes/paper.py:1372; "not stored" after 5 s is still an inference | ADR-017 | the POST carries an attempt id the server de-duplicates |
| Lock stays on when every re-read fails | Opus finding 4: only a reload (or the Orderbook link in the open dialog) recovers | ADR-017 | a good poll decides it, or a "Check again" control |
| A plain add (no exit row) with an unknown outcome can be sent twice from the builder dialog | Opus finding 1 (same dialog); order door is Lane K's | ADR-017 | the same lock for any post |
| Exit all drops earlier staged edits silently after an unknown, unchanged re-read | Opus finding 7 | ADR-330 (59) | covered by item 3 if built |
| `:locked` on the builder dialog is redundant with `:blocked` | Opus finding 6 (no test fails without it) | none | none needed |

## Item 2: the Exit dialog when the market is closed (ADR-330 (60))

Core / Proof: tests_app/test_exit_market_adr330_60.py on the real calendar: Friday 27 Nov 16:02 gives "The market is closed. Exits can be placed from 09:15 on Monday 30 Nov." with a feed present and with no context at all (the same sentence).

| | |
|---|---|
| RCA | The dialog knew only the book's price states; with the market closed a held close reads "live" (feed running), so Confirm was enabled and the server then refused (ADR-212). |
| Fix | New server answer `GET /api/market/exit-state` (`ofo_app/exit_market.py`, `routes/exit_market.py`): `closed`, the catalogue sentence (new explanation templates `exit_market_closed`, `exit_market_closed_no_day`, new slot `DayLabel`), `next_open_at`. It reads the one market-state answer (`routes.outcome.market_state`, calendar behind it) and has no paper or real input. `PaperConfirmDialog` (the ONE component of the builder, Positions and Alerts Exit dialogs, and Exit all) asks it when it opens with an exit row: closed -> the sentence and Confirm off (it replaces the not-live line); answer late, failed, ambiguous or without a sentence -> Confirm off with "The market status could not be read. Try again in a moment." (pending owner read). Entry-only dialogs never ask. ADR-212's server refusal is unchanged. |
| Lane N | `next_open_at` on Lane N's market-state answer was not on the branch; the day comes from `market_calendar.next_open` directly. When origin/fix/last-close-1127 lands, replace that one call in `exit_market.py`. |
| Lane V files | Not touched: PaperStrategies.vue and the Positions dialog block need no change (same component). |
| Tests | backend 5; frontend 7 (builder per-leg, Exit all, wins over not-live, open, four answer states, late answer, entry-only never asks); 14 older test files got the open answer in their mock. |

## Item 3: Exit all with a staged change (ADR-330 (59))

| | |
|---|---|
| Fix | Exit all is not blocked. The dialog adds "Exit all closes every open leg. The change waiting on <legs> is not sent and will be discarded." (prop `note`); Cancel puts the legs back exactly as they were (no exit left staged); Confirm posts only the exits (no acted / basket / approach, which are dropped from the link with the discarded change); then "The change waiting on <legs> was discarded." (also when the re-read fails). Unknown outcome: the change is kept, with "The change waiting on <legs> was not sent; it is kept until the exit's outcome is known."; after the item-1 re-read: stored or changed -> "...was discarded."; not stored -> the legs come back unchanged with "The exit was not stored. The change waiting on <legs> is back, unchanged." All sentences pending owner read. |
| Tests | 7 in exit-all-staged-adr330-59 (not blocked, Cancel exact, a 4xx then Cancel, posts only exits and acted dropped, no staged: no note, unknown then not stored, unknown then stored). |
| Reviews (items 2 and 3) | Opus Tier A round 1: REVISE (BLOCKER: openapi.json not regenerated; MAJOR: acted / basket / approach outlived the discarded change; MINOR: no discarded note when the re-read failed, untested clauses). Fixed: openapi regenerated, acted dropped, note always shown, tests for the late answer and the 4xx-then-Cancel. Round 2 not run (B1: what is left is MINOR, listed). |

### Left, MINOR (To file as deferred issues)

| Title | Evidence | Spec basis | Done when |
|---|---|---|---|
| The market answer is fixed for one opening of the dialog | Opus finding 5: opened 15:29:55 keeps Confirm on after 15:30 (the server refuses); opened 09:14:50 stays grey after 09:15 until reopened | ADR-330 (60) | the dialog re-asks while open, or on Confirm |
| Mutations not pinned by a test: the stale-answer sequence guard, the page-close clearing of the waiting change, re-ask when the orders change | Opus finding 4 | ADR-330 (59), (60) | tests added |
| Positions / Alerts dialogs with the market closed are covered by the shared component only | no PaperStrategies test with the closed answer | ADR-330 (60) | one Positions test |
| DayLabel uses the host locale's day names | `strftime("%A %d %b")`; nothing calls setlocale today | ADR-330 (60) | an English table |

## PC steps, market CLOSED (round 2 Sat 21:00 or round 3 Sun 12:00): item 2

Expected text (all): "The market is closed. Exits can be placed from 09:15 on Monday 30 Nov." (Monday after that weekend); Confirm grey; the legs the exit would close are listed.

A. Feed running. Builder, open a paper trade, tick one leg, Exit. Expected: the dialog opens with the leg, the line above, Confirm grey; Cancel; no order in the Orderbook. Repeat with Exit all (one row per open leg, same line).
B. Feed stopped (stop the feed process, API up). Same steps. Expected: the same line (not "Prices are not live"), Confirm grey.
C. Positions > Paper > tick a leg, Exit; and Exit all if offered there. Expected: the same line, with the feed running and stopped.
D. Stop the API for 10 s, then press Exit. Expected: "The market status could not be read. Try again in a moment." and Confirm grey; start the API and reopen: the market line.

## Monday 09:30 steps (items 1 and 3; need an exit that completes)

1. Exit all with a staged change: builder, a paper trade of at least 2 legs, raise one leg's lots (do not Review). Exit all. Expected: the dialog lists every open leg and says "Exit all closes every open leg. The change waiting on <leg> is not sent and will be discarded." Cancel: the raised lots are back exactly, no exit staged. Exit all again, Confirm: every leg is exited and the screen says "The change waiting on <leg> was discarded."; the Orderbook shows only the exits.
2. Unknown outcome (stop the API right after pressing Confirm for a one-leg Exit): the dialog says it could not confirm the order; Confirm stays grey past 5 s; the page says "The first exit's outcome is being checked; no second exit is sent until the book has been read." Start the API and press "Open Orderbook" after 5 s: if the exit is in the Orderbook the leg shows as exited; if not, the leg is open and Exit works again. Never two exit orders for one click.

## Paper-only table (ADR-330 (58)), items 2 and 3

Added by U2, none paper-only in logic: `usePaperExit` `unresolved` (no paper flag), `decideUnknownExit` (reads the net), `exit_market_answer` (no paper or real input), the discard sentences (page-built, no tag). Still paper-named: `usePaperExit`, `postPaperOrders` (the only exit door), `EXIT_DONE_TEXT = 'Exit placed on paper'`, the builder's `exitAllPaper` / `exitPaper`. A real exit door can call `exit_market_answer`, the lock and the dialog as they are.

## Paper-only table (ADR-330 (58))

Unchanged from Lane U's table. U2 adds no paper-only branch: the lock lives in `usePaperExit` (flags and one sentence, no paper flag) and the builder's `decideUnknownExit` reads only the book's net.

## Tasks / model / minutes

| Task | Model | Minutes |
|---|---|---|
| Item 1 build | Sonnet | 40 |
| Item 1 Tier A review | Opus (Why Opus: exit path, duplicate order) | 6 |
| Items 2 and 3 build | Sonnet | 60 |
| Items 2 and 3 Tier A review | Opus (Why Opus: exit dialogs and Exit all) | 14 |
