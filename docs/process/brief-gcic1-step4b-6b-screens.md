# Brief: GC-IC1 steps 4b + 6b - REQ-155 / REQ-159 AC-5: the screen controls for pause, watch a level and the delta helper; the Guidance label on situations

Core: on the strategy's Compare page the user can (1) pause adjustment monitoring until a time and clear it (A-38, `/api/strategies/{id}/monitoring-pause`), (2) watch an index level above / below and clear it (A-37, `/api/strategies/{id}/level-watch/{direction}`), (3) read the delta-neutral helper figures (A-23, the `delta_neutral` block of the approaches reply); and in the playbook editor S-03, S-04 and S-05 carry a "Guidance" label (ADR-240 (1)) while the rule situations do not.
Proof: step 1 of this brief - frontend unit tests (vitest) drive each control against a mocked API: setting a pause sends PUT with the HHMM end and shows "paused until 10:30"; clearing sends DELETE; a 422 shows the server's reason text; a watch above 23,800 sends PUT `.../level-watch/above` and shows it; the delta block shows its figures and its "not known" reason when the server says so; the editor shows "Guidance" on exactly S-03, S-04, S-05 for the iron condor playbook.
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Round: 1/2
Findings checked: engine-input-chosen-per-caller
Spec quote: REQ-159 AC-5 "Situations S-01 to S-12 (catalogue Part 4) are part of the playbook"
Threat model: in scope - any figure computed in the browser (forbidden: ADR-008 / ADR-012, the browser shows server figures only); a text typed in the component instead of coming from the server's catalogue (every user-visible sentence comes from the API or the existing label tables); a control that hides a server refusal; a layout that overflows 390 px (step 8 re-checks; keep the drawer and controls in the existing responsive patterns); the Guidance list kept in the frontend (decided: the server says which situations are guidance, one source). Out of scope - new server behaviour beyond the one guidance field.
Sensibull: catalogue-raw.md line 55 (Greeks tab: per-leg delta and a Total) for the delta helper's figures layout; line 222 (conditional exit on an index level) for the watch control; no pause in the study.
Reference: none - searched pause control, level watch control, guidance label
Copy from: the existing Compare page and drawer components (`frontend/src/components/strategy/AdjustCompare.vue`, `AdjustDrawer.vue`, `frontend/src/lib/adjustCompare.js`, `adjustDrawer.js`) and the editor's situations list (`frontend/src/pages/AdjustmentsPage.vue:126`) - extend them, no new page.
Tier: B (screens; frontend tests + the step 8 re-check are the gate).
Size: M, about 8 files, backend + frontend (backend: one guidance field), 4 items
CI: the frontend job runs `npx vitest run` for the changed test files; the backend unit job runs `tests/adjustment` for the guidance field; vars: none

## Where
`git switch -c build/gcic1-s4b <sha given in the dispatch>` inside your agent worktree (feature/adjustments; never main, never push). Frontend: run `npm ci --prefer-offline` in `frontend/` of YOUR worktree if node_modules is missing (no junctions to other trees). NO DB tests.

## Do, in order
1. Backend (one small change): the playbook body reply (the route the editor reads) adds per situation `kind: "rule" | "guidance"` from ONE server constant naming S-03, S-04, S-05 (ADR-240 (1)); never a new key stored in the body (saved bodies must work). Unit test.
2. Frontend: the three controls on the Compare page (near the existing approach columns / drawer), each with its server texts; the editor's situation rows show the Guidance label from `kind`.
3. Vitest tests per the Proof; grep `frontend/tests/` and `frontend/e2e/` for any changed selector or text and update them.
4. Run `npx vitest run` on the changed and neighbouring test files (log to a file, tail), `npx eslint` on changed files, `python -m pytest -q tests/adjustment`, the guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan`, `python scripts/ruff_ratchet.py`.

Standing items:
- B4 (d) answer states for each control: set / none / cleared / server refusal (422 with reason) / network failure (named, the control stays usable); delta block: figures / not known with reason / absent (old server).
- No figure computed in the browser; no sentence typed in a component that the server's catalogue owns.
- Generated files (board pages, indexes) stay out of the branch.
- If `git commit` is refused by verifier_inflight_gate, retry at most 3 times, then report files + command. End with the final commit sha on build/gcic1-s4b.

Attack list:
1. A pause end typed as 10:30 sent as "10:30" (the server takes HHMM): test sends "1030".
2. A 422 swallowed: the reason shows.
3. The delta block computes lots in JS: grep; it shows server numbers only.
4. Guidance label from a frontend list: grep; it reads `kind`.
5. Mutants (scratch copy, at most 5): drop the DELETE on clear; show the label on every situation; hide the 422 reason; send 10:30 with a colon; compute delta in JS. Each turns a test red; report mutant -> test name.
