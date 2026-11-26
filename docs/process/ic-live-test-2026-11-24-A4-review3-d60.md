## A4 review 3 (2026-11-24): D-60 round 2, commits 1a81d59e, e1b210d8 and gate move aa6ea9fb

Reviewer: fresh-context helper, read-only. Class: every way a leg is added or moved in the builder, and Add to Paper
with a kept duplicate (ADR-319). Verdict: REVISE (the door is sound; the class is not closed).

Findings:
1. MAJOR `frontend/src/lib/paperDrafts.js:63-71` (signedByContract), `:90-121` (paperOrdersFor): a paper strategy
   opened in the builder (Drafts Mode) merges a kept duplicate silently: both rows sum per contract_id into one `add`
   order (held 1 lot + Keep separate 1 lot = one order of 1 lot), so the server's duplicate check
   (`routes/paper.py:1021`), which sees only the posted batch, never fires. ADR-319 (3) "never merged silently" fails on
   this paper entry path. Add to Paper is hidden in Drafts Mode (`StrategyBuilderPage.vue:989`). Class: yes.
2. MAJOR `StrategyBuilderPage.vue:723-750` (editLeg, moveLeg) with `backend/ofo_app/routes/leg_edit.py`: the strike
   stepper is the known gap, and the same `/strategies/leg-edit` call also carries Shift, Width and Hedge
   (RELATIVE_CONTROLS `legEdit.js:50`; MOVES `leg_edit.py:118`). Each can land a leg on a held contract with the same
   action; no browser door call and no server duplicate check (`_check_landing` checks tradability only). Class: yes.
3. MINOR `StrategyBuilderPage.vue:130-153` (prepareApproach): adjustment apply sets the server's after-legs with no
   door; a duplicate in a plan-only draft is refused later by the server; in Drafts Mode it merges as finding 1.
   ADR-319 (1) does not list adjustment apply. Class: yes.
4. MINOR `StrategyBuilderPage.vue:100-118, 616`: a draft link, saved strategy or ready-made template replaces the list
   without asking; old duplicates show the LegList row warning (`LegList.vue:253`) and are refused at Add to Paper.
   Chain Add Selected cannot create a same-action duplicate. Class: no.
5. MINOR `LegList.vue:85`: the row warning is hand-copied text, not the served sentence (the server names the contract
   and numbers legs over posted non-exit orders). Class: no.
6. MINOR `legDoor.js:20-28`: incoming legs are not compared with each other; the picker does not produce that today.

Holds: through the door: picker and edit-form save (`LegPicker.vue:529`, strike and expiry change in the form), Done
(`resolveDuplicates`, :586), the Buy/Sell button (:652). One server entry for paper orders, POST
/paper/strategies/{id}/orders (`paper.py:1036`, check at 1056); every frontend caller uses it; the refusal carries the
gate's sentence. aa6ea9fb: behaviour unchanged.

Runs: `npx vitest run tests/leg-duplicate-d60.test.js` 14 passed; `pytest tests -k "closure or order_path or
duplicate_leg"` 15 passed; `pytest tests/execution/test_validation.py tests/errors/test_template_pins.py -k duplicate`
2 passed; probe of `paper_duplicate_leg`: same-side repeat refused, buy and sell not, futures repeat refused.

Covers the class: no (the leg-edit family and the Drafts Mode merge).
