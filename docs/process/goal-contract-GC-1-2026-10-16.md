# Goal contract GC-1 (2026-10-16 night): Stage 4a close-out + the 4b core proof

Chain: `goal-chain.md` (rules, process rules 1-8, scorecard). Owner-approved 2026-10-16 19:30 IST. Owner needed: **no**
(fully offline; no Kite login). **Cap: 8 h wall-clock**; at the cap, unfinished items are parked and named, then
item 9 still runs.

Core: every 4a acceptance criterion and every row the coverage register places in 4a is either proven (code + test +
evidence) or named with its status and owner.
Proof: the audit table `docs/process/4a-closeout-audit-2026-10-16.md`, each "built" row citing file:line + test +
evidence path.

## Why
The 4a gate PASSED live on 2026-10-16 10:25 (`gate-4a-review-2026-10-15.md`), but only REQ-032/033/072 are Verified,
REQ-065 is Testing (open exception allowed by ADR-074), and 15 4a requirements are still "Approved", never checked AC
by AC. #159 shows a 404 after every good Zerodha login. The coverage register was generated 2026-10-10 and lists 5
closed issues. Separately, Thursday's real order was placed through a basket built outside the app, so the 4b chain
(read-back, reconcile) has never run on real Kite responses; item 8 proves it offline before GC-2b is designed.

## Done list (items 2-7 run in parallel where independent)

1. **4a audit (read-only).** Three read-only agents (Sonnet, `Budget: 20 min wall-clock, 40 tool calls`, about 5
   requirements each) over REQ-001, REQ-015 (AC-4..9), REQ-028, REQ-034, REQ-035, REQ-038, REQ-048, REQ-049, REQ-051
   (AC-1..5), REQ-052, REQ-053, REQ-054 AC-1 (authenticate, margin), REQ-063 (AC-1/2/3/5), REQ-064, the index-spot AC
   (REQ-072), REQ-065 (open exception, ADR-074) and REQ-047 AC-4 (status Specified: flag only, not buildable).
   Plus one status row each for the other rows the coverage register places in 4a:
   - build-plan rows P3a, P3b, P4, token-auto-refresh-rule, vps-test-db-credentials, safety-net-wording,
     rotate-algochanakya-secrets (an owner action);
   - findings F-21, F-23, F-29, F-30, F-33;
   - open issues #30, #129, #148, #154, #191, #199, #200, #297.

   Output: `docs/process/4a-closeout-audit-2026-10-16.md`. The orchestrator re-checks every NOT BUILT row and one
   BUILT row per requirement against the source before accepting (a worker's report is a claim).
2. **Verify the built ACs** through the `deliver` verifier (fresh context, read-only) -> evidence files written by
   the orchestrator -> the requirement goes to Verified where every AC passes; `trace_check.py` green.
3. **Build the gaps** through `deliver` (tier by blast radius), only those whose behaviour the spec already settles.
   A gap that changes what a user sees beyond the spec, or that would need a named exception (a decision row, class
   3), is NOT decided here: it goes to `docs/process/owner-questions-<date>.md` with a recommendation and the run
   continues. A gap larger than about 2 h becomes a work item placed in a named later contract in `goal-chain.md`.
4. **#159, Tier A (auth callback):** the frontend serves `/broker/connected` (plain confirmation + a link to the
   Strategy Builder) and the failure path shows the catalogue message; Playwright drives both states, desktop and
   mobile; Opus review.
5. **#126, Tier B:** the catalogue delist limit and refusal alert wired into the daily load job per ADR-058; any part
   that needs the Notifier is deferred to GC-5 with a note.
6. **#232:** no new screenshots. Close it from the gate evidence (`gate-4a-review-2026-10-15.md`, 2026-10-16 re-run:
   items 1, 2 and 4 are gone; item 3's remainder is tracked in #297) with `gh issue close` and that comment. #297 stays
   open.
7. **Bookkeeping (in the contract's one docs PR):** regenerate the coverage register; the W-075 card to its real state
   (its code merged in #311); the W-017 card's blocker corrected (class 1 card defect: real Kite responses exist since
   2026-10-16, ADR-060 replaced the wait for Zerodha); release the superseded worktree with
   `agentwt.py aaaebf66eb2e8d59e release` (`land/W-080..build/W-080-kite-basket` is empty), proving the main
   checkout's tracked-file and installed-package counts unchanged.
8. **4b core proof (throwaway script, outside deliver)** on `D:/Abhay/Ventures/ofo-kite-ticks/2026-10-16/real-order/`
   (orders/trades/positions at 122104 = after entry, 151006 = after exit), through the existing fill ledger (REQ-057)
   and reconcile (REQ-060):
   - **Known up front:** the flat row is `{'quantity': 0, 'average_price': 0, 'last_price': '3.1'}`;
     `backend/ofo/reconciliation/positions.py:44` refuses an average price of 0 and `positions.py:49-54` refuses
     strings. Record a finding the same turn: a flat row = quantity 0 with no average price; name the boundary
     conversion (`Decimal(str(v))`). Strings in the recording do NOT prove how live floats are parsed; the finding says
     so.
   - **Scaffolding, named as such:** symbol -> contract mapping from `2026-10-16/instruments.json` (`compare()` keys
     on underlying / Instrument / strike / expiry; #115); IST attached to Kite's naive times; a test-only strategy,
     version and Order for `OrderBook.apply_fill`, because the real order was placed outside the app.
   - **Expected:** no mismatch after entry (65 long NIFTY26O1923650CE) and after exit (flat); gross P&L =
     (3.10 - 5.10) x 65 = -130.00 exact Decimal. No charges re-check: charges already match except stamp (F-35); the
     stamp check against the contract note stays an owner item.
   - Output under `docs/research/core-proof-4b-2026-10-16/`. The result decides GC-2b's shape.
9. **Write GC-2a** from the results, get it independently reviewed, mark it NEXT in `goal-chain.md` and this row DONE
   or PARTIAL, merge with the handover, then print the prompt, a 5-line summary and the scorecard.

## Stops
- No Kite login is needed. DB steps run through `scripts/orchestrator/dev_run.py` / `db_run.py` (ofo_dev for
  live-style runs, ofo_test for tests). **Tunnel down = stop that item, park it, continue the offline items.**
- Owner away: no questions. Class-3 items and user-visible choices go to the owner-questions file.
- Park rule: two failed rounds or an outside blocker -> a `parked` issue (filed with `gh_issue.py --stage`), named in
  the handover, move on.
