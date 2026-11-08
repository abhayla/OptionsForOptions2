# Iron condor fix plan v3 for owner approval (7 Nov 2026 ~01:1x; nothing built until approved)

Scope of "implementation" (owner 7 Nov ~01:2x, question tool): coding + unit tests for the changed code and files
only, INCLUDES on-screen testing (visible Chrome, test data) at the end of each group; no PRs, no CI.

Estimate basis (measured): on 6 Nov five fixes (issues 3, 6/16, 24, 31, 34) were coded and unit-tested between ~12:20
and 13:45 by 2-3 builders in parallel: ~20-40 min each for a 1-3-file change (e.g. issue 31 found ~13:2x, commit
e97ee712 13:40). Sizes: S = 15-30 min (1 file + its test), M = ~1 h (2-4 files), L = 2-2.5 h (5+ files, a store or a
data repair), XL = ~5 h (new flow). Builder time; with 2-3 builders in parallel the elapsed time is about one third.

## Every issue found in testing (1-91) and what happens to it
Already fixed and verified on 6 Nov (no work): 3, 6, 16, 24, 27, 29, 31, 34.
Withdrawn / closed / verified OK (no work): 10, 19, 56, 58, 67 (my tool, fixed).
Parked, mobile out of scope: 50, 51, 53, 54, 76.
Observe only, no code: 18 (DB tunnel dropped once).

## P0 - wrong information a trader acts on / blocks real orders (~10 h)
| # | Issues | What | Size | Est. | Why that size |
|---|---|---|---|---|---|
| P0-1 | 65, 89, 36 | Rule baseline stored once at tracking start; one function for screen + background check + background write; repair wrongly stored rows | L | 2.5 h | 3 callers + store + repair script + 3 unit tests |
| P0-2 | 79, 87, 77, 91 | Stale prices on Compare and tracking panel (ADR-272); Compare uses market clock and fresh spot | L | 2 h | approaches route + 2 Vue components + clock source |
| P0-3 | 49, 45 | Stale legs marked at mid; loss above max loss = "not checked" (ADR-266) | M | 1 h | marking function + check guard |
| P0-4 | 47 | Planned entry at bid-ask mid, setting, credit > width warning (ADR-265) | M | 1 h | capture + setting + warning |
| P0-5 | 1 | Delist guard tells wing narrowing from a truncated file | M | 1 h | one guard + its test |
| P0-6 | 70 | Builder blank after close (regression): find cause, fix | M | 1.5 h | includes reading for the cause |
| P0-7 | 17 | "No live quote / no IV" after an exit | M | 1 h | may share P0-6's cause |

## P1 - decided behaviours (~22 h + settings framework)
| # | Issues / decision | What | Size | Est. |
|---|---|---|---|---|
| P1-1 | 15, 52 | Exit confirm: max loss and margin before -> after, unprotected-short warning | M | 1 h |
| P1-2 | 43 | Stop on a sold leg also closes its wing (ticked by default) | M | 1 h |
| P1-3 | 57, 59, 60, 69 | Day rules / user watches never held by the daily cap; every record has its text | M | 1.5 h |
| P1-4 | 63, 64 | Intrinsic-only delta 1/0; T-01 flags at or beyond the short | S | 30 min |
| P1-5 | 81 | T-19 always shows a result at the adjustment limit | M | 1 h |
| P1-6 | 88 | Passing rules listed with value / limit; IV compared at shown precision | M | 1 h |
| P1-7 | 72, 73 | Paper strategies cannot be deleted; Undo in the fixed toast | S | 45 min |
| P1-8 | 23 | Partial exits count as adjustments, Exit all does not | S | 30 min |
| P1-9 | 80, 30 | One order per contract and side in a basket, split by freeze qty | S | 45 min |
| P1-10 | 84, 39 | History names the Compare approach | S | 30 min |
| P1-11 | 11, 38 | One alert list; bell counts live strategies only | M | 1.5 h |
| P1-12 | 25, 71 | Completed Strategies; closed strategy reopens as "All legs closed" | M | 1.5 h |
| P1-13 | 4 | Headline money after charges, labelled; payoff table matches | M | 1 h |
| P1-14 | (decided) | Compare always available without an alert | S | 20 min |
| P1-15 | 83 | Ready-made IC shorts by delta (default 0.20), user preference | M | 1 h |
| P1-16 | (decided) | T-11 / T-14 evaluated on live strategies | S | 30 min |
| P1-17 | 68 | Roll to a later expiry closes and opens a linked strategy | XL | 5 h |
| P1-18 | 20 | Generic rules for a shape left after a wing exit | L | 2.5 h |
| P1-19 | (decided) | Settings framework (admin default, user override, lock) | ? | measure first (30 min read) |

## P2 - correctness and display (~7.5 h)
| # | Issue | What | Est. |
|---|---|---|---|
| P2-1 | 37 | "Add booked P&L" box changes the payoff table | 30 min |
| P2-2 | 5 | P&L % bases labelled / one base | 20 min |
| P2-3 | 22 | Exit-whole max loss Rs 193 gap: measure, fix if real | 20 min |
| P2-4 | 13 | Old opportunity rows with wrong %: measure, fix if real | 15 min |
| P2-5 | 41 | Paper summary not blanked by one unpriced old position | 30 min |
| P2-6 | 46 | Paper panel first paint shows "loading" | 20 min |
| P2-7 | 48 | Unsaved builder draft restored | 1 h |
| P2-8 | 42 | Alert -> Compare opens with a usable prepare list | 20 min |
| P2-9 | 40 | Paper list counts open legs only | 15 min |
| P2-10 | 44 | Conditional-exit orders labelled correctly | 15 min |
| P2-11 | 28 | Polling: one combined read, longer interval | 1 h |
| P2-12 | 55 | Price-bus payload trimmed, reconnects logged | 1 h |
| P2-13 | 82 | Failed-load message next to the control + Retry | 30 min |
| P2-14 | 7, 86 | Plan dialog shows "loading" | 20 min |
| P2-15 | 2 | OI column one format | 15 min |

## P3 - wording batch (~1.5 h)
8, 9 (date formats), 12 (raw 4-decimal values, units), 21 (units vs lots), 26 ("Zerodha" header on paper), 32 (A-26
"fallen" when it rose, "1 lots"), 35 / 85 (strike quoted as price), 78 ("not finite" at zero), 90 (raw
"day.beforeWeekend.1500.0"), A-26 max profit "if NIFTY falls to 0" note.

## P4 - tests, tooling, ops (~3 h)
| Issue | What | Est. |
|---|---|---|
| 74 | Stale downgrade test runs from its own head | 30 min |
| 14, 75 | Launcher restarts every role on a code move | 1 h |
| 61, 62, 66 | Test-data copy: background checks after frame moves, index display, pool size | 1.5 h |

## Totals
| Group | Builder time | Elapsed with 2-3 builders |
|---|---|---|
| P0 | ~10 h + on-screen test ~1.5 h | ~5.5 h |
| P1 | ~22 h + framework + on-screen ~2 h | ~10 h + framework |
| P2 | ~7.5 h + on-screen ~1 h | ~4 h |
| P3 | ~1.5 h | ~1.5 h |
| P4 | ~3 h | ~1.5 h |
| All | ~44 h + framework + on-screen ~5 h | ~23 h + framework |
