# GC-2e contract: independent review record (chain rule 3)

Reviewer: fresh Opus agent, read-only (Explore type), not the author and not the reviewer of the GC-3 draft; run
2026-10-17 ~09:05 IST on the first GC-2e draft (docs worktree). Raw output below, verbatim, then the orchestrator's
decision on each finding, then the narrow re-check of the applied changes.

## Reviewer output (verbatim)

I found four MAJOR and four MINOR problems. The proof the contract names as its core cannot run on what is merged today, and item 2's audit write would be refused by the allow-list as written.

**Findings**

1. **MAJOR: the Core/Proof has no replay to run against, and no item builds one.** On main, replay mode only overrides the outcome route and the live socket (`backend/ofo_app/main.py:76-82`).
   - Without a live Kite session the Execute route answers "broker unconfirmed" (`execute.py:129-135`, `:261-262`).
   - The depth price comes from the real live market, which is empty under replay ("the test replay has none", `live_market.py:240-244`). So every leg is refused.
   - The CI replay API on port 8001 only serves the recorded 2026-10-08 frames (`app-tests.yml:256-269`).
   - Nothing replays the orders, positions, funds, basket-margin or quote replies for Execute, or any reply for the return route.
   - The line "`OUTCOME_REPLAY=1`-style" (contract line 17) hides this gap. Item 2 or 3 must name a test-only replay (refused outside `APP_ENV=test`, like `replay_mode.require_test_env`). That replay must cover: the Kite session replies for both routes, depth for the leg, a pinned market-hours clock, and a seeded strategy plus a Pro grant. Being test code inside the order path, it is Tier A.

2. **MAJOR: the allow-list cannot carry item 2's `execution_recorded` payload.** The allow-list declares `execution_recorded` as a Kite trade record only: `trade_id, order_id, … fill_timestamp` (`audit_allowlist.py:44-46`, `:108-112`, `:130`). A payload of `{plan_number, tags, action}` keeps no declared field, so it is refused with `PayloadShapeError` (`:206-210`). The matching event type is `order_prepared` (`ofo/audit/catalogue.py:22`), and it is undeclared, so it is refused too (`:58`). Item 2 therefore needs a new allow-list entry plus a migration that updates the database copy (the 0015 pattern). The contract names neither. It also uses `execution_recorded` with a meaning W-017 did not give it, and it should say whether the return route writes `execution_recorded` from `GET /trades`.

3. **MAJOR: "the figures `checked_basket` already read" is not true of the code.** The sealed `KiteBasket` holds only the orders, with no margin figures (`ofo/execution/basket.py:136-156`). The route reads Zerodha's margin once in `_context` (`execute.py:503`, `:419-427`) and again inside `checked_basket` (`basket.py:270-271`). The contract must choose: either expose the figures from the seal (a domain change to sealed objects, W-098), or show the `_context` figures and say they come from a separate read.

4. **MAJOR: the "cost" leaves out charges.** "Premium 217.75" is right as arithmetic (65 x 3.35). But ADR-082 (1) has the engine compute charges per order, REQ-056 AC-8 lists "margin, charges" in the order plan, and a calculator already exists (`ofo/charges/calculator.py:72`). On a Rs 218 buy, Rs 20 brokerage plus GST is about 10% of the cost, so the owner would say yes to an understated figure (ADR-097 (3)). Also, "per BUY leg" gives the L3 exit (a SELL) a cost of zero. It should be a signed net premium.

5. **MINOR: the time plan does not fit, and the give-way order does not protect it.**
   - Items 1, 2 and 3 run in a strict chain (screen needs cost and audit, which need the return route) and are all Tier A. At the previous review's rate of 1-1.5 h per Tier A item, plus the unnamed replay from finding 1, that is about 4.5-5 h against 4.5 h available.
   - Parking items 7, 6 and 5 frees no time on that chain.
   - Suggested changes: run item 4 in parallel from the start; split the cost half of item 2 from the audit half so item 3 can start earlier; say what GC-3 does if item 3 parks.

6. **MINOR: item 5 can be parked, but ADR-097 (4) requires the holdings read.** GC-3's L4 has no fallback if item 5 parks. Either GC-3 must name an owner-read fallback, or item 5 should move into the contract set.

7. **MINOR: the goal-chain table was not updated (review finding 7 only half landed).** In the worktree's `goal-chain.md` there is no GC-2e row. The GC-3 row still reads "Mon 09:15 if GC-2c is DONE", "written by GC-2c", and has no 13:30 latest start (`goal-chain.md:28`).

8. **MINOR: the entry margin used in the proof is a derived reply, not a recorded one** (`tests/fixtures/kite_replies/margins-basket-entry-derived.json`). The proof should say "derived".

**Review findings 1-13:** 1-6 and 8-13 landed (contract lines 31-60, 65-73). 7 landed in the contract but not in the chain table (finding 7 above). 2 and 3 landed with the defects in findings 2-4.

**Spec departures:** none quoted as a SPEC CHANGE. Findings 2 and 4 depart from W-017 / REQ-063 AC-5 (allow-list semantics) and ADR-082 (1) (charges). The contract should resolve them rather than label them.

| Claim | Evidence (tool call this turn) |
|---|---|
| Replay overrides only outcome and socket | Read `main.py:76-82` |
| Execute needs a real session and live depth | Read `execute.py:129-135,156-165`; `live_market.py:237-244` |
| CI replay serves only 2026-10-08 frames | Read `app-tests.yml:256-269` |
| `execution_recorded` is a trade record; payload with no declared field refused | Read `audit_allowlist.py:44-46,108-130,206-210` |
| `order_prepared` exists | Read `ofo/audit/catalogue.py:22` |
| Basket has no margin figures | Read `basket.py:136-156` |
| ADR-097 "cost"; ADR-082 charges | Read `ADR-097.md:10-11`; Grep `ADR-082.md:5-8` |
| Charges calculator exists | Grep `ofo/charges/calculator.py:72` |
| #358 still open; W-099 merged | `gh pr list` → 358 OPEN, 360 MERGED |
| No GC-2e row; GC-3 row stale | Grep of the worktree `goal-chain.md:28` |
| Kite basket return behaviour | unverified |

**Verdict: NOT READY.** Findings 1-4 change the scope of items 2 and 3, so the contract needs another pass before it runs.

## Decisions (orchestrator)

| # | Decision | Applied as |
|---|---|---|
| 1 MAJOR | ACCEPTED | New item 2 (W-101): a test-only Execute/return replay (refused outside APP_ENV=test like `replay_mode.require_test_env`): the recorded Kite session replies for both routes, depth for the leg, a pinned market-hours clock, a seeded strategy id 1 and a real Pro grant; Tier A. The core proof names it. |
| 2 MAJOR | ACCEPTED | Item 4 (W-103): the Execute route writes `order_prepared` (newly declared in the allow-list with plan number, tags, action, strategy id - migration in the 0015 pattern, a real downgrade); the return route writes `broker_response_recorded` (W-017 keys) per read-back and `execution_recorded` per trade row of `GET /trades` (W-017's trade shape). `execution_recorded` keeps W-017's meaning. |
| 3 MAJOR | ACCEPTED | The cost shows the `_context` figures - Zerodha's funds and basket-margin read in the same request, before `checked_basket` reads again - labelled with their read time; no change to the sealed basket (W-098). |
| 4 MAJOR | ACCEPTED | Cost = signed net premium (BUY pays, SELL receives) + charges from `ofo/charges/calculator.py` (ADR-082 (1), REQ-056 AC-8) + Zerodha's required margin, each a 2-decimal string; the exit shows its own cost. |
| 5 MINOR | ACCEPTED | Item 6 (where Kite returns the browser) runs in parallel from the start; cost (item 3) is split from audit (item 4) so the screen (item 5) can start after the replay + cost; if the screen parks, GC-3 is not started - the next contract finishes it first. |
| 6 MINOR | ACCEPTED | The holdings read moves into the contract set (item 7, never given way before items 1-6 finish or park). |
| 7 MINOR | ACCEPTED | The chain table gains the GC-2e row (NEXT) and GC-3 reads "written by GC-2e, L2 no later than 13:30 IST" in the GC-2c close-out PR. |
| 8 MINOR | ACCEPTED | The proof says the entry margin reply is DERIVED (`margins-basket-entry-derived.json`). |

## Re-check of the applied changes (fresh Sonnet, read-only, 2026-10-17 ~09:10 IST)

Verdict: "Applied: all | missing: none". Row 6 had a wording gap (items 1-7 never given way was implied, not
written) - now written. Two loose spots it named were fixed in the contract: the charge rates' source (the stored
rates the outcome route loads; no rates -> no charges figure, never a default) and the audit link
(`broker_response_recorded` / `execution_recorded` carry order / trade ids, not plan numbers - the link to the plan
is the order id).
