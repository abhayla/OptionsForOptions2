# Fix plan in batches of 6-8 h, one after another (owner 2026-11-07 ~03:xx IST)

Owner: "Let's not build everything together ... 6 to 8 hours ... top priority item first, then the second one after the
first one is complete." Then: "Save the plan and create goal contract to work on batch 1 now."
Minutes are the reviewed figures (plan-v5-estimates.md, independent review). Each batch: 3-4 builders in parallel,
then merge, impact tests (changed files + direct importers), Tier A review for any migration, one screen check on test
data. No PR, no CI, no push, no full gate. Elapsed per batch includes ~30% overrun (measured on past rows).
Priority: wrong numbers / wrong alerts first, then order and exit safety, history and lists, settings, polish.

| # | Batch | Issues | Builders (min) | Elapsed | Contract |
|---|---|---|---|---|---|
| 1 | Trustworthy rules and prices | 65/89/36 (migration), 63/64, 79/87/77/91, gate leftovers, 49/45, 72/73 | 235 / 225 / 185 | ~7.5 h | goal-contract-fix-batch1-2026-11-07.md (APPROVED) |
| 2 | Alerts and exit safety | 57/59/60/69/90; 88/81/12 + ADR-270 (migration); 43 (migration); 15/52 | 190 / 100 / 150 / 130 | ~7 h | not written |
| 3 | Orders, history, lists | 80/30/84/39 (design first, migration); 23/44 + 40/41/21; 25/71; 11/38 | 220 / 170 / 175 / 150 | ~7.5 h | not written |
| 4 | Settings and builder | settings widening + 47; ADR-264 lock (migration); 48/82/7-86/2 | 160 / 230 / 155 | ~7.5 h | not written |
| 5 | Money display and data | ADR-263 (server + screens); 83; 70/17 + 1 (decision row first) | 180 / 180 / 260 / 240 | ~8 h | not written |
| 6 | Roll and polish | 68 (2 builders, migration); 20 + 42; 37/32/35/22/8/9/26/78; 28/66/55 + 5/46/13 + 74/61/62/14 | 200 / 155 / 140 / 190 | ~7 h | not written |
Total ~45 h elapsed in sequence (vs ~23 h all at once): each batch repeats ~2.5 h of merge, review and test.
