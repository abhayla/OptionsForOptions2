# Owner questions, 2026-11-01 (GC-MU run; written while the owner is away, run continues)

## Q-MU-1 (ANSWERED 2026-11-01 08:03 IST: higher of the two -> ADR-231): What does the roll debit limit "Rs 500 or 10% of max profit" mean?

Business call: it decides which rolls a user is refused, and the words are the owner's playbook text.

Spec basis: none - the spec says nothing about how the two parts combine (searched: roll_debit_limit, "Most debit paid
for one roll", "Rs 500 or 10", roll debit). ADR-230 (1) says only that a roll whose debit is above "Most debit paid for
one roll" is refused, with the reason. Every system playbook stores the same text: `Rs 500 or 10% of max profit`
(`backend/ofo/adjustment/system_playbooks.json`).

Real case: an iron condor with max profit Rs 8,000. 10% = Rs 800.

| Option | Debit allowed in the example | Refused at |
|---|---|---|
| A. The higher of the two (built this way, GC-MU A1) | up to Rs 800 | Rs 801 |
| B. The lower of the two | up to Rs 500 | Rs 501 |

Recommendation: A (the higher). Reason: "Rs 500 or 10%" reads as a floor for small trades (Rs 500 even when 10% is
tiny) that grows with bigger trades; B would make the Rs 500 a cap that bites on every large trade. When max profit is
unlimited or not known, A1 refuses any debit above Rs 500 as "cannot confirm" (fail closed) under either option.

Status: built as A on build/gcmu (A1, 17d98038); changing to B is one line in `backend/ofo/adjustment/liquidity.py`.
The answer goes into the spec as a decision row (GC-MU ADR range 231-239).

## Q-MU-2 (ANSWERED 2026-11-01 ~08:05 IST: count conditions -> ADR-232): Does the Live Strategies card count opportunities or inbox rows?

Business call: it is the number a user reads on the card, and it can differ from what the inbox shows.

Spec basis: ADR-230 (2) "The card shows "N adjustment opportunities", linking to that strategy's row in Positions >
Adjustment opportunities; dismissing the row there clears the mark", with the count "from the existing suggestion
records (REQ-112, REQ-162)". It does not say whether N counts records or inbox rows (the inbox groups a strategy's
records into one row, "N conditions triggered").

Real case: scenario ADJ-02's first check opens 3 records for one strategy.

| Option | The card reads | The inbox shows |
|---|---|---|
| A. Count records (built this way, GC-MU A3, d9ba48fd) | 3 adjustment opportunities | 1 row, "3 conditions triggered" |
| B. Count inbox rows | 1 adjustment opportunity | 1 row, "3 conditions triggered" |

Recommendation: A. Reason: each record is a separate condition the user may act on or dismiss on its own, so 3 tells
them how much is waiting; the link lands on the one row that lists all 3. B is one line in `open_counts`
(`backend/ofo_app/routes/adjustment_opportunities.py`) if you prefer it.

---

# Owner questions, 2026-11-01 (GC-SET run, written while the night guard blocks question boxes)

## Q-GCSET-1 (06:51 IST): restart the integration gate that the PC killed for low memory?

What happened: the integration gate for batch 2 (worktree `OptionsForOptions2-OptionsForOptions2-gcset-int2`, branch
`build/gcset-int2`, head 85fd0fa8 = steps 4c, 4e, 5a, 5a-2 and 8) was killed by Claude Code at ~06:45 because the PC
ran critically low on memory (the GC-MU session runs its own builders at the same time). Claude Code's rule: a job it
killed for memory is restarted only when the owner asks.

Already green on 85fd0fa8: full pure `tests` 8640 passed / 0 failed; both openapi drift checks; DB files
adjustment_approaches_route 64, adjustment_check 8, adjustment_opportunities 12.
Not finished: 9 DB files (user_preferences, scenario_mode, settings_route, settings_speeds_wiring, paper_settlement,
chain_live, leg_edit_route, outcome_route, order_closure_all_routes) and the full vitest run.

Spec basis: none - the spec says nothing about test scheduling (searched: memory, gate, vitest); contract §0.1 says DB
tests run one file per run and heavy jobs need enough free memory.

Options:
1. **Restart, one at a time (recommended)**: the 9 DB files strictly one after another, then vitest alone on the
   heavy slot, no builders in parallel. Lowest memory use, about 25 minutes. If green, build/settings fast-forwards to
   the batch and the run continues (market hours, 5b, step 6 guard, step 8 UI, step 9, browser proofs, close).
2. Wait for GC-MU to report no builders running, then restart.
3. Do not restart; build/settings stays at 4c029a29 (steps 1-3, 3b, 4a, 4b, 7, all gated).

Answer (owner, 2026-11-01 ~07:50 IST, chat): "Restart the gate" -> option 1, one file at a time.

## Q-GCSET-2 (09:13 IST): how should the PC be shared between GC-SET and GC-MU heavy jobs?

The memory reaper killed GC-SET's runs and waits 4 times since 06:45 and GC-MU's prepush once.
Answer (owner, 2026-11-01 ~09:15 IST, question tool): "GC-MU finishes, then GC-SET" - wait for GC-MU's heavy slot,
then run the remaining gate runs in the foreground in short chunks.

## Q-GCSET-3 (13:07 IST, information + one decision): why the VPS DB runs were slow

Owner asked (~12:45): check why the VPS is slow and fix what we cause. Read-only findings (Windows VPS 103.118.16.189):
- CPU 1% at the check, one active DB connection: nothing stuck now. The slow DB test runs (1-11 min a file) came
  mainly from our own load: every `db_run_fresh` run creates a fresh database and runs all 34 migrations, and GC-MU
  and GC-SET ran such files at the same time; GC-MU is done now.
- FIXED: 39 leftover throwaway test databases `ofo_test_tmp_*` (0.43 GB, some from 2026-10-23, left when a run's drop
  step failed, e.g. on a tunnel drop) dropped with the tool's own `db_run_fresh.py --sweep` (older than 24 h only).
- MY MISTAKE, fixed: a recursive disk-size scan I started ran ~8 min on the production box (PID 14808); killed by
  PID. No further scans.
- NOT mine, owner's decision: disk C: is 88% used (13 GB free of 110), over the 80% rule; the databases are ~1.2 GB of
  it. Recommendation: run (or check the last run of) the weekly VPS disk-hygiene job for that box (old releases,
  journals, caches); I have not deleted anything on it.
- Not a cause: the `claude.exe` process on the VPS has run since 2026-10-09 with ~4.5 CPU-hours in total.
Answer: (pending)

## Q-GCSET-4 (17:2x IST, written while the owner is away): should a rate change visibly move the builder's Greeks?

SPEC CHANGE question. The goal prompt (item 3) said: if the builder's Greeks do not move at the stored rate 0.07, treat
it as a defect, fix the class and add a test. Measured (F-82): they move only at the third decimal (per-unit Theta
15.988 -> 15.987; IV 13.10% at both rates), because the engine reads the forward from put-call parity, so a higher rate
is absorbed by a higher implied dividend yield (q for 9 Nov -0.0000115 -> 0.0050063). The rate does reach the builder:
`tests_app/test_scenario_rate_wiring.py` core test passes ("figures changed by the rate: dividend_yields, legs, table").
Making the Greeks visibly move needs q held fixed, which changes the pricing model.

Spec basis: ADR-220 ("pricing model kept"); ADR-061 and ADR-063 (forward from parity; the engine owns q); REQ-167 AC-1
(the registry's "what it changes" line for `pricing.risk_free_rate`).

Options:
1. **Keep the model; reword the Settings line (recommended).** Say the rate sets the forward and, on a liquid chain,
   mostly shifts the implied dividend yield, so prices and Greeks move very little. No pricing change, no risk.
2. Keep the model and the current wording (the line over-states the visible effect).
3. SPEC CHANGE: change the pricing model so the rate moves IV and Greeks directly (reverses ADR-220's "pricing model
   kept"; Tier A; its own contract).

Answer (owner, 2026-11-01, question box): "(a) Fix the text only (Recommended)"; then "assume a role of expert option
trader ... take a decision ... proceed with your recommendation". Recorded as ADR-222 (12); registry line reworded.
