# Verifier results: rows 12-14 start check (REQ-072, REQ-032, REQ-033), 2026-10-23 - for recording evidence at their close

Non-DB part: Opus verifier, fresh context, head f9a8d780 (brief `verify-rows-12-14.md`). DB part: Sonnet verifier, head
fb9a3702, 9 queued files through the lock: `224 passed in 397.44s`, no failures. Scratch:
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\b9b5cb32-ea0c-400f-80e1-fbd7045cbf2a\scratchpad\verify-12-14`
(may be gone after the session; this file is the record). AC fingerprints: recompute with `fps_wt.py` at close.

| Row | REQ | AC | Result | Observed (file:line) / attack |
|---|---|---|---|---|
| 12 | REQ-072 | AC-1 | pass | index ids NSE_INDEX:1001 / BSE_INDEX:1 (parser.py ZERODHA_INDEX_SEGMENT, models.py:39-40); a SENSEX leg in a NIFTY strategy refused, naming SENSEX; the NSE cash row sharing token 1001 handled |
| 12 | REQ-072 | AC-2 | PARTIAL (MINOR) | stale spot (+90 s, +3 h) labelled "stale since 09:20 IST"; unavailable after a disconnect refused; BUT a missing index quote with the feed live is refused with the forward reason, not the index reason - service.py:439-443 adds forward errors before the spot gate at :445-456. Fix: `row-12-fix-1.md` |
| 12 | REQ-072 | AC-3 | pass | CURRENT column 22533.25 = spot, spot_at 09:20:09; forward 22529.17 and q 0.0775825852 equal an independent median parity calculation (21 strikes); chain stale -> "estimated from spot" |
| 13 | REQ-032 | AC-1 | pass | table, payoff and summary from one scenario_values call (service.py:469); only math outside the engine is marketdata/forward.py (q, an engine input per ADR-063); PayoffChart.vue only Number() for plotting |
| 13 | REQ-032 | AC-2 | pass | engine/inputs.py:34-124 carries every listed field, plus margin and charges |
| 13 | REQ-032 | AC-3 | pass | Hull reference call 4.76 / put 0.81; textbook formulas in black_scholes.py |
| 13 | REQ-032 | AC-4 | pass | -322.50 exact; floats only inside black_scholes.py and forward.py (levels and a yield, Decimal at output) |
| 13 | REQ-032 | AC-5 | pass | display.py:65-74 shows ~Rs and ~% |
| 13 | REQ-032 | AC-6 | pass | interfaces.py:52-89 MarginPlanner and ChargesModel |
| 14 | REQ-033 | AC-1 | pass | 96 of 96 per-leg cells equal the hand formula; mutants ce/pe_intrinsic_floor, sell_sign killed |
| 14 | REQ-033 | AC-2 | pass | 5 levels on real frames equal to the paisa |
| 14 | REQ-033 | AC-3 | pass | worked check 56812.50 (entry price, not LTP); planned entries != LTP, cells match |
| 14 | REQ-033 | AC-4 | pass | live P&L 260.00 by hand and from the engine |
| 14 | REQ-033 | AC-5 | pass | 4 legs x 24 levels, 0 blank cells |
| 14 | REQ-033 | AC-6 | pass | breakevens 22381.1 / 22718.9, max 4478.50 / 2021.50 equal hand figures; golden 22909 / 23491 |
| 14 | REQ-033 | AC-7 | pass | 0 mismatches on 4 live legs, total 1365.00, 21 levels, 4 samples, credit 6825, max loss 8175 |

Hand computations (recorded frames 2026-10-08 09:20:09, NIFTY 13-Oct, lot 65): spot 22533.25; condor BUY 22350 PE @
66.85, SELL 22450 PE @ 102.35, SELL 22650 CE @ 83.30, BUY 22750 CE @ 49.90. Expiry P&L 22200 = -2021.50, 22500 =
4478.50, 22700 = 1228.50; live P&L 260.00; 22450 PE mid 100.40 IV 0.126717 delta -0.4051; 22650 CE mid 81.70 IV
0.123521 delta 0.3615 - engine identical; the shared (row 8) read equals the unshared read.

Expiry day: at 15:29:59 the engine values 3.17e-8 years left; at 15:30 and after the legs read "expired".

Mutation (24 mutants, verifier's script): 21 killed; survived - `shared_greeks_key_iv` (removing IV from the shared
Greeks cache key; = the #519 class), `days_in_year_guard` (`_check_greek_inputs` untested), `bs_float_boundary`
(effectively equivalent). The first two -> one deferred MINOR issue at the rows' close.

Spec drift found here, now DECIDED: IV from the bid-ask mid vs the locked "LTP" text -> ADR-172 (owner 2026-10-23: mid
when two-sided, else LTP); the code already matches.

Guard tests 1366 passed (4 skipped); repo_scan 1216 passed (1 skipped); engine 724, scenario 38, table 58, outcome
84, marketdata 216, instruments 78 passed. Harness note: tests/engine and tests/table in ONE pytest call fail at
collection (two `conftest` modules with the same name); each folder passes alone.
