# Review brief: GC-IC1 Tier A, area B - the money path (approach builder, Compare pricing, held reads)

Reviewer: fresh context, read-only (no file writes in any repo; scratch only under your own scratchpad). Run the attacks FIRST, read after. Findings + failing inputs, no code.
Range: feature/adjustments 37824fb9..<head given in the dispatch>, these merges only: step 2 (A-24/25/26/27/35, ADR-238 incl. (6)), step 3 (A-02/A-04/A-06, ADR-239), ADR-241 (mid price), the screen-check fixes (far condor recognition, spot skew, read inside the hold, delta reach), the T-19 generator set.
Spec: REQ-155 AC-1 / AC-8, REQ-156, ADR-008, ADR-068 (1) as amended by ADR-241, ADR-172, ADR-221, ADR-238, ADR-239, ADR-241.
Budget: 20 min wall-clock, 40 tool calls.

Attacks (each: run it, then verdict with the failing input or "held"):
1. Money outside the engine: run tests/test_money_outside_engine.py; grep approaches.py / compare.py for arithmetic on prices.
2. A model price used as a trade price (ADR-020 Q185): trace every `Trade.price` to a quote (mid or LTP).
3. Mutants on a scratch checkout (max 5): A-25 floors instead of refusing; A-24 offered at a loss; A-02 moves the wing; ADR-241 health gate dropped (stale book uses the mid); the second pass without the delta reach. Each must turn an existing test red.
4. Live, read-only: POST http://127.0.0.1:8765/api/strategies/82/adjustment-approaches body {"view":"estimated_now"} (market closed after 15:30: expect the closed-market answers; say what each approach answers and whether that is right per spec).
5. The generator's independence: grep tests/adjust_scenarios_gen.py for imports of the builder / engine pricing beyond what it already used at 37824fb9.
Report: evidence-table (claim | command + result), findings ranked CRITICAL / MAJOR / MINOR with file:line and a failing input, "covers the class: yes / no" per finding. Under 400 words.
