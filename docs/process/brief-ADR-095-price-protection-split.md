# Builder brief: ADR-095 price protection split (pro rata) - REQ-056 AC-7 (Tier A: order price)

Core: `protected_limits(legs, tolerance, tick)` splits one strategy-level rupee tolerance across legs in proportion to
each leg's planned value (|planned price| x quantity); each leg's LIMIT = planned price + share/quantity for a BUY,
planned price - share/quantity for a SELL, rounded to the tick toward the user with the existing `round_to_tick`; the
sum of (limit - planned) x quantity in the user's adverse direction never exceeds the tolerance.
Proof: a test on the REAL iron-condor quotes recorded today (`D:/Abhay/Ventures/ofo-kite-ticks/2026-10-16/rest/
rest-120852.json`, call `quote NIFTY 2026-10-19`, the four iron_condor symbols listed in the call
`margins/basket NIFTY 2026-10-19 iron_condor bump=0 cp=true`): copy the four quotes (depth + last_price only) into
`tests/fixtures/kite_quotes/iron-condor-2026-10-16.json` (numbers as JSON numbers), use last_price as planned price,
tolerance Rs 300, and assert the hand-computed per-leg limits; also report, per leg, whether today's depth fills the
quantity within the protected limit (reuse `executable_limit`).

Model: opus.
Budget: 40 min wall-clock, 75 tool calls. At budget STOP and report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under 300 words, branch + head sha.
Copy from: none - extends `backend/ofo/engine/executable_price.py` (W-078); legacy-reuse map has no price-protection row.

## Spec basis
- ADR-095 decision, verbatim: "each leg gets the share of it that its planned value (planned premium x quantity) has of
  the sum of all legs' planned values."
- ADR-080 (3): "price protection splits the user's strategy-level tolerance into per-leg limits."
- REQ-056 AC-7: "the user picks 'Execute at current market conditions' or 'I want price protection' with a limit or a
  strategy-level price tolerance (e.g. expected credit ₹12,500, executable ₹12,350, max slippage ₹300) (Q28)."

## What to build (domain only, `backend/ofo/engine/`, standard library)
- A pure function and a result type per leg: planned price, quantity, side, rupee share, protected limit, and
  `fills_within` (from `executable_limit` on the leg's depth: fillable AND its limit is not worse than the protected
  limit), plus the strategy total of adverse rupees allowed (must be <= tolerance).
- Share in exact Decimal; the leftover from rounding is never handed to another leg (rounding toward the user only
  makes each leg tighter).
- A SELL limit that would fall to 0 or below is clamped to one tick, never 0 or negative.
- Refuse (ValueError): tolerance < 0, not Decimal, empty legs, total planned value 0, quantity <= 0, price <= 0.
- No UI, no route, no wiring into the basket in this item (that is a later item; say so in the docstring).

## Reviewer checklist (Tier A reviewer attacks these - test each first)
1. Sum of adverse rupees over all legs <= tolerance in every case (property test over random legs, 2,000 cases).
2. Rounding direction: BUY floors, SELL ceils (reuse `round_to_tick`), never a looser limit than the share allows.
3. A 1-paisa tolerance: every leg's limit equals its planned price rounded toward the user (no room).
4. A leg with 80% of planned value gets 80% of the tolerance (exact Decimal case).
5. SELL clamp at one tick.
6. Mixed BUY/SELL legs, 4 legs, plus single-leg.
7. Mutation: equal split instead of pro rata; rounding away from the user; share computed on signed value -> a test fails.
Findings classes checked: grep `knowledge/findings/` for `rounding`, `tick`, `decimal`, `float`.

## Rules
- Your own worktree, branch `build/ADR-095-price-protection` from `origin/main`.
- Targeted tests only: `python -m pytest -q -p no:cacheprovider tests/engine`; `python scripts/ruff_ratchet.py`.
- No new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; no regenerated files in the PR.
- Commit and push; do not open the PR; never write `evidence/`, `work/` or the spec. Never call Kite.
