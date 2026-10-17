# Builder brief: W-106 Holdings read on the Kite read door - ADR-097 (4)'s before/after check (Tier A: a new Kite door entry)

Core: `KiteReads.fetch_holdings()` sends `GET /portfolio/holdings` through the read door (allow-listed in
`ALLOWED_CALLS` first, REQ-073 AC-4) and returns, per row, exactly tradingsymbol, exchange, isin, quantity,
t1_quantity as exact values (quantities int; nothing else kept; prices and P&L dropped); a reply of any other shape
raises `KiteReadError` (fail closed). A pure comparison `holdings_unchanged(before, after)` says equal / which rows
differ on those five fields.
Proof: Kite's documented holdings reply shape (zerodha-expert skill + https://kite.trade/docs/connect/v3/portfolio/)
written as a fixture `tests/fixtures/kite_replies/holdings-documented.json` (say in the fixture README it is the
DOCUMENTED shape, not a recording - GC-3 records the real one), parsed by the door through the existing replay
transport used by `tests_app/test_kite_reads.py`.

Tier: A. Model: sonnet.
Budget: 40 min wall-clock, 45 tool calls. HARD limit: at call 42 commit, push, report.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under 250 words, `git status --short` empty,
each new guard with its killing test (mutation-run).
Copy from: none - extend `backend/ofo_app/kite_reads.py` (W-093's orders/trades/positions entries are the pattern).
Findings checked: broker-reply-shape-unproven-at-domain-boundary, money-parsed-through-float, guard-as-forbidden-list, normalise-before-validate, repo-wide-scan-outside-targeted-tests
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py

## Spec basis
- ADR-097: "/portfolio/holdings is read before and after and must be unchanged."
- REQ-073 AC-4: "No code path places an order through the order-placement API; a test fails if one is added."

## Build
1. Load the user-level `zerodha-expert` skill for the holdings reply fields. Add `("GET", "/portfolio/holdings")` to
   the read door's allowed calls (the same place W-093 added `/orders`, `/trades`, `/positions`; the module allow-list
   names `kite_reads` with this call).
2. `fetch_holdings()` -> tuple of a frozen dataclass {tradingsymbol, exchange, isin, quantity, t1_quantity}; JSON
   parsed with Decimal for numbers; a quantity that is not a whole number, a missing field, a non-list `data` ->
   `KiteReadError`. An empty list is a valid answer (no holdings) and is distinguished from a failed read.
3. `holdings_unchanged(before, after)` keyed by (exchange, tradingsymbol, isin): returns the rows whose five fields
   differ, added or missing.
4. Tests (`tests_app/test_kite_reads.py` or a new file - no DB needed): documented reply parsed exactly; each
   malformed shape refused (generated: every field removed in turn, every field given a wrong type); empty list;
   unchanged / changed-quantity / added row / removed row.

## Reviewer checklist (attack cases first)
- Attack: `"quantity": 10.5` -> refused; `"quantity": "10"` -> refused or parsed? (state which and why; fail closed).
- Attack: the door refuses `GET /portfolio/holdings?x=1` and `POST /portfolio/holdings`.
- The call is in the allow-list for the read module only.
- No price/P&L field is kept.

## DB
NOT the shared-DB holder; run no DB command. Local: your test file + the Tests line + `python scripts/ruff_ratchet.py`.

## Rules
- Branch `build/W-106-holdings-read` from origin/main. Work card `work/W-106.md` (frontmatter shape of
  `work/W-100.md`; requirement_ids [REQ-073]; tier A; depends_on [W-093]; tests_required
  ['AC-4: tests_app/test_kite_reads.py']) and `W-106: 4b` in `docs/process/coverage-stages.yaml`.
- Never copy .env; no PR. No kit or `spec/` edit, no `views/`, no `evidence/`. Common rules: `docs/process/builder-brief.md`.
