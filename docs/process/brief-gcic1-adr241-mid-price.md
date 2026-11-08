# Brief: GC-IC1 ADR-241 - REQ-155 AC-1 / REQ-156 AC-2: adjustment approach trades priced at the live bid-ask mid first

Core: `backend/ofo/adjustment/approaches.py` `planned_price` (and the generator's independent copy `hand_price`) price an approach trade at the bid-ask mid when the row's book is live (both sides present, above 0, ask at or above bid, quote health AVAILABLE), else at the LTP, else none - the engine's ADR-172 rule (`ofo.engine.model.iv_price`) reused, never a second copy of the rule.
Proof: step 1 of this brief - a failing test first: a row with LTP 117.75 (stale) and a live book bid 72.00 / ask 75.30 -> planned price 73.65 (today: 117.75); a row with no live book (health STALE) -> its LTP; no LTP and no live book -> None (refused naming the leg). Then every scenario's approach figures equal the regenerated generator figures to the paisa.
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Round: 1/2
Findings checked: engine-input-chosen-per-caller
Spec quote: REQ-155 AC-1 "the server builds the exact legs from the listed strikes, reusing the REQ-078 server strike moves, and prices them"
Threat model: in scope - a second mid rule beside `iv_price` (one rule: call it, or factor a shared `live_book_mid` both use); the health gate dropped (a stale book's mid used after hours: ADR-172 / ADR-197 say after hours every leg uses its closing LTP); a draft leg's planned entry in the builder changed (NOT in scope: ADR-241 covers adjustment approach trades only); a model price. Out of scope - draft-leg planned entry (ADR-068 (1) unchanged there), wording.
Sensibull: n/a - server-side price choice.
Reference: none - searched planned price, bid ask mid, stale last price
Copy from: `ofo.engine.model.iv_price` (ADR-172) - the rule to reuse.
Tier: A (money: every approach figure and T-19's cost change).
Size: M, about 6 files plus regenerated scenario files, 1 item
CI: the backend unit job runs `tests/adjustment`, `tests/test_adjust_scenarios.py`, `tests/engine`; vars: none (no DB)

## Decision
`spec/decisions/ADR-241.md` (owner 2026-11-03): approach trades (Compare trades, cost rows, T-19's cheapest cost) at the live mid first, else LTP, else none; ADR-172 rule with its health gate; draft-leg planned entry unchanged.

## Where
`git switch -c build/gcic1-adr241 <sha given in the dispatch>` inside your agent worktree (feature/adjustments; never main, never push). NO DB tests.

## Do, in order
1. The chain row the builder sees needs the book's health (or a precomputed live flag): `ChainRow` today has ltp / bid / ask but no health. Add what is needed in ONE place the reader fills (`adjustment_readers.chain_rows`), not a second health rule.
2. `planned_price` uses the shared rule; paise rounding as today (half-up to 0.01).
3. Generator: `hand_price` follows the same rule written independently (its rows' health: the scenario's own data state; a scenario with a stale book keeps the LTP). Regenerate the scenario files (`tests/adjust_scenarios_gen.py`), diff and explain any figure that moves.
4. Every test whose expected planned price changes: update with the regenerated figures (grep `tests/`, `tests_app/`, `frontend/tests/`, `frontend/e2e/` for hard-coded old prices of approach trades; list each).
5. Run `python -m pytest -q tests/adjustment tests/test_adjust_scenarios.py tests/engine tests/errors`, the touched pure tests_app files, the guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan`, ruff on changed files, `python scripts/ruff_ratchet.py`.

Standing items:
- B4 (d) answer states: live book / stale book / one side missing / ask below bid (crossed: LTP) / no LTP and no live book (None).
- Money exact Decimal (ADR-008); no float.
- ruff / mypy baselines must not rise; regenerated scenario files only (no other aggregates).
- If `git commit` is refused by verifier_inflight_gate, retry at most 3 times, then report files + command. End with the final commit sha on build/gcic1-adr241.

Attack list:
1. Stale book after hours uses the mid: must use LTP (health gate).
2. Crossed book (ask below bid) uses the mid: must use LTP.
3. Draft-leg planned entry changed: `ofo.outcome.planned_entry` tests unchanged and green.
4. Two mid rules: grep for the rule text; one function.
5. Mutants (scratch copy, at most 5): LTP first again; health gate dropped; crossed book allowed; mid without paise rounding; generator copy importing the builder. Each turns a test red; report mutant -> test name.
