# Review of the GC-2g contract (chain rule 3; fresh Opus, 2026-10-18)

Round 1: **CHANGES NEEDED**, 1 MAJOR + 3 MINOR - all accepted, applied before merge.

| # | Sev | Finding | Decision |
|---|---|---|---|
| 1 | MAJOR | `pending` had no end and did not say it blocks: only `routes/execution_return.py:252` closes a plan and `execution_plan_store.py:18` says nothing reopens one, so a user who never returns from Kite's page leaves the contract pending forever, hiding any shortfall (finding state-with-no-working-exit) | Accepted: pending BLOCKS the strategy; it ends when the open plan's own orders (by tag) are final in Zerodha's order book, then normal comparison applies even without Check; tests for the never-returned case. Recorded as ADR-110 with the owner's view decision |
| 2 | MINOR | How pending looks on Positions is the owner's call | Accepted and asked at once (owner present): "Show waiting + link (Recommended)" -> ADR-110, REQ-044 section + pin |
| 3 | MINOR | REQ-052 AC-1 is not evidence-only and W-067 (REQ-051, done) is the wrong owner; `test_kite_history.py` only tests the client | Accepted: a new work item and a new repo_scan test that no route or page shows history |
| 4 | MINOR | The 08:30 fallback named only `lock/gc-2f` | Accepted: the delta names `lock/gc-2f` or `lock/gc-2g` |

Confirmed by the review: the cap (close-out by 06:45 at the latest) and rule 4b read correctly; nothing lets a product
commit reach main (every code item is a HOLD PR; GC-3L's docs-only head check backs it).
Verdict after fixes: READY (no round 2 needed: every finding was a text change applied as written).
