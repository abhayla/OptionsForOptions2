# Review of the GC-2f contract (chain rule 3; fresh Opus, 2026-10-18)

Under review: `goal-contract-GC-2f-2026-10-18.md`, ADR-109, W-108..W-111, the REQ-044/058/060 edits, goal-chain and the
GC-3L delta line. The plan before it had its own fresh Opus review (12 findings, all applied; recorded in the plan).
Round 1: **CHANGES NEEDED**, 2 MAJOR + 7 MINOR. Every "exists" claim checked held (`held_units` :188,
`strategy_blocked` :233, `compare` :399, `GET /strategies` :329, the fixtures, `end_session(reason='disconnected')` at
`broker_token_store.py:103`); no product commit can reach main.

| # | Sev | Finding | Decision |
|---|---|---|---|
| 1 | MAJOR | On the 08:30 fallback main still marks GC-2f NEXT, so the standard prompt re-runs GC-2f | Accepted: the delta gives a fallback prompt naming GC-3L |
| 2 | MAJOR | Surplus measured against one strategy's held units only; strategy 65 + standalone 25, Zerodha 90 would block, breaking REQ-060 AC-7's example | Accepted: surplus = Zerodha net - (all strategies' held + recorded standalone); cases (e) standalone, (f) two strategies Q224, (g) contract held by none added to W-108 and the contract; ADR-109 / REQ-060 text corrected |
| 3 | MINOR | Close-out fixed at 06:45 while the cap may be earlier | Accepted: close-out at cap - 45 min; GC-3F draft written as soon as items 1 and 7 settle |
| 4 | MINOR | `outcome.py:231` `step` is response-only; W-090 needs a request change | Accepted |
| 5 | MINOR | REQ-044 `depends_on: [REQ-060]` not applied; Q-B4 not in open-questions | Q-B4 accepted (Q272). `depends_on` **rejected**: `build_order.py --may-start REQ-044` then refuses ("waiting: on REQ-060") and `order_override` cannot skip an unfinished dependency (`build_order.py:30-31`), so Positions could not start until reconciliation is Verified; the real dependency is W-111 `depends_on: W-108`, with part 2 after GC-3F |
| 6 | MINOR | "exit of 65 fills 30" cannot happen (whole lots) | Accepted: 130 fills 65 |
| 7 | MINOR | The shortfall line was stated back, not answered; REQ-058's "Why" is ours | Accepted: labelled as the unchanged AC-6/Q199 rule restated; the reason labelled as the orchestrator's |
| 8 | MINOR | W-108 must say how `intended_position` is built and keep the raw net | Accepted |
| 9 | MINOR | Item 8 had only a Sonnet re-check before a live run | Accepted: scoped fresh Opus re-check of GC-3L against ADR-109 and ADR-108 |

Scope (reviewer): the full list is tight for one night; cut order W-111, #370, W-110's evidence passes - written into
the contract.

## Round 2
Fresh Sonnet re-check of the 9 fixes: all FIXED (path:line each); the `depends_on` rejection judged sound
(`build_order.py:27-32, 297-330`: `order_override` skips only the earlier-group check); the seven W-108 cases (a)-(g)
agree with each other, ADR-109 and REQ-060 AC-7. Two wording nits accepted: case (e) is the lot-65 analogue of AC-7's
example; case (d) is an opposite-direction difference, asserted explicitly. **Verdict after round 2: READY.** Review
rounds used: 2 of 2.
