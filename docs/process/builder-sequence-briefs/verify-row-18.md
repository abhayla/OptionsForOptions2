# Verifier brief: row 18 (W-146, REQ-035 strategy table) - full AC list on the screen users reach (Tier A checker)

Common brief: docs/process/builder-brief.md (checker part). Fresh context, adversarial, read-only: edit no file,
commit nothing; copy files to your scratch folder for every mutation. No database over the tunnel.
Why Opus: `backend/ofo/table/model.py` is in the safety set (SAFETY_SET in scripts/orchestrator/measure_process.py).
Starting state "verified" earlier (W-064 evidence), but REQ-035 was set back to Approved at row 17 because AC-5's text
changed (ADR-168 (4)); contract step 3: the verifier runs on the FULL AC list and its failing ACs become the build list.

Spec basis: REQ-035 AC-1 "There is exactly one table (not two) per strategy."; REQ-035 AC-2 "then the market-level
scenario columns, then Lower Breakeven, Upper Breakeven, Status."; REQ-035 AC-5 "The strategy table shows each leg's Bid
and Ask in its Details view, with no per-user switch"; REQ-035 AC-6 "vendor Greeks are kept only as
reference/comparison."; REQ-035 AC-8 "offers only listed, not-expired contracts of the chosen underlying".
Copy from: none - verification only.
Reference: screens 013, 014, 015, 017, 212 - copy the table columns with no level dependence; open RD-124 (SPEC CHANGE, waiting for the owner, Q282 - does not block), RD-125 (expected delivered by row 17: confirm)

Chunk head to check: the head of `build/seq-chunk-2` in `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs` (say the
sha you checked). Frontend tests run in `D:\Abhay\Ventures\OptionsForOptions2-row17b2\frontend` (has node_modules;
confirm its HEAD's `frontend/` tree equals the chunk head's, or say it does not).

For EVERY AC say which screen or route shows it (`/strategy/builder` StrategyBuilderPage + StrategyTable.vue; the
outcome route `POST /strategies/outcome`; the live push) and whether you exercised it THERE.

## Per AC (one evidence block each: pass / fail / partial / live check pending)
- AC-1 one table per strategy on the builder screen (and the saved/live strategy views if they show a table).
- AC-2 the exact column order, from the route's response AND as rendered (vitest mount of StrategyTable with a real
  fixture); scenario columns between Vega and Lower Breakeven.
- AC-3 sticky left columns and the highlighted current-market-level column: as rendered (class/style assertions in
  vitest); say plainly if only a browser can prove stickiness (then `live check pending` is wrong - it is a replay/e2e
  check: name the e2e spec that covers it, or fail).
- AC-4 the six live-updating columns update from the live push (frontend strategy-live tests + `tests_app/test_strategy_live_push.py`
  DB-free parts); recorded replay (`OUTCOME_REPLAY=1`) is the proof shape.
- AC-5 Bid and Ask per leg in the Details view for every user, read from `leg_quotes`; absent when not live.
- AC-6 IV and Greeks from the platform engine (trace the numbers to `backend/ofo/engine`); any vendor Greek only as reference.
- AC-7 locked order for everyone; heading pair "NIFTY at expiry | You make/lose" (and SENSEX); % return, breakevens,
  Greeks, IV all shown.
- AC-8 the builder's picker offers only listed, not-expired contracts of the chosen underlying (catalogue routes +
  LegPicker); an expired or unlisted contract cannot be added.
Mutation (Tier A): on scratch copies - swap two columns in the locked order; drop the highlight of the current level;
show an expired contract in the picker list - each must be killed by a test; quote which. Run
`python -m pytest -q -p no:cacheprovider tests/table tests/outcome` and the frontend files strategy-table, strategy-live,
leg-picker.

Attack list:
1. Column order on a SENSEX strategy equals AC-2 (not only NIFTY).
2. A not-live answer still renders one table with no stale value shown as live.
3. A leg with no quote shows no Bid/Ask row content invented.
4. An expired contract id posted directly to the outcome route is refused.
5. The highlighted column follows the current level when the spot moves across a scenario boundary.

Threat model: in scope - a second table, a wrong or level-dependent column order, a stale or invented price, Greeks
from outside the engine, an expired contract addable; out of scope - row 19's new picker tabs, RD-124's
three-view split (owner's batch).
Findings checked: verified-on-a-module-the-product-does-not-call, brief-rule-from-memory

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 20 min wall-clock, 40 tool calls
Report: evidence-table - per AC: verdict, screen/route, exercised there yes/no, command, output line; then numbered
findings CRITICAL / MAJOR / MINOR with file:line. Under 500 words.
