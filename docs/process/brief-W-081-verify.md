# Verifier brief: W-081 margin gate before the basket (Tier A)

Core: against the real 2026-10-15 basket-margin reply for the 4-leg NIFTY iron condor (`final.total` 68498.85,
`initial.total` 296332.8), available Rs 68,498.85 builds the basket and Rs 68,498.84 blocks it, the message showing
available vs required and the three offers; any read failure blocks.
Proof: re-run and attack yourself; the builder's report and the reviews are claims.

Model: opus (Tier A verifier).
Budget: 25 min wall-clock, 26 tool calls. HARD: at call 23 stop and return what you have.
Report: evidence-table, then the JSON block below (one block per AC).

## Where
- Your own read-only copy: `git -C D:/Abhay/Ventures/OptionsForOptions2 worktree add --detach <scratchpad>/v081 origin/build/W-081-margin-gate`;
  remove it at the end from the main checkout.
- Brief: `docs/process/brief-W-081.md`; card `work/W-081.md` (decision by role: required = `final.total`); REQ-055; ADR-016;
  ADR-054; real reply `docs/research/kite-proof-2026-10-07/rest-2026-10-15/margins_basket.json`.
- Note: W-080 (basket) is parked (#271); W-081 merges standalone with its own urllib transport.
- ACs and fingerprints (main checkout): AC-1 `72546cbc045d`, AC-3 `c798814d614e`, AC-4 `fb96f4697778`.

## Spec basis
- REQ-055 AC-1: "fetch available funds/margin from Zerodha, obtain the required margin for
    the planned orders, and build the basket only if sufficient"
- REQ-055 AC-3: "The platform's own margin figure is shown as a planning estimate; Zerodha's figure is authoritative."
- REQ-055 AC-4: "If margin is insufficient: no basket is built; show available vs required, and offer quantity change, review,
    or an add-funds path."

## Check (how could it fail?)
1. In `v081`, separately: `python -m pytest -q -p no:cacheprovider tests/execution`, `tests/errors`,
   `tests/test_door_names_private.py tests/test_fixture_symbols.py`; `python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_kite_margin_client.py`.
2. Probe (outside the repo) with the real reply: equal allowed, one paisa short blocked; message amounts and offers; a
   forged verdict (replace, direct construction, copy+setattr) impossible through ordinary code; negative funds block
   with Zerodha's signed figure; BFO accepted (SENSEX marked unproven); every transport failure (403 with unreadable
   body, 429, 500, IncompleteRead, bad UTF-8, non-JSON, nested JSON 200,000 deep, missing `final`, non-numeric total)
   blocks with a typed reason.
3. AC-3: where the platform's own margin estimate is worded, it says estimate and Zerodha's figure decides; the builder
   reported an older wording at `templates.py` (`gate_margin_insufficient`) - judge whether AC-3 holds.
4. `equity.net` as available funds and `consider_positions=true` are unproven on real data - say so in the evidence.
Never write in the main checkout; never write `evidence/`.

## Return
Evidence table, then one JSON block: `[{"ac": "AC-1", "requirement": "REQ-055", "ac_fp": "...", "result": "pass|fail",
"commands": "...", "observed": "...", "attack": "..."}, {"ac": "AC-3", ...}, {"ac": "AC-4", ...}]`. Plus defects.
