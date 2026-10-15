# Verifier brief: W-078 executable price, product, circuit band (Tier A)

Core: from the real 15:10 depth of NIFTY26O1923550CE, BUY 1 lot gives limit 4.00 and slippage Rs 3.25 vs LTP 3.95;
BUY 2 lots gives 4.05 and Rs 523.25 vs Rs 513.50; a BUY limit 3.975 is sent as 3.95 (SELL 4.00). Exits carry their
position's product, and missing products block; the circuit band blocks entries/adjustments with a missing or
breached band, and blocks exits only on a breached known band (missing band = confirm warning).
Proof: re-run and attack yourself; the builder's report and the reviews are claims. This is the item's last gate: a
FAIL parks it.

Model: opus (Tier A verifier).
Budget: 30 min wall-clock, 30 tool calls. HARD: at call 27 stop and return what you have.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), then the JSON block below.

## Where
- Your own read-only copy: `git -C D:/Abhay/Ventures/OptionsForOptions2 worktree add <scratchpad>/v078 origin/build/W-078-executable-price`
  (detached); remove it at the end from the main checkout (`git worktree remove` + `git worktree prune`).
- Brief + checklist: `docs/process/brief-W-078.md`; card `work/W-078.md`; ADR-080 (decision + real cases); REQ-059.
- Orchestrator decision (round 3, Spec basis REQ-059 exit carve-out "unhealthy data is shown as a warning the user
  confirms, not a block" and Q239 "Each blocks only an order Zerodha would reject"): exit + missing band = warning;
  exit + breached known band = block; entries/adjustments: missing or breached band = block; adjustments compare the
  order's own limit price (`ExecutionContext.order_prices`), no price = block "price not known yet".
- AC: REQ-059 AC-3. Fingerprint (main checkout): `python tools/ac_fp.py REQ-059 AC-3 --yaml` -> currently `a6ed85e0d32b`.

## Spec basis
- ADR-080: "BUY rounds down, SELL rounds up - so the price sent is never worse than the price the
  user accepted"
- ADR-080: "a price outside the day''s circuit band blocks that leg with the reason, never a silent clamp"
- REQ-059 AC-4: "Validation never silently changes the user's strategy."

## Check (how could it fail?)
1. In `v078`, separately: `python -m pytest -q -p no:cacheprovider tests/engine`, `tests/execution`, `tests/strategy`,
   `tests/orders`, `tests/errors`, and `tests/test_door_names_private.py tests/test_fixture_symbols.py`.
2. Recompute ADR-080's real cases from `docs/research/kite-proof-2026-10-07/rest-2026-10-15-order/quote_CE.json` and
   `quote_PE.json` by hand and compare with the code's output (write a scratch probe outside the repo).
3. Attacks: an exit whose position is MIS -> the order sent carries MIS; products missing -> blocked; an entry with a
   missing band -> blocked; an exit with a missing band -> warning + confirmation text naming the band; an adjustment
   with no order price -> blocked; an off-tick depth level -> not fillable; a float anywhere -> refused.
4. Does any existing check get looser (compare `passed` sets / gate tests vs origin/main)?
Never write in the main checkout; never write `evidence/`.

## Return
Evidence table, then one JSON block:
```json
[{"ac": "AC-3", "requirement": "REQ-059", "ac_fp": "<from ac_fp.py>", "result": "pass|fail",
  "commands": "...", "observed": "...", "attack": "..."}]
```
Plus defects (file:line, severity).
