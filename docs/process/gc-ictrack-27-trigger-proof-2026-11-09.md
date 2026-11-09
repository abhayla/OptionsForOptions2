# GC-ICTRACK core proof, test data (row 27p, ADR-276 (6)), 2026-11-09

Method: the real background Worker (`background.Worker.cycle`, `owner_lister`, the worker's own state build) ran on
every iron condor scenario of the library, seeded on a throwaway database migrated to head (ofo_dev untouched).
The state the worker evaluated was captured and evaluated with the iron condor body with all 27 triggers on.
Inputs a real strategy has were supplied as production does: entry facts (entry spot), one level watch above
spot-50, the lister's charge-rate source, a fresh rate limiter per scenario. Harness: `tests_app/test_zz_proof27_tmp.py`
(not committed); per-scenario records in the run's scratch folder.

Scenarios: 46; evaluated 42; ADJ-19, ADJ-24a, ADJ-24b paused by the worker's stale-feed rule (their purpose);
ADJ-45 refused by the seeder (adjustments_used mismatch).

| Trigger | Fired | Clear | Not checked (reason) | Example fired (scenario: value vs limit) |
|---|---|---|---|---|
| T-01 | 16 | 26 | - | ADJ-02: 0.3416 vs 0.5 |
| T-01b | 14 | 28 | - | ADJ-02: 80.00 vs 120 |
| T-02 | 2 | 40 | - | ADJ-05: -474.50 vs 0 |
| T-03 | 8 | 34 | - | ADJ-02: 0.4103 vs 0.35 |
| T-04 | 16 | 26 | - | ADJ-02: 0.2120 vs 0.15 |
| T-05 | 11 | 20 | side_value_not_positive 11 | ADJ-02: 29.5135 vs 3 |
| T-06 | 1 | 41 | - | ADJ-11: 54.9578 vs 50 |
| T-06b | 1 | 41 | - | ADJ-11: 2.188 vs 1 |
| T-07 | 11 | 31 | - | ADJ-07: 64.7107 vs 50 |
| T-08 | 6 | 36 | - | ADJ-02: 2.0024 vs 2 |
| T-09 | 20 | 22 | - | ADJ-02: 2.7 vs 3 |
| T-10b | 7 | 8 | no_stage_value 27 | ADJ-09: 14:46 vs 14:30 |
| T-11 | 5 | 37 | - | ADJ-06: 4.051 vs 3 |
| T-11b | 1 | 0 | missing_vix 41 | ADJ-60: 12 vs 10 |
| T-11c | 0 | 1 | missing_vix_percentile 39, sensex_no_vix 2 | - |
| T-12 | 1 | 41 | - | ADJ-11: 1.5638 vs 1 |
| T-13 | 0 | 0 | gap_after_open 40, missing_day_open 2 | - |
| T-14 | 0 | 0 | missing_margin 42 | - |
| T-14t | 3 | 36 | no_premium_left 3 | ADJ-04: 3.2695 vs 5 |
| T-14v | 13 | 29 | - | ADJ-01: 13.7243 vs 10 |
| T-15 | 0 | 0 | missing_margin 42 | - |
| T-16 | 0 | 0 | switched_off 42 | - |
| T-18 | 1 | 41 | - | ADJ-12: 2 vs 2 |
| T-19 | 0 | 0 | no_approach_priced 42 | - |
| T-20 | 42 | 0 | - | ADJ-01: 23050 vs 23000 |
| T-20b | 1 | 0 | missing_adx 41 | ADJ-60: 100 vs 25 |
| T-21 | 0 | 0 | - | - |

Result: 21 of 27 triggers proven on test data (20 fired in at least one scenario; T-11c read its input and was clear).
Not proven on test data: T-14 and T-15 (the test-data checker has no margin reader: #676); T-13 (checked only before
09:30, scenario clocks are later); T-16 (switched off in the IC defaults; margin-based, so also #676); T-19
(no approach priced in this harness, cause not proven; covered by the worker's own T-19 tests, ADR-254); T-21 (a
suggestion gate, not a firing trigger). The live record (task 37) covers T-13, T-14, T-15 and T-19 on real prices.

## Live data (task 37, 2026-11-09 09:16 IST, owner's Kite session)

India VIX 18.29, previous close 18.43 (the close of the Diwali Muhurat session on Sunday 8 Nov, present in Kite's daily
candles; last night's "previous close equals Friday" puzzle was correct data, not a defect). VIX percentile (250
sessions) 83.2; NIFTY ADX(14) 35.16. The live checker wrote the daily ATM IV row (NIFTY, 2026-11-09, 0.407059, 09:15:06).

`POST /api/playbooks/test` (the one state build `state_of`, live prices), iron condor body with all 27 triggers on,
strategy 92 "UT IC 9Nov G" (paper IC on real contracts, expiry today): 23 of 27 checked. Fired: T-01 (spot beyond the
sold 24,950 CE by 24.75 points), T-01b 24.75 vs 70, T-03 0.537 vs 0.40, T-11c 84 vs 80, T-15 99.7 vs 80 (paper margin
against the account's free margin), T-20b 35.16 vs 25. Clear (checked): T-02, T-04, T-05, T-06, T-06b, T-07, T-08, T-09,
T-10b, T-11b, T-14, T-14t, T-14v, T-16, T-18, T-19, T-21. Not checked: T-11 and T-12 (no entry IV: entered 11-06,
before the entry-IV writer), T-20 (no level set), T-13 (previous close absent in market hours, ADR-212).

**Background checker (the one that alerts by itself), live:** checking (fresh reads, flags raised) but T-13, T-14,
T-15 and T-16 answer missing_prev_close / missing_margin: its process holds no Kite session of its own (#627).

**Owner decision (2026-11-09 ~09:2x):** "Consider T13 to T16 as completed." Recorded as accepted by the owner, not
proven in the background checker; #627 (live) and #676 (test data) stay open.

Also found (issue #678): the playbook-test route lists scenario test strategies (23 of 24 tested) in live mode; the background
checker keeps them apart.
