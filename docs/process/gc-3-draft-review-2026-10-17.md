# GC-3 draft contract: independent review record (chain rule 3)

Reviewer: fresh Opus agent, read-only (Explore type), not the author; run 2026-10-17 ~08:55 IST on the draft
`goal-contract-GC-3-2026-10-19.md` (unmerged, docs worktree). Raw output below, verbatim, then the orchestrator's
decision on each finding. Outcome: the draft was split - the NEXT contract is GC-2e (live-order preparation,
unattended, `goal-contract-GC-2e-2026-10-18.md`), and GC-3 stays the owner-present live run, written by GC-2e. The
GC-2e contract was then reviewed on its own (`gc-2e-contract-review-2026-10-17.md`).

## Reviewer output (verbatim)

**Verdict: NOT READY.** The order-safety guardrails are right, but the contract claims things are in place that are not on main. The live run would hit at least five of these gaps after the owner has already logged in.

**Findings**

1. **MAJOR: the return route (W-096) is not merged.** The contract (line 19) lists W-096 as merged in #358, but #358 is still OPEN with CI pending. `backend/ofo_app/routes/` on main has no return route; the only POST route there is `execute.py:251`. Fix: make W-096 a precondition, or add it as a P-step that never parks, the way P1 is conditioned on W-100.

2. **MAJOR: no audit event will exist for L4 to read back.** L4 (line 55) expects `broker_response_recorded` and `execution_recorded` events from the run. Nothing in the execute path writes audit events (grep for `audit` in `routes/*.py`, `execution_plan_store.py` and `execute_plan.py`: 0 hits). #358 writes only `BROKER_RESPONSE_RECORDED`, and only for orders tagged for the strategy that have no stored plan (diff lines 350-351, 603-609). Nothing writes `execution_recorded`. Fix: add a writer as a P-step, or drop that part of L4.

3. **MAJOR: the route never returns the "cost" the owner must approve.** ADR-097 (3) requires a final yes on "contract, side, quantity, limit price and cost". `ExecuteOut` (`execute.py:107-111`) returns only `plan_number`, `tags`, `basket` and `orders`, with no margin or cost field. The browser must not compute money (`decimal-money-boundaries.md`). P2 promises "Zerodha's margin figure" but no P-step changes the route to return it.

4. **MAJOR: the live price depends on a subscription the contract never mentions.** `LiveDepthQuotes.leg_quote` returns None, which refuses the leg, unless the live feed holds a full frame for that contract (`execute.py:156-165`, `live_market.py:237-244`). Your own memory notes "the REST outcome is 'not live' without a subscribed screen". P2 must keep a live subscription open for the legs' contracts while the Execute screen is up, with a test for it.

5. **MAJOR: the holdings check compares fields that move on every tick.** P3 returns "exact Decimal rows" and L4 asserts before == after. Holdings rows include last price and P&L, which change all day, so L4 would fail on prices alone. Fix: name the compared fields (symbol, exchange, quantity, t1_quantity, ISIN).

6. **MAJOR: where Kite sends the owner back after the basket is unproven, and it can trigger a false stop.** The only Kite return handler on main is the login callback, which refuses anything without a valid `state` (`broker.py:238-242`). If Kite sends the owner back to that registered URL (I have not verified Kite's behaviour), the owner sees a refusal page. The stop at line 91 ("Kite login fails") could then fire by mistake. Fix: say where the owner lands, and that the return route is called by the run's action, not by a redirect.

7. **MAJOR: the time plan does not fit, and two rules conflict.**
   - P1, P2 and P3 are all Tier A. The GC-2c review measured about 1-1.5 h per Tier A item; P2 also waits on Playwright in CI. That is roughly 3.5-4.5 h, which uses up the 4.5 h left after the 1.5 h tail before any L-step.
   - The chain row says "Mon 09:15, ~2 h" (`goal-chain.md:28`).
   - "P1-P3 never parked" contradicts the park rule at line 93 (two failed rounds of one class means park).
   - Fix: run P1-P5 in an earlier unattended session, and start Monday's session only at L1, with a latest L2 start time (for example 13:30) so the exit can still happen before 15:00.

8. **MINOR: no step for an entry that does not fill.** A LIMIT entry may sit open. Add a stop: no fill within N minutes means the owner cancels on Kite, the return route closes the plan, there is no exit, and nothing is retried (ADR-017).

9. **MINOR: L2 does not say who clicks the button that opens Kite's page.** That POST opens Kite's site in the browser. Under ADR-097 (2) ("no ... assistant action ... operates Kite's site") it should be the owner's click, so state it.

10. **MINOR: P2 uses field names the route does not have.** P2 says "`form_fields` to `basket_url`", but the route returns `basket: {url, api_key, data}` (`basket_post.py:89-91`). The brief should use the real names.

11. **MINOR: "P&L from the fills = Kite's" does not say gross or net of charges.** Kite's position P&L is gross. Say which one is compared.

12. **MINOR: P4 will clash with W-096.** P4 makes the audit store stamp its own time, but #358 passes `timestamp=at` into `audit_store.append`. P4 has to land after W-096 and update that caller.

13. **Core/Proof: acceptable, with one gap.** The core is named correctly, and its parts were proven on recordings in GC-2c. But the first live proof is at L2, after the screen is built. Suggest a no-order live probe right after L1: depth and band for the chosen contract read live. Avoid calling the Execute route for the probe, because it stores a plan, and one open plan blocks the next press (ADR-105).

14. **Spec: no contradiction found.** L2's items match ADR-097 (3). No API order is planned (ADR-100). The holdings read and W-100's quote read are reads, so the static-IP rule does not apply. The wording "Execute Strategy" matches REQ-056 AC-1.

| Claim | Evidence (tool call this turn) |
|---|---|
| #358 not merged | `gh pr view 358` → `"state":"OPEN","mergedAt":null`, checks api/lint-and-test/frontend still pending |
| No return route on main | `ls backend/ofo_app/routes` and grep for `@router.post`: only `execute.py:251` plus non-execution routes |
| `execution_recorded` never written | grep of `gh pr diff 358` → only `EventType.BROKER_RESPONSE_RECORDED` (line 603); grep for `audit` in the execute path → 0 hits |
| No cost or margin in the reply | Read `execute.py:107-111` |
| Depth needs a live full frame | Read `execute.py:156-165` and `live_market.py:237-244` |
| Login callback refuses without state | Read `broker.py:238-242` |
| Basket reply field names | Read `basket_post.py:89-91` |
| Migration head is 0016 | `ls alembic/versions` → `0016_execution_plans.py` |
| How Kite returns the owner after the basket | unverified |

**Verdict: NOT READY.** Findings 1-7 need contract changes; 8-12 are wording fixes.

## Decisions (orchestrator)

| # | Decision | Applied as |
|---|---|---|
| 1 MAJOR | ACCEPTED | W-096 is merged in the GC-2c close-out before NEXT is set, or it is GC-2e's first item; the contract states which, with the PR number read from GitHub. |
| 2 MAJOR | ACCEPTED | GC-2e item: the Execute route writes `execution_recorded` when it stores a plan and the return route writes `broker_response_recorded` for every read-back (within the W-017 allow-list); GC-3's audit read-back then has events to read. |
| 3 MAJOR | ACCEPTED | GC-2e item: the Execute reply carries the cost the owner approves - Zerodha's required margin and available funds, and the basket's premium (quantity x LIMIT per BUY leg), each as a 2-decimal string computed server-side. |
| 4 MAJOR | ACCEPTED | GC-2e's Execute screen holds a live subscription for every leg's contract while it is open, with a test; GC-3 adds a no-order live probe (depth + band read) right after L1. |
| 5 MAJOR | ACCEPTED | Holdings compared on tradingsymbol, exchange, isin, quantity, t1_quantity only (GC-2e's holdings read returns them; GC-3 asserts them). |
| 6 MAJOR | ACCEPTED | GC-2e item: find out (zerodha-expert skill, Kite's basket docs, no order) where Kite returns the browser after a basket and make that a page that does nothing but show the "Check with Zerodha" action; the return route is called by the owner's click, never by a redirect. Unverified until then - written so. |
| 7 MAJOR | ACCEPTED | Split: GC-2e = all preparation, unattended, its own 6 h cap; GC-3 = the live run only (~2 h, owner present), L2 no later than 13:30 IST. The "never parked" line is dropped - GC-2e's items follow the park rule. |
| 8 MINOR | ACCEPTED | GC-3: an entry not filled within 15 min -> the owner cancels on Kite; the return route closes the plan; no exit; nothing retried (ADR-017). |
| 9 MINOR | ACCEPTED | GC-3: the owner clicks the button that opens Kite's page (ADR-097 (2)). |
| 10 MINOR | ACCEPTED | Real field names (`basket.url`, `basket.api_key`, `basket.data`) in GC-2e's screen item. |
| 11 MINOR | ACCEPTED | Gross P&L compared (Kite's position P&L is gross; ADR-102). |
| 12 MINOR | ACCEPTED | The store-stamps-its-own-time mechanism lands after W-096 and updates its caller (stated in GC-2e). |
| 13 | ACCEPTED | GC-3 opens with the no-order probe after L1; the Execute route is not used for the probe (an open plan blocks the next press). |
| 14 | NOTED | No spec change. |
