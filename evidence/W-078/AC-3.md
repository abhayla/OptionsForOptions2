---
work_item: W-078
ac: AC-3
requirement: REQ-059
ac_fp: "a6ed85e0d32b"
result: pass
verified_by: "verifier (opus, fresh context)"
builder: "builder (sonnet, worktree agent)"
date: '2026-10-16'
commands: "python tools/ac_fp.py REQ-059 AC-3 --yaml; python -m pytest -q -p no:cacheprovider tests/engine; tests/execution; tests/strategy; tests/orders; tests/errors; tests/test_door_names_private.py tests/test_fixture_symbols.py; python -m pytest -q -p no:cacheprovider <scratchpad>/probe/test_probe078.py; git diff origin/main...HEAD -- tests/execution/test_safety_checks.py tests/execution/test_strategy_guard.py tests/execution/partial_inputs.py tests/strategy/test_modification.py"
---

AC: AC-3
result: pass
commands: as in the frontmatter (verified at 13195ec)
observed: engine 676, execution 493, strategy 437, orders 64, errors 678, door/fixture 237 passed. Independent probe on the real quote_CE/PE.json: BUY 65 limit 4 walked 260 planned 256.75 slippage 3.25; BUY 130 limit 4.05 walked 523.25 planned 513.50 slippage 9.75; SELL 65 limit 3.95 slippage 0; PE BUY 65 limit 4.6 slippage 3.25; 41405 units fill at 4.2, 41406 not fillable (depth_too_thin, total None); 3.975 BUY 3.95 / SELL 4.00. Probe 10/11 passed; the 1 failure is defect D1 (minor: price_bands / order_prices are live views of the caller's dict, not copies - deferred #263).
attack: exit of an MIS position carries MIS, forcing NRML by monkeypatch is refused; products missing (None/None, partial map either side) block; entry missing one band blocks that leg; exit missing band = confirmation naming the band, listed not checked and not passed; exit missing + breached = block; adjustment compares order_prices not the 0.00 placeholder (40 vs 32.6 blocks 4 legs), no band blocks; off-tick depth level not fillable; floats refused at 8 entry points; gate tests vs main only gained cases. Scope note: round_to_tick / executable_limit are not yet called by a send path (the step that sets an order's price from the executable limit is later wiring).

Recorded by the orchestrator from the verifier's returned block.
