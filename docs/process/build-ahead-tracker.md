# Build-ahead tracker (every decided item, tracked until it is closed)

Owner, 2026-10-18 ~23:00 IST: "create a goal contract for this so that it should complete everything that is decided,
and ... properly track everything until it is closed." Plan: the 2026-10-18 inventory (43 open issues, 75
requirements, the goal chain) with its priority list P1-P5; ADR-112 (4c after the 4b fixes).

Rules (goal-chain.md chain rules 8-9): every contract's close-out updates the rows it touched and runs
`python scripts/orchestrator/tracker_check.py .`; a row is never deleted; it leaves only as `closed` (merged + verified,
or the issue is shut with evidence), `parked #N` or `deferred #N`. No row is open without a contract.

Status words: `todo`, `building`, `held #PR` (open draft PR, HOLD until GC-3L ends), `merged #PR`, `verified`,
`closed`, `parked #N`, `deferred #N`, `blocked-owner`, `blocked-live`.

| Id | Item | P | Contract | Tier | Status | Evidence |
|---|---|---|---|---|---|---|
| #352-1 | #352 half 1: an earlier-day open plan resolved the next day from positions only (ADR-111; deadline Mon 10-26 12:00) | P1 | GC-3F | A | held #421 | GC-2h: R1 REVISE (other holders not blocked) -> round-2 fix a474d30 + openapi; round-2 review NOT run (cap) - first step of GC-3F |
| #352-2 | #352 half 2: close-of-day read (after 15:30 IST, before the book clears) closes every open plan | P1 | GC-3F | A | todo | needs the live timing |
| #352-proof | Real next-day positions reply captured with `probe.py` (Wed 2026-10-21) as #352-1's pre-merge proof | P1 | GC-3F | A | blocked-live | GC-2h review MINOR 8 |
| OQ-GC2h-1 | Owner question: may a next-day net be adopted as the strategy's fill (ADR-109 (2) says never automatically)? | P1 | owner | A | blocked-owner | owner-questions-2026-10-19.md |
| #352 | Open plan cannot be read back next day - closes when #352-1 and #352-2 merge + verifier | P1 | GC-3F | A | todo | |
| #380-1 | #380 step 2.1: migration - stored mismatch record, sticky block (Q222), standalone store (REQ-060 AC-7) | P1 | GC-3F | A | held #419 | GC-2h: R1 REVISE -> R2 PASS (eb3d871); openapi regenerated 5ee4e1d, CI re-run pending |
| #380-2 | #380 step 2.2: one reconciler in both routes (via #398), triggers as reads, expired legs (T6) | P1 | GC-3F | A | todo | |
| #380-3 | #380 step 2.3: partial actions (ADR-109 (3)), 3-action reconcile screen (ADR-109 (4)), rejection reason | P1 | GC-3F | A | todo | |
| #380 | Live Kite-basket routes skip reconciliation/partial rules (F-42) - closes when #380-1..3 merge + verifier | P1 | GC-3F | A | todo | |
| #389 | Exit basket mixes buy-backs and sells (shorts-first, REQ-058 Q238) - with #380-2 | P1 | GC-3F | A | todo | |
| #390 | Entry basket cannot hold a sell until its protective leg fills (REQ-056 AC-3/4) - with #380-3 if it fits | P1 | GC-3F | A | todo | |
| #338 | Negative balance blocks a closing (reduce-only) basket | P1 | GC-3F | A | held #418 | GC-2h: R1 REVISE -> R2 PASS; CI fix (held from stored plans) 891bc52, CI green; ADR-113 |
| #353 | Kite allow-list checked per call, not per calling module | P1 | GC-3F | A | held #418 | with #338 |
| #63 | Two ProposedOrder builders do not slice at the freeze limit | P1 | GC-3F | A | held #420 | GC-2h: R1 REVISE -> R2 PASS 0ca3bc7, CI green |
| #43 | Plan gaps: Complete ignores freeze/margin; per-slice failure; lot alignment | P1 | GC-3F | A | held #420 | with #63 |
| #263 | NRML+MIS same contract blocks exits; non-NRML entry; freeze load race | P1 | GC-3F | A | todo | |
| #279 | Settle-before-reconcile order; expired standalone note; persist settlement state | P1 | GC-3F | A | todo | |
| #115 | Orders linked to the catalogue by symbol, not InstrumentId | P1 | GC-3F | A | todo | |
| #405 | W-108 attribution (redesigned, round 2 PASS) | P1 | GC-3F | A | held #398 | GC-2g handover |
| W-111 | Positions part 1 (stacked on #398) | P1 | GC-3F | A | held #410 | GC-2g handover |
| #381 | Return route reads trades before orders | P1 | GC-3F | A | held #394 | GC-2f handover |
| #370 | e2e flake: API pools exhausted the role's connection limit | P5 | GC-3F | B | held #395 | merges FIRST in GC-3F |
| W-109 | My Strategies list + Completed filter | P4 | GC-3F | B | held #393 | |
| W-110 | Repo-wide money guard (REQ-063 AC-3) | P2 | GC-3F | B | held #396 | |
| W-089 | Settings -> Broker & Market Data (+ ofo_dev proof after merge) | P4 | GC-3F | A | held #397 | |
| W-090 | User scenario range, At Expiry / Estimated Now | P4 | GC-3F | B | held #399 | |
| W-112 | REQ-052 AC-1 no history shown (evidence written) | P4 | GC-3F | B | held #408 | evidence/W-112/AC-1.md on the branch |
| #400 | Money/P&L figures computed outside the engine (ADR-008) | P2 | GC-3G | A | todo | |
| #240 | ADR-082 charges in the engine; money sentences include charges | P2 | GC-3G | A | todo | |
| #313 | Order book, fills, adopted holdings persisted (with #380-1's store) | P2 | GC-3G | A | todo | |
| #45 | W-026 backup checks unpinned; REQ-056 AC-7 price unchecked | P2 | GC-3G | A | todo | |
| #234 | W-065 verifier LOWs (push matcher, socket fallback, outage leg edit) | P2 | GC-3G | A | todo | |
| REQ-041 | Rule engine open points: priority, conflict, cooldown | P3 | GC-4 | A | todo | ADR-112 |
| REQ-043 | Live monitoring statuses (on the replay) | P3 | GC-4 | A | todo | ADR-112 |
| REQ-042 | Alert + prepared basket, user confirms (ADR-002) | P3 | GC-4 | A | todo | ADR-112 |
| REQ-062 | In-app Alerts + AC-3 dedupe against a fake Notifier | P3 | GC-4 | B | todo | ADR-112 |
| REQ-064 | Stored timeline + audit emitters (2 of 33 event types today) | P3 | GC-4 | A | todo | |
| #107 | Scheduled audit-log verification monitor | P3 | GC-4 | B | todo | |
| GC-5 | A real rule fires; WhatsApp via the Notifier delivered | P3 | GC-5 | A | blocked-live | owner go + release record |
| #404 | Evidence REQ-048 AC-1/AC-5, REQ-049 AC-4 (REQ-052 AC-1 done in #408) | P4 | GC-3G | C | todo | |
| #148 | Response serializer + request-boundary user words | P4 | GC-3G | A | todo | REQ-065 before Stage 5 |
| #199 | Response door MINORs (expires strip, per-status headers, dynamic shapes) | P4 | GC-3G | B | todo | |
| #200 | Response door module rebinding (parked after 9 rounds) - independent redesign | P4 | GC-3G | A | parked #200 | |
| #220 | Responsive clipping check on the data-filled table | P4 | GC-3G | B | todo | |
| #409 | History scan misses aliased import shapes, `intraday` | P4 | GC-3G | B | deferred #409 | |
| #411 | Positions pending-row wording; pending e2e is a mock | P4 | GC-3F | B | deferred #411 | |
| #297 | Gate 4a minors (raw symbols, duplicate notice, margin login message, Loss 0) | P4 | GC-3G | B | todo | |
| #402 | Broker settings wording after a failed read | P4 | GC-3F | B | todo | |
| #126 | Catalogue delist limit + refusal alert in the daily load job | P4 | GC-3G | B | todo | |
| #386 | GC-3 P0 review MINORs (probe private attrs, recorder compare, W-107 pins) | P4 | GC-3F | B | todo | |
| #401 | Disconnect route: owner check / cross-site protection (full fix with Stage 5 login) | P4 | GC-3F | A | todo | |
| #403 | Windows local pytest EgressRefused (+ the eslint-run test that never runs) | P5 | GC-3F | A | held #424 | GC-2h: built, NOT reviewed (cap); a hook change = Tier A review first |
| BUDGET | Nothing stops a worker at its tool-call budget (101-122 of 50-80 on 2026-10-18/19) | P5 | GC-3F | C | todo | kit item: handoff file New 4 |
| TRACKER | `tracker_check.py`: tracker vs GitHub states, every open issue has a row | P5 | GC-3F | B | held #417 | GC-2h: Tier B PASS, minors fixed, CI green |
| #344 | History finalize scale test flaky on CI | P5 | GC-3G | B | todo | |
| #318 | Clean up 462 `# noqa` markers | P5 | GC-4 | C | todo | |
| #247 | atool selector misses two-hop dependents | P5 | GC-4 | C | todo | |
| #191 | gate_before_commit bypasses | P5 | GC-4 | C | todo | |
| #385 | GC-3 live steps L1-L4 | - | GC-3L | A | verified | GC-3L 2026-10-19: strategy 9 entry filled 65 @ 7.00, exit 65 @ 6.65, 0 mismatches, holdings unchanged, pnl_equal -22.75, audit chain rows=9 (`session-handover-2026-10-19-gc3l.md`); issue to close with this evidence |
| TAG-8 | Basket tag over Kite Publisher's 8-character limit for strategy id >= 10 / version >= 10 (finding basket-tag-exceeds-publisher-limit) | P1 | GC-3F | A | todo | GC-3F item 1 (core); live proof on a strategy id >= 10; may move to GC-3L same-day if the owner approves |
| FRESH-CLOCK | Execute gate judged freshness on the request-start clock (finding freshness-judged-on-request-start-clock) | P1 | GC-3L | A | merged #427 | a614b16, fresh-Opus PASS; proven live by the GC-3L L2/L3 prepares |
| TRIM-STRUCT | Daily list trims far strikes and trips the ADR-058/059 percentage guards (finding daily-list-trims-far-strikes-trips-truncation-guard) | P1 | GC-3F | A | todo | GC-3F item 4; ADR-058/059 change as a technical decision row |
| DB-CONNLIMIT | ofo_app rolconnlimit 5 below one API's pool (finding db-role-connection-limit-below-pool-size) | P2 | GC-3F | A | todo | GC-3F item 5 |
| OUTCOME-500 | Outcome route 500 on a 2-expiry draft (finding outcome-multi-expiry-unhandled-500) | P4 | GC-3F | B | todo | GC-3F item 6 |
| #273 | Margin check uses the platform estimate, not Zerodha's figure | - | GC-3F | A | todo | GC-3L's real replies now saved (`ofo-kite-ticks/2026-10-19/`); Zerodha margin 484.25 read at 10:24:54 |
| #255 | Never split anywhere: Complete / Retry / exit block above the freeze limit (ADR-092, OQ-2 answered 2026-10-16) | P1 | GC-3F | A | held #420 | with #63, #43 |
| #269 | Max-loss sentence vs charges (OQ-4, OQ-10) | - | owner | A | blocked-owner | OQ-4, OQ-10 |
| Q272 | Which control counts as "the owner's own account" (REQ-073 AC-5) | - | GC-3F | A | blocked-owner | GC-3L done 2026-10-19: ask now |
| #129 | Anonymous callers can lock the owner out of Kite login | - | stage-5 | A | blocked-owner | needs platform login (Google OAuth credentials) |
| #112 | Entitlement ledger index + free-day cap | - | stage-5 | A | todo | with W-008/W-009 |
| #422 | Freeze check accepts any type; Evaluation.as_of has no timezone check (PR #420 review MINORs) | P4 | GC-3F | A | deferred #422 | |
| #423 | Reconciliation store: route must derive zerodha_net_now / basket-reconciled from Kite; Q224 lock race (PR #419 MINORs) | P1 | GC-3F | A | deferred #423 | with #380-2 |
| OQ-GC2h-2 | Owner question: what lifts the block on a contract two strategies share (Q224 + Q222 leave none) | P1 | owner | A | blocked-owner | owner-questions-2026-10-19.md; needed before #380-2 |
| ADR-113 | Closing baskets checked on Zerodha's figure alone (technical decision, rides in #418) | P1 | GC-3F | A | held #418 | merges with #418 |
| ADR-094-ptr | ADR-094 gains a back-pointer to ADR-113 (PR #418 round-2 MINOR) | P4 | GC-3F | C | todo | docs |
