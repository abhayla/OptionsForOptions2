# Goal contract GC-ALERT1: alert discipline, check speed per style, background check off the database

Core: a rule value that wobbles across its line raises ONE adjustment suggestion per crossing episode, not one per
crossing (REQ-170 AC-1), computed by a pure gate (no DB, no Redis). Proof (step 1): the gate replays two real
2026-11-02 cases and gives the counts derived independently in step 0 (not assumed): strategy 66 T-07 (30 records
10:38-11:09 IST that day) and strategy 67 T-07 (23 records 10:38-11:10).

Status: APPROVED by the owner 2026-11-02 20:4x IST (chat: "go ahead with your recommendation and give me the goal
contract"). Draft reviewed independently before that (Sonnet, FIX FIRST, all findings accepted). The draft's one open
question is answered: ADR-236.

DATES: every time written in a record comes from `date` in the same step. NIFTY nearest expiry on 2026-11-02 was
2026-11-03; strategies 66 / 67 / 78 / 79 expire 3-9 Nov, so live steps need fresh paper strategies.

## Session start (read in this order, nothing else first)
1. `git -C D:\Abhay\Ventures\OptionsForOptions2-OptionsForOptions2-settings log --oneline -5` and `git status`; the run
   works ONLY in that tree, on `feature/adjustments`. Read §Progress below; a step marked DONE is not redone.
2. `docs/process/session-handover-2026-11-02-gclive3.md` (yesterday's state), then REQ-170, ADR-235, ADR-236, ADR-217,
   REQ-112 AC-7, REQ-165, REQ-168, and the #636 comment of 2026-11-02 ~13:20.
3. `knowledge/findings/` for `check-latency-bound-by-db-round-trips`, `check-clock-read-once-per-batch`,
   `bus-consumer-holds-no-own-tokens`, `engine-input-chosen-per-caller`.
4. Memory notes `dev-redis-5-portable`, `kill-processes-for-memory`, `scenario-test-data-over-live`,
   `wording-brief-runs-name-guard`, `merge-builder-by-sha`, `prepush-every-goal-close`.

## Scope and branch
- Tree `D:\Abhay\Ventures\OptionsForOptions2-OptionsForOptions2-settings`, branch `feature/adjustments`. Nothing to
  main, no PR to main, without the owner's explicit OK. Paper only; no real orders.
- In scope: REQ-170 (Approved 2026-11-02) incl. ADR-236 (dismiss vs a worse stage), ADR-235 (check speed per style),
  #636 round 4 (design: #636 comment 2026-11-02 ~13:20), side tasks S1-S4 below. "Part of #N" / "Refs #N" wording;
  `Fixes #N` only when the whole issue is done.
- Out of scope: the logged-in T3 re-run (ADR-234 (6), its own morning step), #616, #615 / F-97, C1 latency, GC-ADJ4+.

## Owner decisions behind this contract
- REQ-170 Q-AD-1..Q-AD-5 (all answered). Q-AD-5 = ADR-236: after a dismiss, the same stage stays quiet until it
  clears by the re-arm margin and the cool-down (counted from the record, not the dismissal) has passed; one stage
  worse opens a new suggestion at once, worded "Worse than the one you dismissed"; cap and quiet time still apply.
- ADR-235: 10 / 30 / 120 s per style, admin settings. ADR-233 (3)-(6) stand.
- ADR-217, ADR-003 (decision-support wording), ADR-008 (one engine, exact decimal money).
- Test data: scenario library + one real anchor; no captured Kite quotes in the repo.

## Steps (each brief: Core / Proof / Class / Budget / `Report: evidence-table`; B4 standing items; `model` set)
| # | What | Done when (evidence) | Budget |
|---|---|---|---|
| 0 | DATA FIRST: rebuild the 66 / 67 rule-value paths for 10:30-11:15 on 2026-11-02. Real data on disk: `D:\Abhay\scratch\gclive3\inbox-1150.json` (record times, values, thresholds; no dip depth). Try Kite 1-minute candles per leg (broker status said `historical_data: not_available` on 2026-11-02: likely unavailable); else the scenario library + those real record times as anchors. Fixture holds derived percentages only, never Kite quotes. Write the strategies' expiries (66 likely 3 Nov = intraday preset) and the expected counts per preset, derived by hand | fixture + a hand-derived expected count per preset, committed | 30 min, 40 calls |
| 1 | CORE: the pure gate (edge not level, confirm on candle close, cool-down, re-arm margin, escalation, daily cap, quiet time, dismiss per ADR-236) replays step 0. Test cases include: dismiss then same level (quiet), dismiss then clears + re-crosses before cool-down (quiet), dismiss then next stage (opens, "Worse than the one you dismissed"), dismiss then next stage over the cap (held, shown) | counts equal step 0's hand-derived numbers; every ADR-236 case has a test; tests red first | 45 min, 60 calls |
| 2 | SPEC RECONCILE (before wiring), technical calls decided and recorded: (a) the re-arm margin's base ("entry value" is undefined in the spec); (b) candle-close confirmation needs a time-driven wake while ADR-235 (3) checks only on price change; (c) ADR-235 (4) "recorded within the check interval" vs REQ-170 confirm delay; (d) where "held" crossings (AC-4) and dismiss state are stored (likely a migration). Only a product choice goes to the owner (question tool, `Business call:` line; owner away -> dated owner-questions file) | spec text + decision rows written the same turn | 30 min |
| 3 | Settings: admin defaults per style (registry), cap ceiling with a rejection test (AC-6), user values on the Preferences tab per style (REQ-168), style from the strategy + a per-strategy pin and its screen; new texts (incl. "Worse than the one you dismissed") pinned in `tests/errors/template_pins.json` as pending owner read | tests; Preferences tab and pin screen seen in the owner's visible Chrome (390 px + desktop) | 60 min, 80 calls |
| 4 | #636 round 4 FIRST in the worker (structure): merge the base branch, guard tests, record the merge commit in #636; memory-only check path (settings cache resolved against the clock, count poll 2-5 s, rebuild kept, plan change resets the signature, writes via one queue). Tier A: Opus builder + Opus checker (`Why Opus:` line). Time-box one round + checker; red -> PARK and wire steps 5-6 on the old path | zero DB calls per check in steady state; future-dated setting applies with no write; connection budget: API 2 + background + feed + writer + poll within the role limit of 5 | 60 min, 80 calls |
| 5 | Wire the gate into the worker (after 4, same file, one after the other); risk exits never call the gate (AC-5 test); the screen check and the background check use the same gate | worker tests incl. restart, dismissed record, dismiss then worse stage, plan change, day rollover | 45 min, 60 calls |
| 6 | ADR-235: three check-speed settings per style; the worker uses the strategy's style interval | tests: 0-1 day 10 s, weekly 30 s, monthly 120 s | 30 min, 40 calls |
| 7 | LIVE (needs a market day, earliest Tue 2026-11-03): owner Kite login (private window); portable Redis 5 on 6380; three fresh paper strategies (intraday / weekly / monthly); owner's visible Chrome; background on, no app tab; count records per strategy per hour; dismiss one and watch it stay quiet | counts vs 2026-11-02 baseline (103 records 09:30-11:50, 75 lapsed); written into REQ-170 | market hours |
| 8 | Close: `coord.py take-heavy`; no tracked-file edit while prepush runs (run it in the background with a Monitor on its step lines); generated files via `regen.py` only; one `prepush.py --full` TOTAL PASS on the final head; push `feature/adjustments` to origin (backup, as soon as TOTAL PASS: amendment 2026-11-03); handover `docs/process/session-handover-<date>-gcalert1.md`; memory | TOTAL PASS line + push line; nothing on main | 60 min |

## Side tasks (small, technical; run beside steps 3-6, at most 2 builders at once, never in the same files as 4-5)
| # | What | Done when | Budget |
|---|---|---|---|
| S1 | #624 remainder (Tier B, Sonnet): (1) an unreadable playbook must not skip the limits silently: `read_guards` error -> reply carries "limits not applied: playbook unreadable" (or a refusal); "no playbook matches" stays None; (2) the adjust drawer flags each approach's new strike that breaks a limit ("Below your liquidity limit" / "OI not known"), per ADR-230 (1); (3) drop the test that re-implements the comparison inline | failing tests first; scenario ADJ-50 in the owner's Chrome shows the drawer flag; a broken playbook file gives the reason line, not silence | 30 min, 60 calls |
| S2 | #633 final proof (fix already merged cf20e904): on ADJ-50, T-19's named approach and cost equal the Compare's cheapest non-refused approach, to the paisa, through the API | one evidence row; then close #633 with `Fixes #633` in the docs commit, or a comment naming what is left | 15 min, 20 calls |
| S3 | #628 final check (fix merged 894babd4): re-seed ADJ-13 on ofo_dev; adjustment history shows entry (4 legs incl. the call spread) + 1 adjustment; Compare reads "1 used" | API lines recorded; close #628 or comment what is left | 15 min, 20 calls |
| S4 | File a `deferred` issue (`gh_issue.py app ... --stage`, never while a prepush runs): the `spec_basis_gate` hook resolves ids only from the main checkout's spec, so every owner question citing a `feature/adjustments`-only id (ADR-217, REQ-170, ADR-236) is refused (seen 2026-11-02 20:3x) | issue number in the handover | 5 min |

## Rules
- 2 fix rounds per class, then park (`parked` issue with evidence); a second red of the same class gets an independent
  reviewer first (different model, fresh context).
- Memory: under 3.0 GB free, no builder dispatch; one DB test file at a time on a throwaway DB; the VPS DB host also
  serves another app's production, so targeted test files only.
- Merge a builder by its reported sha, never by branch name.
- Wording changes also run `tests/strategy/test_templates.py` and `scripts/ruff_ratchet.py`.
- Owner questions only for business calls; technical calls are decided and recorded.
- Never click inside a live order panel; paper only.

## Progress (the run updates this table; a DONE row is not redone)
| Step | State | Evidence |
|---|---|---|
| 0 | DONE 21:00 | 7018098e: Kite 1-min candles WERE available (F-33); T-07 = 100 x (spread - debit)/(200 - debit), every live value back-solves to a 0.05 tick; fixture tests/fixtures/alert_discipline/gclive3_2026-11-02_t07.json; expected 1/1/1 per preset for 66 and 67 (live 30 / 23) |
| 1 | DONE 21:10 | merge 2c27ee7c (builder 17ab5350): backend/ofo/adjustment/alert_gate.py; tests/adjustment/test_alert_gate.py 31 passed (re-run by orchestrator), replay 1/1/1, red first (ImportError); note: replay feeds a close at its end time, so record times are one minute late in that test (counts unaffected) |
| 2 | DONE 21:04 | e4f0ccb1: ADR-237 (band base, candle close, record timing, lapse at the band, storage migration, one writer, cap/quiet); REQ-112/165/170, ADR-235 text; owner info item docs/process/owner-questions-2026-11-02.md |
| S2 | DONE | #633 closed: T-19 A-29 Rs 85.04 = Compare cheapest A-29 85.04 (strategy 81, ADJ-50) |
| S3 | DONE | #628 closed: strategy 80 history entry 4 legs + 1 adjustment; Compare A-36 "1 of 2" |
| S4 | DONE | #637 filed (deferred, S6.7), 0712a94e |
| 3 | PARTIAL | items 1-3 merged 73854700 (builder 1eb28da3): registry keys per style incl. speeds.background_check_seconds.<style> (step 6 settings half), alert_presets.preset_for/style_for, user cap ceiling; tests_app/test_alert_preferences.py 10 passed on a throwaway DB (db_run_fresh.py; shared ofo_test is at 0030), domain 173 passed; items 4-7 merged 9bf0f0c1 (builder 99d9e7a9): migration 0035 strategy_alert_style + store + GET/PUT alert-style, plan-sheet picker, Preferences tables per style, 13 texts pinned pending owner read; re-run on merged head: domain 557 passed, vitest 28 passed; Tier A review running; Chrome check after review + ofo_dev migration |
| 4 | PARKED (#636) | build/gcalert1-636r4 5bf1db31 NOT merged: 0 DB calls per check proven, but Opus check FIX FIRST (one bad replaced settings row stops every check after a restart; stale writes for exited strategies; writer can die silently). Findings + next round on #636; steps 5-6 wire on the old path |
| S1 | DONE (review owed at close) | merge of 6ed5eb6c + fd60a14b (openapi, reply inventory): unreadable playbook -> limits_reason, drawer liquidity_flags; approaches route 75 passed, 218 neighbours, domain 544, vitest 29, drift 25 (fresh DB) |
| 3 review | DONE | pin fix merged 12035bf6 (builder bde3897a, round 2/2): test_strategy_alert_style 35 passed, test_adjustment_plan 7 passed (fresh DB) |
| 3 screens | PARTIAL | ofo_dev migrated 0034 -> 0036 (owner role, scratch wrapper). Owner's Chrome desktop 1366: Preferences tab shows the 3 style tables with the REQ-170 defaults; live POST daily_cap 8 -> 422 "can be at most 6, the limit your administrator set" (AC-6); pin on 81: Automatic (now Weekly) -> PUT monthly 200 (in force monthly) -> reset 200 (weekly). NOT seen: 390 px (window would not resize, innerWidth stayed 1536) and the plan-sheet picker (screenshots timed out twice); flaws seen: style tables show no units, lowercase labels |
| 5 | DONE (review running), 3 tests PARKED #638 | 5a merged 79196507 (readings for every rule, Lapsed at band, restore, migration 0036); 5b r1 b6d6fb1d + r2a 3ac7b661 (worker drives Opened/Held/Lapsed through the gate; fresh spot stamped now: quiet index was read stale after 3 s; group key letters+digits: inbox 500 fixed) + r2b 05bd6e78 (screen check writes no record, 503 on store failure; AC-5 risk exits import-walk) + completion 44f0d4c9 (catalogue ids in the gate, gate_rows.py split, worker tests: cap, quiet time, dismiss x2, close pass). Fresh-DB on merged heads: worker 5 (pre-completion), cycle 59, wire_want 7, storage 27, adjustment_check 10, opportunities 14, group key 1, speeds 10, alert style 35, openapi 1, reply inventory 24; domain 1227. PARKED #638: per-style interval gaps {30,60} for weekly, plan change, day rollover (xfail strict). Still owed: dev ofo_dev runs live in GC-LIVE4 |
| 6 | DONE | settings in step 3 (speeds.background_check_seconds.<style> 10/30/120), worker use in 5b r1; old single key removed; interval test parked #638 |
| 7 | MOVED to GC-LIVE4 (owner 2026-11-03 00:39) | docs/process/goal-contract-GC-LIVE4-2026-11-03-DRAFT.md |
| 8 | not started | |

## Amendment 2026-11-03 00:39 IST (owner, chat)
Owner: "finish everything as soon as possible, obviously test it. But for market hour testing, create a separate contract, separate goal contract, and we will run it during that market hours. Maybe we will combine other live market hours testing along with this one ... At least the building part should be completed."
- Step 7 (LIVE) MOVES to its own goal contract, `docs/process/goal-contract-GC-LIVE4-2026-11-03-DRAFT.md`, run in market hours with any other live checks ready by then. GC-ALERT1 no longer waits for a market day.
- Step 8: push `feature/adjustments` as soon as the full gate is TOTAL PASS (no longer "after market hours"); nothing on main.
- Definition of Done line 2: "live counts recorded, or step 7 PARKED" is replaced by "step 7 handed to GC-LIVE4 (draft written)".

## Definition of Done
- [ ] Step 0 data + hand-derived counts, then the core proof (step 1), before any other code.
- [ ] Spec reconciled (step 2); REQ-170 AC-1..AC-7, ADR-236 and ADR-235 built with tests; #636 round 4 built or
      PARKED with its reason; live counts recorded, or step 7 PARKED if no market day falls inside the run.
- [ ] S1 done or parked; S2 / S3 closed or commented; S4 issue filed.
- [ ] Full gate TOTAL PASS on the final head; feature/adjustments pushed; handover written; nothing on main.
