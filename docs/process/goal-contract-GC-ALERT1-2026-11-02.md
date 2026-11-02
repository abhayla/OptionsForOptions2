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
| 8 | Close: `coord.py take-heavy`; no tracked-file edit while prepush runs (run it in the background with a Monitor on its step lines); generated files via `regen.py` only; one `prepush.py --full` TOTAL PASS on the final head; push `feature/adjustments` to origin (backup, after market hours); handover `docs/process/session-handover-<date>-gcalert1.md`; memory | TOTAL PASS line + push line; nothing on main | 60 min |

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
| 0-8, S1-S4 | not started | - |

## Definition of Done
- [ ] Step 0 data + hand-derived counts, then the core proof (step 1), before any other code.
- [ ] Spec reconciled (step 2); REQ-170 AC-1..AC-7, ADR-236 and ADR-235 built with tests; #636 round 4 built or
      PARKED with its reason; live counts recorded, or step 7 PARKED if no market day falls inside the run.
- [ ] S1 done or parked; S2 / S3 closed or commented; S4 issue filed.
- [ ] Full gate TOTAL PASS on the final head; feature/adjustments pushed; handover written; nothing on main.
