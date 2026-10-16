# Builder brief: #321 margin gate must not block a closing basket (Tier A: money gate)

Core: `required_from_basket_reply` treats Kite's `final.total` below 0 (a basket that closes or reduces held positions
releases margin) as 0 required, never as a credit; the real 2026-10-16 exit reply (`final.total -214.5`) then gives
required 0 and `check_margin(available, 0)` allows it; an entry reply is unchanged.
Proof: copy `margin_raw` (the reply) and `order` (the request) from
`D:/Abhay/Ventures/ofo-kite-ticks/2026-10-16/real-order/fetch.json` (recorded 15:06 IST: SELL 65 NIFTY26O1923650CE NRML
against +65 held) into `tests/fixtures/kite_margins/basket-2026-10-16-exit-sell-held.json` (numbers as JSON numbers,
no account data beyond the reply); a test on it fails on origin/main (MarginReplyError) and passes after.

Model: sonnet.
Budget: 20 min wall-clock, 40 tool calls. At budget STOP and report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under 200 words, branch + head sha.
Copy from: none - this repo's `backend/ofo/execution/margin_gate.py` (W-081, ADR-094).
Findings checked: margin-gate-blocks-closing-basket, money-parsed-through-float, targeted-tests-miss-dependent-files

## Spec basis
ADR-094 decision: "a negative difference counts as 0, never as a credit". ADR-016 (Zerodha is the authority on
margin). REQ-055 AC-1 (build the basket only if available >= required).

## Class (defect-fix contract)
- RCA: the gate validates Kite's required figure as "0 or more", but Kite reports a position-reducing basket with a
  negative figure.
- Class: every basket whose legs close or reduce held positions (exit, square-off, Complete/Retry of a closing leg,
  net-down adjustments), NFO and BFO. Before: all blocked; after: none blocked for margin when Kite's figure <= 0.
- Detection: the real-fixture test plus a property test: for any reply, required >= 0 and required >= final.total.

## Must hold (reviewer checklist - test each first)
1. Negative final.total -> required 0; it is never subtracted from or added to available funds.
2. NaN / inf / missing / non-number final.total still raises (fail closed); only a finite negative becomes 0.
3. ADR-094 top-up still added for BUY legs on top of max(final.total, 0) (a mixed basket: BUY new leg + SELL a held
   one) - write one case by hand.
4. Available funds negative still blocks (unchanged).
5. Mutation: removing the max(.., 0) clamp makes the real-fixture test fail; letting a negative through as a credit
   (available - final.total) makes a test fail.

## Rules
- Your own worktree, branch `fix/321-exit-margin` from `origin/main`.
- Tests: `python -m pytest -q -p no:cacheprovider tests/execution tests/test_*.py tests/errors/test_write_allowlist.py`;
  the app client test `tests_app/test_kite_margin_client.py` via the main checkout's
  `scripts/orchestrator/db_run.py <worktree> ...`; `python scripts/ruff_ratchet.py`.
- No new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; no regenerated files in the PR.
- Commit message without the word "spec"; commit and push; do not open the PR; never write `evidence/`, `work/` or the
  spec. Never call Kite.
