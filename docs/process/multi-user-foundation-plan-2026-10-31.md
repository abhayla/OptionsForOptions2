# Multi-user foundation plan (2026-10-31)

Why this exists: on 2026-10-31 the owner asked how trigger checks run and whether the app holds at 1,000 / 10,000 /
50,000 users ("Sensibull is already working, right? So why need to reinvent the wheel?"), then: "create requirements
for each of them ... so that we can work on them in another session, and we do not forget them ... they must be
implemented early."

**Owner decision (2026-10-31, question tool): this work runs right after GC-ADJ2, before GC-ADJ3 and any other new
feature.** (Order, not product behaviour, so it is recorded here, not as a decision row.)

## What we found

The target shape is already the spec's, and it matches what our Sensibull study shows (their server holds the price
feed and relays it to browsers; Greeks are computed on their server and cached; each user's own broker login is used
only for that user's positions, margin and orders). The building stopped: two core items were parked on 2026-10-23
after two failed Tier A rounds each, and the run moved on to screens.

| Piece | Requirement | State on 2026-10-31 |
|---|---|---|
| One shared price stream, fanned out inside the server; browsers never reach the vendor | REQ-048 (core), AC-4 | W-059 done (one Kite stream fanned out); pipeline W-134 **PARKED #517** |
| Greeks and market figures computed once, shared by every user; load tests at 5-6k users | REQ-050 AC-1, AC-3, AC-4 | W-136 **PARKED #519** (30 of 40 cache-key parts unguarded); AC-4 deferred by ADR-053 until a vendor licence |
| Price feed in its own process, survives API deploys | REQ-113 | W-137 in review |
| Background workers for rules and alerts, rebuilt after restart, pause on stale data | REQ-115 | not started (no work item) |
| Playbook triggers checked in the background, at most once a second, no screen needed | **REQ-165 (new, approved 10-31)** | not started; GC-ADJ2 checks on screen request |
| Several API copies; nothing only in one copy's memory | **REQ-164 (new, approved 10-31)** | not started; login states in memory, cap 20 |
| No user reaches another user's data | REQ-125 (approved 10-31) | not started; fixed owner reference in code |
| Licence to share prices with many users | REQ-052, ADR-014, ADR-170 (Q210) | **business, open**: Zerodha's written answer or a vendor |

Measured facts behind it: Kite allows 3 live sockets per app key across all users (F-59), so per-user feeds stop at 3
users; Kite supplies no IV or Greeks (F-32); Zerodha grants multi-user access only after a demo of a production-ready
platform (F-31); about 1,771 NIFTY + SENSEX options for the nearest two expiries (recordings of 2026-10-15).

## Decided in the afternoon discussion (2026-10-31, ADR-220, REQ-166)

The owner asked a run of questions after the requirements were approved; the answers are recorded so they are not
lost. Product decisions are in ADR-220 and REQ-166; the rest is recorded here.

| Topic | Outcome | Where recorded |
|---|---|---|
| Server roles | Five roles, one codebase, owner's names: api, maths, user orders, liveprices, background | ADR-220 (1), REQ-164 AC-7 |
| One machine or several | One machine now; liveprices and background as their own processes; api + maths + user orders as one process with a split setting; separate as users grow, by four measured lines held for 5 trading days | ADR-220 (2), REQ-164 AC-7 |
| How often maths runs | Four speeds as admin settings, light sums in the background, a safety valve with "as of" time; same speed for every plan | ADR-220 (3), REQ-166 |
| Pricing model vs the reference | Kept (ADR-061, ADR-063, RD-080: same prices and IV as Black-76 on the forward); compare Greeks on one real NIFTY chain before the first non-owner user; theta gap above Rs 5 per lot per day goes to the owner | ADR-220 (4) |
| Vendor Greeks | Assume none; our engine computes every Greek; REQ-165 AC-4 gates a vendor's if one ever appears | ADR-220 (5) |
| Why not copy the reference product's code | Its server code is closed (the study saw only the browser); its shape is already copied (REQ-048, REQ-050, REQ-164). What it has and we lack is permission: SEBI and NSE limits on sharing live prices (F-23), 3 sockets per app key (F-59), multi-user access only after a demo (F-31) | this file, business track A |
| Browser vs server split | Same as the reference: all maths on the server, the browser displays the server's strings (ADR-008, decimal rule); broker hosts banned in the browser by an ESLint rule (ADR-012). Two gaps found, items T1 and T2 below | this file |

Correction recorded for the record: in the discussion the model was first described as "Black-Scholes, no
dividends"; that predates ADR-061 and was wrong. The current model is the parity forward with an implied dividend
yield.

## Technical items found in the discussion (no owner decision needed)

- **T1. A check that the browser does no money maths.** Today "no P&L arithmetic in the browser" is a rule in the
  briefs and in `.claude/rules/project/vue-frontend.md`, not an automated check; only broker hosts are blocked by
  ESLint. Add a frontend test or lint rule that fails on arithmetic over price, P&L or quantity fields outside the
  named drawing exceptions (chart pixels, cell colour intensity). Small; built with step 1.
- **T2. One decision rule lives in the browser.** `frontend/src/lib/guided.js` `readingFromRange` applies ADR-121's
  "more than twice the distance" rule. Check whether the server has the same rule; if it does, or when background
  suggestions need it, the browser reads the server's answer instead of keeping a copy. Unverified today; checked in
  step 1.
- **T3. Greeks comparison with the reference product** (ADR-220 (4)). Needs market hours and the owner's Kite login;
  runs during step 1's live proof, on one real NIFTY chain, before any user other than the owner.

## Order (each step opens with its core proof; at most 2 fix rounds, then park)

1. **Revive #519 (REQ-050 shared computation).** Merge main into its branch first (run discipline B1), then the
   reviewer's structural fix: build each cache key from the engine call itself.
   Core: one option's figures computed once per update and read by many strategies. Proof: 1,000 strategies on the
   same NIFTY strike, real recorded ticks, engine call count = 1 per update.
2. **Revive #517 (REQ-048 pipeline).** Same merge-first rule; the AC-5 redesign as a reply-field inventory.
   Core: one stream in, many browsers out. Proof: recorded ticks into the gateway, two browser clients get the same
   update, neither talks to Kite.
3. **Finish W-137 (REQ-113 feed process).** Core: an API restart does not close the Kite socket. Proof: restart in a
   test, socket count unchanged.
   This step names the liveprices role in the code (ADR-220 (1)).
4. **REQ-115 workers + REQ-165 playbook checks + REQ-166 speeds.** Core: a trigger fires with no browser connected.
   Proof: scenario ADJ-02 through the worker, no client, one opportunity record within a second of the price. This
   step names the background role, makes the four speeds settings and adds the safety valve. **Needs an owner
   decision first:** REQ-165 checks the playbook triggers of REQ-159, whose code lives only on the local
   `feature/adjustments` branch, and nothing goes to main without the owner's approval; so either adjustments reach
   main before step 4, or step 4 is built on that branch. Asked when step 3 closes.
5. **REQ-125 user isolation** (approved 2026-10-31). Core: user A cannot read user B's strategy. Proof: two
   real sign-ins, a guessed id returns 404.
6. **REQ-164 several copies** (approved 2026-10-31). Core: a login that starts on copy A finishes on copy B.
   Proof: two local API copies, callback on the other. This step adds the api / maths / user orders split setting
   and the daily separation-line log (REQ-164 AC-7).
7. **REQ-050 AC-4 load test**, on this PC or CI, never on the VPS (ADR-048: throughput runs in CI or not at all).
   It stays deferred by ADR-053 for the shared-feed part until step B below.

Business track, in parallel, owner only:
- A. Send Zerodha the multi-user question (Q210, ADR-170): more sockets per app, or how a platform should stream to
  many users; and the demo date (F-31). It is a permission question, not a technical one: the build of one shared
  stream is known (REQ-048); whether Zerodha and the exchange allow it for many clients is not (F-23).
- B. Vendor quotes (REQ-052): price quotes; Greeks are not expected from them (ADR-220 (5)), so asking is optional.

## When each part runs

| When | What | Who |
|---|---|---|
| Now, while GC-ADJ2 runs | Nothing in code; this record only | - |
| Any time | Business track A and B | owner |
| When GC-ADJ2 closes | Merge its result into local `feature/adjustments`; measure prepush's real memory peak; remove the old GC-ADJ1 worktrees | orchestrator |
| Next goal contract (written only after the owner approves it) | Steps 1-3 with T1, T2 and T3 | goal session |
| After step 3 | Owner decision on adjustments reaching main (step 4 above), then steps 4-6 | owner, then goal session |
| After step 6 | Step 7 load test; then the first separation-line readings | goal session |

## Owner decisions this plan waits on

- DONE 2026-10-31: REQ-164, REQ-165 and REQ-125 approved (owner: "Go with your recommendation").
- DONE 2026-10-31: server roles, one machine first, calculation speeds, pricing model kept (ADR-220, REQ-166).
- Owner said: no goal contract is written until the owner approves it.
- The two business-track items above.

## Not decided here

How many users the first launch must hold (REQ-050 AC-4 says 5-6k): a business number, asked when step 7 is planned.
