# Brief: GC-MU step 1 T1 - the frontend money scan fails on arithmetic over price / P&L / quantity outside the named drawing exceptions

Core: `tests/test_money_outside_engine.py` turns red when a planted `a.pnl + b.pnl` sits in a non-exempt frontend file, and green when it is removed.
Proof: step 1 of this brief - plant the line in a scratch file under `frontend/src/lib/`, run the test, record red or green, delete the file.
Budget: 25 min wall-clock, 30 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Class: frontend arithmetic over money fields that escapes the ADR-008 scan - before: unmeasured (does the scan see `a.pnl + b.pnl`, `x.price * q`, `Number(r.ltp) - Number(r.close)`, `sum += leg.pnl`, `.reduce((s, l) => s + l.pnl, 0)`); after: each shape is a planted test that is red.
Round: 1/2
Spec quote: ADR-008 "One strategy/risk engine produces every number"
Threat model: in scope - a developer adding browser-side sums or differences over price, P&L, premium, margin, quantity or charges fields in .js/.vue under frontend/src, outside the files the test names as drawing exceptions; out of scope - deliberate obfuscation (computed property names), and the drawing exceptions themselves (PayoffChart.vue, PnLCell.vue, etc. as listed in the test).
Sensibull: n/a - code guard, no screen.
Reference: none - searched money arithmetic, frontend sums (no screen)
Copy from: none - the scan exists (tests/test_money_outside_engine.py); this brief only extends it if a planted shape passes.
Tier: B.

## Where
Worktree `D:\Abhay\Ventures\OptionsForOptions2-gcmu-t1`, branch `build/gcmu-t1` (from `build/gcmu`). Commit there only, never push. Open issue #598 lists two MINOR gaps of the same scan - read it and do not duplicate; if a shape below is one of them, say so.

## Do, in order
1. CORE: for each of the 5 shapes in Class, plant it alone in `frontend/src/lib/zz_planted.js`, run `python -m pytest tests/test_money_outside_engine.py -q`, record red/green, delete the file. Report the table.
2. For every shape that stayed green: extend the scan (smallest change in the test's own matcher), and add a permanent planted-fixture test (the shape as a string fed to the matcher, not a file in src) that is red. Shapes already red: add the same string-fed test so they stay red.
3. Run the test file in full, the guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan`, `python scripts/ruff_ratchet.py`. Logs to a file, tail only. A newly-red REAL file in frontend/src is a finding: list it with file:line, do not change product code.

## Standing items
- One test per shape; every changed test file run in full; a skipped test counts as not run.
- Known bypasses written in the test's docstring.
- If `git commit` is refused by verifier_inflight_gate, retry at most 3 times, then report the files and the commit command.
- End with the final commit sha on build/gcmu-t1.
