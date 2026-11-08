# Goal contract GC-ADJ3 (DRAFT, not approved): cost and honesty for adjustments (2026-11-01)

**Status: DRAFT for owner approval. Do not run.** Written 2026-10-31 late evening after the GC-ADJ3 gap check
(findings F-77, F-78) and the owner's answer on T-19 (ADR-221). Questions Q-ADJ3-2..5 in
`docs/process/owner-questions-2026-10-31.md` must be answered first; items marked (Q-n) follow that answer.

Core: every adjustment money figure a user sees, and every figure a trigger acts on, comes from ONE engine function,
so an alert and the Compare table can never disagree (ADR-008, ADR-221).
Proof: step 1 - scenario ADJ-02 and ADJ-13 on the dev server: the T-19 check names the cheapest approach of the stage,
and its cost equals, to the paisa, the "This adjustment" cost the Compare shows for that approach; a scenario where
premium left is below that cost fires T-19, one above it does not (both added through the generator).

## Owner decisions behind this contract

- **Owner rule (2026-10-30): every change stays on `feature/adjustments`. Never open a PR to main, never merge or push
  to main. Only the owner's explicit approval allows that.** The approval given 2026-10-31 was withdrawn the same day
  (PR #622 closed unmerged); it does not carry over.
- ADR-221 (owner, 2026-10-31): T-19 uses the cost of the cheapest approach the playbook offers for the current stage,
  priced as the Compare's "This adjustment" cost; the flag names it.
- ADR-008 (one engine owns money), ADR-003 (decision support), ADR-216 (iron condor numbers), ADR-217 (dismissed stays
  dismissed), REQ-155..163, REQ-112.
- Test data (owner, 2026-10-30): proofs run on the scenario library; new cases through `tests/adjust_scenarios_gen.py`.

## Steps

| Step | What | Done when |
|---|---|---|
| 1 (core) | F-77: one engine function for "this adjustment's cost" (charges + half spread, today in `compare.py:220-231`); the checker prices the stage's approaches and T-19 uses the cheapest (ADR-221); `adjust_money.adjustment_cost` and `COST_PER_LEG` retired; the flag line names the approach and cost | Proof above; a test holds the T-19 cost equal to the Compare cell for every scenario that has approaches; finding class `one-money-figure-two-formulas` -> guarded |
| 2 (Q-ADJ3-2) | F-78: the three playbook limits do what the owner chose (recommended: flag strikes below the OI / above the spread limit in the drawer and Compare, refuse a roll above the debit limit, with reasons) | Scenario with a thin strike flags it; a roll over the limit is refused with the catalogue reason; class `setting-saved-but-never-applied` -> guarded by a test that every guard key has a reader |
| 3 (Q-ADJ3-4) | F-04 rest of the cost line (recommended: rows "cost as % of premium left" and "change in max profit", charge breakdown as a detail under the cost row) | Values equal the generator's engine-free figures on ADJ-02 / ADJ-13; wording pinned and screened (ADR-003) |
| 4 (Q-ADJ3-3) | Live Strategies card alert (recommended: "N adjustment opportunities" mark linking to the inbox row) | Owner's Chrome, scenario ADJ-02: the card shows the mark; dismissing in the inbox clears it |
| 5 (Q-ADJ3-5) | Both stop values with no rule (recommended: treated and shown as "whichever comes first") | Plan sheet and summary show both; trigger behaviour unchanged |
| 5b (ADR-222) | Settings work is its own track, built now on feature/adjustments in the order REQ-167 (admin Settings, app-wide) -> REQ-168 (per-user adjustment Preferences tab) -> REQ-169 (admin edits system playbooks); this contract only uses it: step 1 deletes COST_PER_LEG (ADR-222 (8)) | Step 1 proof shows no flat per-leg cost anywhere |
| 6 | Leftovers: "Adjustments used" on the Compare fed from the GC-ADJ2 history count (today "-", `adjustment_readers.py:109-112`); phone width 390 px checked in Chrome for Compare, editor, inbox | Compare shows the count on ADJ-13; screenshot proof at 390 px |
| 7 | Close: `prepush.py --full` TOTAL PASS on the run head; merged `--no-ff` into LOCAL `feature/adjustments`; handover; memory | Pass record for the head sha; no push to main, no PR |

## Out of scope (later contracts, from the GC-ADJ1 handover plan)

GC-ADJ4 more strategy types (needs the owner's approval of the other 11 playbooks' numbers), GC-ADJ5 remaining
triggers (T-04, T-05, T-08, T-12, T-15, T-17, T-20 are "not checked in this version"; T-13 needs the day-open price;
T-14 formula), GC-ADJ6 what-if and paper adjust, GC-ADJ7 time-of-day help, GC-ADJ8 deeper analysis.

## Known facts the run must not re-discover

- `low_oi_blocked` has no live source (only scenario mode sets it, F-78); step 2 must say "OI state not known" live
  rather than claim a strike is fine.
- Wording changes run `tests/strategy/test_templates.py` (REQ-028 AC-5: no strategy-shape name in backend code; names
  with shape words load from `backend/ofo/adjustment/approach_names_with_shape_words.json`) and `scripts/ruff_ratchet.py`.
- prepush --full needs about 6 GB free memory.
