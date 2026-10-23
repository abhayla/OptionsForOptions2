# Verifier brief: row 20 frontend part + backend delta (W-148, REQ-076 leg rows) - checker

Common brief: docs/process/builder-brief.md (checker part). Fresh context, adversarial, read-only: edit no file,
commit nothing; scratch copies for every mutation. No database over the tunnel.
Checker model: Sonnet - no changed file is in the safety set (builder-brief.md).

Spec basis: REQ-076 AC-3 "the browser computes no P&L, payoff, margin or Greek"; REQ-076 AC-7 "Tick every leg to
execute: the whole strategy is sent as one plan."; REQ-076 AC-8 "The leg list shows the name of the template the engine
matched for the current leg set"; REQ-077 AC-7 "keeps the ADR-085 message and Reprice button".
Reference: screens 025, 103, 111, 244 - copy only what each open record says; open RD-031, RD-091, RD-097, RD-139, RD-140, RD-141, RD-032, RD-113, RD-129, RD-130, RD-131, RD-132, RD-133, RD-134, RD-145, RD-146, RD-147, RD-148, RD-149 (RD-032/129-134 are row 19's and RD-113/145-149 row 21's: not checked here)

What was built: chunk head on `build/seq-chunk-2` in `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs` (row 20 commits
after the backend check: 463dca78 frontend, 58b77cd8 fix round 1, 47679238 finisher, docstring wrap). Frontend:
`LegList.vue` is the ONE leg list (steppers, 1-50 multiplier select, include tick, template name, Hedge marks, depth
icon per leg, Edit, Reprice, Remove), `legEdit.js`, the builder page wiring (a `read` leg-edit call on load and after
Done), Execute refused while a leg is unticked; LegPicker no longer renders a list on the builder (`showLegList`).
Backend delta since the backend check: `backend/ofo_app/routes/leg_edit.py` gained the `read` control (changes no leg)
and per-leg `contract_id` / `lot_size` in the reply (so a stepped leg can be saved). Frontend tests run in
`D:\Abhay\Ventures\OptionsForOptions2-row20\frontend` (node_modules; confirm its HEAD's frontend tree equals the chunk
head's with git diff).

For EVERY AC say which screen shows it (`/strategy/builder`) and whether you exercised it THERE (vitest page mount with
replies shaped exactly like `routes/leg_edit.py`'s models).

## Per AC (pass / fail / partial)
- AC-1 steppers on option legs only; a refused step shows the server's reason.
- AC-2 after a step, Save Draft posts the NEW contract id (never the old, never none); the route test asserts the reply's
  contract id equals the catalogue's id for the stepped strike.
- AC-3 every number is the reply's; no arithmetic in the browser (the money guard is green - confirm no allow-list change:
  `git diff 86264455 HEAD -- tests/test_money_outside_engine.py` empty).
- AC-4 the multiplier select 1-50 sends the choice; the server's refusal (if any) is shown.
- AC-5 quantity from lots x the server's lot size; the freeze-limit block reason shown on its leg.
- AC-6 an unticked leg greyed, 'Left out of the numbers', numbers from the reply; every leg unticked shows no zeros.
- AC-7 Execute refused with the exact text while any leg is unticked; the tick never in the saved body.
- AC-8 / AC-9 name and Hedge marks on load (read control) and after every edit, only from the server; the read control
  changes no leg (route test).
- AC-10 'No legs yet' with Add leg and Pick from Option Chain and no numbers; steppers work without live data.
- REQ-077 AC-7 / ADR-085: an unpriced leg on the one list shows the message and a working Reprice; Edit works as before.
- REQ-080 AC-7 remainder: every leg row opens the depth popup for its own contract.
Also judge: exactly one leg list on the builder screen; the builder's known gap (removing a leg while the picker is mid-edit
leaves a stale edit form) - severity with a real click path.

Attack list:
1. Step, then Save Draft: the saved body has the new contract id and lot size.
2. A refused draft link renders its refusal exactly as before and sends no read request.
3. Live push still matches the legs after a step.
4. Execute with one unticked leg sends no request and shows the exact reason.
5. Mutate on a scratch copy: name computed in the browser; tick added to the save body; Reprice hidden - each killed.

Threat model: in scope - a number or name computed in the browser, a stale contract saved after a step, two leg lists,
Execute allowed with an unticked leg, Reprice/Edit lost, the read control changing a leg; out of scope - typed price and
Reset Prices (row 21), late replies (row 23).
Findings checked: verified-on-a-module-the-product-does-not-call, brief-rule-from-memory

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 20 min wall-clock, 40 tool calls
Report: evidence-table - per AC: verdict, screen, exercised there yes/no, command, output line; numbered findings
CRITICAL / MAJOR / MINOR with file:line. Under 500 words.
