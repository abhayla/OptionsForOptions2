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
| Playbook triggers checked in the background, at most once a second, no screen needed | **REQ-165 (new, Draft)** | not started; GC-ADJ2 checks on screen request |
| Several API copies; nothing only in one copy's memory | **REQ-164 (new, Draft)** | not started; login states in memory, cap 20 |
| No user reaches another user's data | REQ-125 (Draft) | not started; fixed owner reference in code |
| Licence to share prices with many users | REQ-052, ADR-014, ADR-170 (Q210) | **business, open**: Zerodha's written answer or a vendor |

Measured facts behind it: Kite allows 3 live sockets per app key across all users (F-59), so per-user feeds stop at 3
users; Kite supplies no IV or Greeks (F-32); Zerodha grants multi-user access only after a demo of a production-ready
platform (F-31); about 1,771 NIFTY + SENSEX options for the nearest two expiries (recordings of 2026-10-15).

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
4. **REQ-115 workers + REQ-165 playbook checks.** Core: a trigger fires with no browser connected. Proof: scenario
   ADJ-02 through the worker, no client, one opportunity record within a second of the price.
5. **REQ-125 user isolation** (needs owner approval: Draft). Core: user A cannot read user B's strategy. Proof: two
   real sign-ins, a guessed id returns 404.
6. **REQ-164 several copies** (needs owner approval: Draft). Core: a login that starts on copy A finishes on copy B.
   Proof: two local API copies, callback on the other.
7. **REQ-050 AC-4 load test**, on this PC or CI, never on the VPS (ADR-048: throughput runs in CI or not at all).
   It stays deferred by ADR-053 for the shared-feed part until step B below.

Business track, in parallel, owner only:
- A. Send Zerodha the multi-user question (Q210, ADR-170): more sockets per app, or how a platform should stream to
  many users; and the demo date (F-31).
- B. Vendor quotes (REQ-052): include "do you supply IV and Greeks, and how are they computed" (REQ-165 AC-4).

## Owner decisions this plan waits on

- Approve REQ-164 and REQ-165 (Draft), and REQ-125 (Draft since 2026-10-21).
- The two business-track items above.

## Not decided here

How many users the first launch must hold (REQ-050 AC-4 says 5-6k): a business number, asked when step 7 is planned.
