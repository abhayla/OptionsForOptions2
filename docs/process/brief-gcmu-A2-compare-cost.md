# Brief: GC-MU A2 - ADR-230 (3): Compare rows "Cost as % of premium left" and "Change in max profit", charge breakdown on tap

Core: two new Compare figures computed by the one engine from the existing cost and max-profit figures, equal to the generator's engine-free figures to the paisa.
Proof: step 1 of this brief - on scenarios ADJ-02 and ADJ-13 the two figures (and the charge components) equal the generator's independently computed values to the paisa.
Budget: 45 min wall-clock, 60 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Round: 1/2
Findings checked: F-73..F-76 (spec/findings.md), knowledge/findings grep for compare, premium_left, charges
Spec quote: ADR-230 "Two new rows, "Cost as % of premium left" and "Change in max profit""
Sensibull: bundle-findings.md section 2.5 (charges panel, chunk-DrUqoNrp.js): Total Charges, Breakdown of charges, Brokerage Charges, STT, Exchange transaction charges, GST, Stamp Duty, SEBI Turnover fee, plus an approximate-charges disclaimer - copy the component list and order under the cost figure (no screenshot of it is in the study).
Reference: none - searched charges breakdown, max profit change (no adjust-compare screen in the study); open records: RD-096 (shape detection, not touched)
Copy from: none - no legacy-reuse map row for the adjust Compare (built new in GC-ADJ1).
Tier: B.

## Where
Worktree `D:\Abhay\Ventures\OptionsForOptions2-gcmu-cmp`, branch `build/gcmu-cmp` (from `build/gcmu` AFTER A1 merged). Commit there only. Never push. `frontend/node_modules` is a junction: never delete it, never run `npm ci`/`npm install`.

## The decision (spec/decisions/ADR-230.md decision (3) and consequences)
Two new rows under the existing cost row; the breakdown (brokerage, STT, exchange, GST, stamp) opens on tap under the existing cost row. Figures from the one engine (ADR-008). "% of premium left" uses the same cost T-19 uses (ADR-221) - that cost function is being built by another session: use today's `compare.py` cost (`_ColumnCells.cost`, ~line 220) through a stand-in in your NEW module marked `# MERGE-SWAP(GC-SET): ADR-221 one cost function` (one line naming what replaces it).

## Do, in order
1. CORE: new module `backend/ofo/adjustment/compare_cost_rows.py`: cost-as-%-of-premium-left (cost / premium left x 100, Decimal, rounding as the existing percent cells do; premium left 0 or unknown -> dash with a catalogue reason, never a division error) and change-in-max-profit (After max profit - Before max profit, after charges; unlimited or unknown on either side -> dash with reason). Charge breakdown from `ofo.charges.calculator` per component (SEBI is a separate component in the calculator - show it, or fold it as the calculator's own grouping says; state which). Generator (`tests/adjust_scenarios_gen.py`): add engine-free expected values for ADJ-02 and ADJ-13 only (new keys; regenerate fixtures with the generator only). Test: equal to the paisa.
2. Thin call sites in `backend/ofo/adjustment/compare.py`: two ids in `ROWS` (MONEY_NOW group, right after `cost`; leader direction LOW for % and HIGH for change) and two cell methods that delegate to the new module; labels in `backend/ofo/errors/explanations.py` `ADJUSTMENT_CRITERION_LABEL_TEXT` (the import-time check requires both), pins updated by the repo's template-pin process; ADR-003 wording. Breakdown served with the cost cell (a small field), not a new route.
3. Frontend `frontend/src/components/strategy/AdjustCompare.vue`: the two rows render; tapping the cost row opens the breakdown under it (keyboard reachable, a button). vitest for the component.
4. Run in full each changed test file; `tests/strategy/test_templates.py`; `python scripts/ruff_ratchet.py`; guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan`; `npx vitest run <changed specs>`. Logs to a file, tail only.

## Standing items
- One test per answer state: both known; premium left zero; premium left unknown; cost unknown (charges unknown / no bid-ask); max profit unlimited; no trades.
- A shown-value change greps every test tree (e2e included) for the row list / row count it changes (row-order tests will move).
- Money exact Decimal (ADR-008); no float.
- No new duplicated literal; ruff/mypy baselines must not rise; regenerated fixtures only via the generator.
- REPORT every shared file changed with line ranges: `backend/ofo/adjustment/compare.py`, `backend/ofo/errors/templates.py`, `backend/ofo/errors/explanations.py`, `tests/errors/template_pins.json`, `tests/adjust_scenarios_gen.py`, `tests/fixtures/adjust_scenarios/`, `tests/strategy/test_templates.py`, `frontend/src/pages/AdjustmentsPage.vue`.
- Commit after each step passes. End the report with the final commit sha on build/gcmu-cmp.
