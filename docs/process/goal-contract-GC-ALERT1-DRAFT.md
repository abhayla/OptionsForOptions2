# Goal contract GC-ALERT1 (DRAFT for owner approval): alert discipline, check speed per style, background check off the database

Core: a rule value that wobbles across its line raises ONE adjustment suggestion per crossing episode, not one per
crossing (REQ-170 AC-1), computed by a pure gate (no DB, no Redis). Proof (step 1): the gate replays two real
2026-11-02 cases and gives the counts derived independently in step 0 (not assumed): strategy 66 T-07 (30 records
10:38-11:09 IST that day) and strategy 67 T-07 (23 records 10:38-11:10).

Status: DRAFT 2026-11-02 after GC-LIVE3, revised after an independent review (Sonnet, FIX FIRST, all findings
accepted). Not run until the owner approves.

DATES: every time written in a record comes from `date` in the same step. NIFTY nearest expiry on 2026-11-02 was
2026-11-03; strategies 66 / 67 / 78 / 79 expire 3-9 Nov, so live steps need fresh paper strategies.

## Scope and branch
- Tree `D:\Abhay\Ventures\OptionsForOptions2-OptionsForOptions2-settings`, branch `feature/adjustments` (after the
  GC-LIVE3 push). Nothing to main without the owner's explicit OK. Paper only.
- In scope: REQ-170 (Approved 2026-11-02), ADR-235 (check speed per style), #636 round 4 (design: #636 comment
  2026-11-02 ~13:20). "Part of #636" wording, never close keywords.
- Out of scope: the logged-in T3 re-run (ADR-234 (6), its own morning step), #616, #615 / F-97, C1 latency.

## Open owner question (asked at approval, one question)
- When the user DISMISSES a suggestion, does that rule's cool-down restart from the dismissal (quiet for 30 min on
  weekly) or does the rule re-arm only by clearing the line? Decide with the actor-intent table (spec-first R3b).

## Steps (each brief: Core / Proof / Class / Budget / evidence-table; B4 standing items)
| # | What | Done when (evidence) | Budget |
|---|---|---|---|
| 0 | DATA FIRST: rebuild the 66 / 67 rule-value paths for 10:30-11:15 on 2026-11-02. Real data on disk: `D:\Abhay\scratch\gclive3\inbox-1150.json` (record times, values, thresholds; no dip depth). Try Kite 1-minute candles per leg (broker status said `historical_data: not_available` on 2026-11-02: likely unavailable); else the scenario library + those real record times as anchors (memory `scenario-test-data-over-live`). Fixture holds derived percentages only, never Kite quotes. Write the strategies' expiries (66 likely 3 Nov = intraday preset) and the expected counts per preset, derived by hand | fixture + a hand-derived expected count per preset, committed | 30 min, 40 calls |
| 1 | CORE: the pure gate (edge not level, confirm on candle close, cool-down, re-arm margin, escalation, daily cap, quiet time) replays step 0 | counts equal step 0's hand-derived numbers; test red first | 45 min, 60 calls |
| 2 | SPEC RECONCILE (before wiring): (a) define the re-arm margin's base ("entry value" is undefined in the spec); (b) candle-close confirmation needs a time-driven wake while ADR-235 (3) checks only on price change; (c) ADR-235 (4) "recorded within the check interval" vs REQ-170 confirm delay; (d) where "held" crossings (AC-4) are stored (likely a migration: separate draft PR) | spec text + decision rows written; owner asked only if a product choice remains | 30 min |
| 3 | Settings: admin defaults per style (registry), cap ceiling with a rejection test (AC-6), user values on the Preferences tab per style (REQ-168), style from the strategy + a per-strategy pin and its screen; new texts pinned in `tests/errors/template_pins.json` | tests; Preferences tab and pin screen seen in the owner's Chrome (390 px + desktop) | 60 min, 80 calls |
| 4 | #636 round 4 FIRST in the worker (structure): merge the base branch, guard tests, record the merge commit in #636; memory-only check path (settings cache resolved against the clock, count poll 2-5 s, rebuild kept, plan change resets the signature, writes via one queue). Tier A: Opus builder + Opus checker (`Why Opus:` line). Time-box one round + checker; red -> PARK and wire steps 5-6 on the old path | zero DB calls per check in steady state; future-dated setting applies with no write; connection budget: API 2 + background + feed + writer + poll within the role limit of 5 | 60 min, 80 calls |
| 5 | Wire the gate into the worker (after 4, same file, one after the other); risk exits never call the gate (AC-5 test) | worker tests incl. restart, dismissed record, plan change, day rollover states | 45 min, 60 calls |
| 6 | ADR-235: three check-speed settings per style; the worker uses the strategy's style interval | tests: 0-1 day 10 s, weekly 30 s, monthly 120 s | 30 min, 40 calls |
| 7 | LIVE (needs a market day): owner Kite login; portable Redis 5 started (`D:\Abhay\tools\redis5`, memory `dev-redis-5-portable`); three fresh paper strategies (intraday / weekly / monthly); owner's visible Chrome; background on, no app tab; count records per strategy per hour | counts vs 2026-11-02 baseline (103 records shown 09:30-11:50 that day, 75 of them lapsed); written into REQ-170 | market hours |
| 8 | `coord.py take-heavy`; no tracked-file edit while prepush runs; generated files via `regen.py` only, out of feature PRs; one `prepush --full`; push; handover | TOTAL PASS + push line | 60 min |

## Rules
- 2 fix rounds per class, then park; a second red of the same class gets an independent reviewer first.
- Memory: under 3.0 GB no builder dispatch; one DB test file at a time on a throwaway DB.
- Owner questions only for business calls.

## Definition of Done
- [ ] Step 0 data + hand-derived counts, then the core proof (step 1), before any other code.
- [ ] Spec reconciled (step 2); REQ-170 AC-1..AC-7 and ADR-235 built with tests; #636 round 4 built or PARKED with
      its reason; live counts recorded, or step 7 PARKED if no market day falls inside the run.
- [ ] Full gate TOTAL PASS; feature/adjustments pushed; handover written.
