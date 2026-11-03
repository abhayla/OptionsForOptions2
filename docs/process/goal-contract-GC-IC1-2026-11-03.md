# Goal contract GC-IC1: iron condor adjustments complete (2026-11-03)

**Status: APPROVED by the owner 2026-11-03 08:36 IST** (chat: "Give me the prompt goal contract for this work").
Written 2026-11-03 08:12 IST after the iron condor audit. Owner
decision the same morning (question tool, Business call): **"Full playbook"**. The iron condor counts as done only
when every action and day rule the approved iron condor playbook shows a user actually works, the open background
defects are fixed, wording is applied, the phone width is checked, it has run live, and a verifier has signed off.
No other strategy type starts before this closes.

Core: a day rule that is switched on in the playbook (today none acts, except "tighten") raises a suggestion at its
time, offering its own action, through the same alert gate (REQ-170) as every trigger.
Proof (step 1): scenario mode with a pinned clock on an expiry-day iron condor (new generator case): at 14:29 no
record; at 14:30 one record "close any spread whose short is within 0.3%" offering A-28 for the tested spread and
A-27 for the far short below Rs 2; a second scenario with the short 0.4% away gives no record. Records counted from the DB.

## Owner decisions behind this contract

- **Owner rule (2026-10-30): every change stays on `feature/adjustments`. No PR to main, no merge or push to main**
  without the owner's new explicit approval.
- Owner 2026-11-03 ~08:10: scope "Full playbook" (this contract).
- The approved iron condor system playbook (ADR-216), ADR-221 (T-19 cheapest cost), ADR-230 (limits, card mark, cost
  rows, "whichever comes first"), REQ-155..REQ-163, REQ-167..REQ-170, ADR-235..237. ADR-008 (one engine owns money),
  ADR-003 (decision-support wording).
- Test data: proofs on the scenario library; new cases through `tests/adjust_scenarios_gen.py` (owner 2026-10-30).

## Audit facts the run must not re-discover (measured 2026-11-03 on origin/feature/adjustments 5e5eb400)

- `backend/ofo/adjustment/approaches.py:61` `KINDS` builds 7 approaches (A-36, A-01, A-05, A-29, A-28, A-11, A-31).
  The iron condor playbook's `approaches.applicable` lists 18; the 11 with no builder are never shown:
  A-02, A-04, A-06, A-23, A-24, A-25, A-26, A-27, A-35, A-37, A-38.
- Day rules: only `_tighten` (`backend/ofo_app/adjustment_check.py:137`) acts. Iron condor rules switched on and inert:
  `beforeWeekend` 15:00 action 0, `beforeHoliday` 15:00 action 0, `expiry` 14:30 action 5 with
  `close_if_short_within_pct` 0.3.
- Situations S-01..S-12 are display text only, except S-11 (`backend/ofo/adjustment/offered.py`).
- Every trigger switched on in the iron condor playbook is checked (`playbook_eval.py:459`), but T-13 and T-16 do not
  run in the background worker (#627).
- No verifier evidence file exists for REQ-046, REQ-112, REQ-155..REQ-170 (REQ-045 has 1).
- 390 px never seen in Chrome for Compare, editor, inbox, Preferences, plan sheet.

## Steps

| Step | What | Done when | Review |
|---|---|---|---|
| 0 | Overlap check: `git log` since 5e5eb400; GC-LIVE4 result if it ran; read #627, #636, #638, #639 | Nothing in this list is already built | none |
| 1 (core) | Day-rule evaluator: switched-on day rules produce records through the REQ-170 gate, with the rule's action; expiry-day rule (0.3% at 14:30) first, then before-weekend / before-holiday 15:00 carry check (S-06 content: overnight margin and loss at +/-2% gap, engine figures). Holidays from the existing exchange calendar source, or "holiday list not known" (never assume a weekday) | Core proof above; carry-check record on a Friday 15:00 scenario shows engine figures equal to the generator's engine-free values | Tier A |
| 2 | Exit and reduce actions: A-27 (buy back shorts under the playbook's Rs limit), A-24 (take profit, whole), A-25 (close X% of lots; refuse when it is not whole lots), A-26 (close the untested side when it has decayed per the playbook), A-35 (time exit at the set time). Each priced by the engine as a full "After", refusals per REQ-155 AC-8 | Each on ADJ-02 / ADJ-13 equals the generator's engine-free figures to the paisa; Compare shows them; S-11 still keeps only exit and reduce at the limit | Tier A (money) |
| 3 | Roll actions: A-02 (roll the tested short away, to the playbook's target delta or points), A-04 (roll up/down and out to the next expiry), A-06 (shift one leg by +/-N strikes; keeps width unless asked) | Same proof as step 2; A-04 refuses when the next expiry has no chain rows, with the reason | Tier A (money) |
| 4 | Non-trade actions: A-23 delta-neutral helper ("to reach net delta +/-X: N lots of strike K or N futures", engine Greeks), A-37 alert only / watch a level (user level, re-check), A-38 pause monitoring until a time (the worker skips that strategy until then; stop-losses never paused, REQ-170 AC-5) | A-23 figures equal a hand engine check; A-38 pause proven on the worker with a pinned clock; a paper stop still fires inside the pause | Tier A (worker), Tier B (A-23, A-37) |
| 5 | Background parity: #627 T-13 day-open price and T-16 margin in the worker; #636 round 5 (merge base first, guard tests, record merge commit in #636; the round-4 FIX FIRST findings); #638 three xfail worker tests diagnosed and green; #639 three follow-ups | Worker answers T-13/T-16 like the screen on the same scenario; #636 latency measured; xfail markers removed; issues closed with `Fixes #N` only when whole | Tier A |
| 6 | Situations that change behaviour: decide per situation whether it is a rule (code) or guidance text (label it "guidance" in the editor so it is not read as a rule). Technical call per situation, recorded; any that changes what users see goes to the owner | Every situation either has a test proving its effect or is labelled guidance on screen | Tier B |
| 7 | Wording: apply the 11-02 decisions for #629 (`D:\Abhay\scratch\wording629\owner-decisions.md`) and every new text of steps 1-6 pinned and screened (ADR-003) | `tests/strategy/test_templates.py` + `ruff_ratchet` green; pins marked per the decisions | Tier C |
| 8 | 390 px in the owner's visible Chrome: Compare, drawer, editor, inbox, Preferences, plan sheet, history (desktop too) | Screenshots per screen; defects fixed or deferred with issue | none |
| 9 | Live day (market hours, owner's Kite login, paper only): fresh NIFTY iron condor; GC-LIVE4 section A if not run yet; every new action priced on the live chain; the day rules at their times if the day allows (else scenario proof stands, named in the handover); #624 liquidity flags live | Counts and lines in the run log; failures become issues | none |
| 10 | Verifier pass: one evidence block per AC for REQ-046, REQ-112, REQ-155..REQ-163, REQ-167..REQ-170 (the iron condor paths) | Evidence files written by the orchestrator from verifier output; any FAIL fixed (2 rounds, then park) | verifier |
| 11 | Close: `prepush.py --full` TOTAL PASS (started as a detached `Start-Process`, the reap kills session shells); push `feature/adjustments` as its own command; handover; memory | Pass marker for the head sha; nothing on main | none |

## Out of scope

Other strategy types and their playbooks (the 11 draft playbooks wait for this contract; their owner answers are in
`D:\Abhay\scratch\pbreview\owner-answers.md`); triggers switched off in the iron condor playbook (T-04, T-05, T-06b,
T-08, T-11b/c, T-12, T-14t/v, T-15, T-20, T-20b) stay "not checked in this version"; GC-SET2 (#632); the PR to main.

## Known facts

- prepush --full needs about 6 GB free; run it detached.
- DB tests use `db_run_fresh.py` (shared ofo_test is at 0030).
- The spec-basis question gate cannot see ids that exist only on this branch (#637): cite REQ ids on main in owner questions.
