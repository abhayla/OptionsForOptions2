# Iron condor fix plan v4 (code-verified) for owner approval - 7 Nov 2026; nothing built until approved

Scope (owner): every issue found in testing, incl. the 3 items I first called "features" (they are small changes on
existing code). Implementation = code change + unit tests for the changed code + a test of what changed + on-screen
check. No PRs, no CI.

How this version was made: 4 read-only code checks (rule engine; Compare/orders; builder/data; display/tooling/gate),
each item located to file:line, then spot-checked by me (planned_entry.py:36 LTP-first; strategy_store.py:115
_CAN_DELETE_SQL has no paper orders; MyStrategiesPage.vue:24 COMPLETED_STATUSES = []; paper_monitor.py:232 every
trigger order kind "stop"; alert_gate.py:275 the daily cap counts every rule; background.py:749 rule memory only in
process; StrategyBuilderPage.vue:143 `Number(id)` breaks the ADR-008 guard; config.py:46 DB_POOL_SIZE default 2;
approaches.py:465 target-delta strike pick exists). Minutes = code + unit tests (checkers' figures, mid of range).

## What was removed or merged, and why
| Was | Now | Why | Saved |
|---|---|---|---|
| 65, 89, 36 as 2 items | one: rule memory loaded from the DB + baseline at entry + ADR-258 re-baseline | same cause (background.py:1187/1207, adjustment_check.py:535) | ~1 h |
| 81 (T-19 missing) | inside 88 | T-19 is a PASSING rule; passing rules are never output (playbook_eval.py:801-806) | ~1 h |
| 12 (raw 4-decimal values) | inside 88 | same value formatter | ~30 min |
| 90 (raw "day.beforeWeekend") | inside 57/59/60/69 | same "every record carries its text" path | ~40 min |
| 17 | inside 70 | same bus-mode after-close quote cause | ~1 h |
| 7 and 86 | one | same dialog | ~20 min |
| 35 and 85 | one | same line legEdit.js:167 | ~10 min |
| 30 + 80, 39 + 84 | one change on the paper order post | same POST (paper.py:726) | ~45 min |
| 23 and 44 | one | both change the history step / order kind | ~30 min |
| 72/73, 25/71, 4 | one list change | same list query + Completed page | ~1.5 h |
| 83 new delta placement | reuse Compare's target-delta strike pick (approaches.py:465) | code exists | ~1.5 h |
| 43 new trigger column (migration) | add the wing as a second target at fire time | no migration needed | ~1 h |
| ADR-264 "framework" (unmeasured) | only the admin lock flag in layers.resolve | 3 layers + 99-key registry already exist | ~3 h+ |
| 68 "new feature" | link + close/open on the existing next-expiry roll (A-04/A-05 exist) | roll code exists | ~1 h |
| P3 as its own round; a screen test per group | wording inside each lane; ONE screen test at the end | one test session covers all | ~3 h |

## The plan: 4 parallel lanes (each lane owns files no other lane touches, so no merge clashes)
Lane A - rule engine and alerts (~11 h builder)
| Issues | Fix | Min |
|---|---|---|
| 65, 89, 36 | load rule memory from the DB before the first check; store the baseline at entry; re-baseline after an adjustment; repair rows written after a crossing | 120 |
| 57, 59, 60, 69, 90 | day rules and user watches skip the daily cap; pass the user values with `.own` (background.py:1144); every day-rule record has text | 90 |
| 88, 81, 12, ADR-270 | output passing rules with value/limit (2 decimals + unit); T-14 live (one line); T-11 entry IV stored at entry | 150 |
| 63, 64 | delta 1/0 at intrinsic; T-01 at/beyond the short | 50 |
| 49, 45 | stale leg marked at bid-ask mid; loss above max loss = not checked | 75 |
| 11, 38 | bell and inbox drop deleted strategies; one alert list | 120 |
| 20 | generic rule set (stop, target, distance to shorts) for an unmapped shape | 80 |

Lane B - Compare, orders, exits, history (~13 h builder)
| Issues | Fix | Min |
|---|---|---|
| 79, 87, 77, 91 | stale flag + age on the approaches reply; no leaders when stale; Prepare disabled; Pause box + tracking panel read `withheld`; test the 14:30 time-exit clock | 140 |
| 15, 52 | exit confirm: max loss and margin before -> after, unprotected-short warning | 90 |
| 43 | stop on a sold leg also exits its wing (second target at fire time) | 60 |
| 23, 44 | Exit all is not an adjustment; conditional exits get their own order kind | 85 |
| 80, 30, 84, 39 | one order per contract and side (split by freeze qty); approach id stored and shown in history | 130 |
| 68 | next-expiry roll closes the strategy and opens a linked one | 240 |
| 42, ADR-261 | Compare from an alert shows all approaches; Compare always available | 45 |
| 37, 32, 35/85, 22, A-26 note | booked P&L box; A-26 wording; price not strike; verify the Rs 193 gap; "if NIFTY falls to 0" | 100 |

Lane C - builder, data, settings (~11 h builder)
| Issues | Fix | Min |
|---|---|---|
| 47, ADR-264, 83 | mid-first planned entry + setting; admin lock flag; ready-made IC by delta via the existing delta pick | 240 |
| 1 | delist guard passes a contiguous wing trim | 60 |
| 70, 17 | find the after-close cause in bus mode; keep the last close on the API side | 150 |
| 72, 73, 25, 71, 4 | paper strategies not deletable; Undo in the toast; Completed derived from "all legs closed"; a closed strategy reopens with its result; headline money after charges, labelled | 200 |

Lane D - display, load, tooling, gate (~7 h builder)
| Issues | Fix | Min |
|---|---|---|
| gate (5 failures) | finding `scope`; spec digest; 20 coverage rows; test map entry; StrategyBuilderPage.vue:143/651/658 maths into lib; openapi.json | 60 |
| 48, 82, 7/86, 2 | draft kept in sessionStorage; error next to the expiry box + Retry; dialog loading line; one OI format | 135 |
| 40, 41, 21 | open legs only in counts; closed books do not blank the total; server sends lots on closed rows | 60 |
| 8, 9, 26, 78 | dates as "17 Nov" / IST; "Fill" header; "max profit is zero" wording | 35 |
| 28, 66, 55 | poll interval / pool default / stream length | 35 |
| 5, 46, 13 | locate, then fix (not located yet) | 50 |
| 74, 61, 62, 14/75 | downgrade test from head; test-data copy RCA; launcher restarts every role | 110 |

## Totals
| | Builder time | Elapsed |
|---|---|---|
| Lanes A-D in parallel | ~42 h (A 11, B 13, C 11, D 7) | longest lane (B) ~13 h |
| Merge the 4 lanes, unit tests of touched files | | ~1 h |
| One on-screen test of every fix (test data, Chrome) | | ~2.5 h |
| **All issues** | **~42 h** | **~16 h** (about 2 long sessions) |

v3 was P0+P1 only at ~18-19 h elapsed; v4 is every issue (~65 items) in ~16 h elapsed.

## How it can be made faster still (owner's choice)
1. Split lane B into two lanes (68 + 15/52 on their own): elapsed ~12 h, same builder time; costs a 5th builder at once
   (memory ~5 GB free: tight but possible).
2. Move 68 (roll to a later expiry as a new strategy) to a later round: the only item that changes a core flow;
   -4 h builder, elapsed ~12 h without a 5th lane.
3. Leave out the 3 unlocated items (5, 46, 13) and the test-data tooling (61, 62) unless quick: -2 h builder.
Risks that add time: the cause of 70/17 is not found yet (+1-2 h); the DB repair in 65 if many rows are wrong (+1 h).
