# Session handover: GC-IC1 step 9 live day, 2026-11-04 09:03-15:5x IST

Contract: `docs/process/goal-contract-GC-IC1-2026-11-03.md` (step 9) and GC-LIVE4 section A. Branch `feature/adjustments`
in `D:\Abhay\Ventures\OptionsForOptions2-OptionsForOptions2-settings`. Previous handover:
`session-handover-2026-11-04-gcic1.md`. Full timed run log: `D:\Abhay\scratch\gclive3\run-log-1104.md`.
Nothing on main, no PR (owner rule).

## DONE (each proven by the orchestrator's own run; times IST)
| Item | Result | Proof |
|---|---|---|
| A0 preflight | Kite session 17 via the app link (the first owner login went to kite.zerodha.com directly and stored nothing); ofo_dev was at 0036 while the code needs 0038 -> migrated (owner role, additive); ofo_app CONNECTION LIMIT 5 -> API 3 + feed 1 + worker 1 | run log A0 |
| A1 | fresh paper ICs 83 (NIFTY 9 Nov, weekly), 84 (SENSEX 5 Nov, intraday), 85 (NIFTY 23 Nov, monthly), plan = system playbook 3; NIFTY's next weekly is 9 Nov, monthly 23 Nov | alert-style replies |
| A2 | 09:30-11:50: 27 records / 8 lapsed vs 103 / 75 on 2 Nov (-74 % / -89 %); worst 84 (1 day left, past breakeven) 5 records in an hour, 4 lapsed, then the intraday daily limit | a2-final-1104.txt; F-101; ADR-246 |
| A3 | dismiss #114 at 09:26:25 -> 0 new records / holds on 84 through 09:35 while still true; "worse" path NOT OBSERVED | run log A3 |
| A4 | check speed: weekly 30 s, monthly 2 min PASS; intraday 4-6 per minute vs 6 | minute lines |
| A5 | paper stop fired 8.4 s after arming while 85's alerts were in quiet time | trigger 10 / alert 6 |
| A6 | inbox, Preferences, alert-style picker at desktop and 390 px (same-origin iframe, DOM measured) PASS | run log A6 |
| Live fix 1 | routes judged the live spot against the request-start clock (5 s requests over the tunnel -> every quote "tick_in_future" -> Compare 0 of 15 approaches) -> one helper judges at one instant after the slow reads (34a329d4, review FIX FIRST -> fix round -> PASS; non-DB sweep 4328 passed 0 failed) | merge a5fed2dc; live Compare 15 of 15 at 10:48 |
| Live fix 2 | Compare chain rows carried no OI -> every live strike "OI not known" (e945b814, Tier B PASS) | merge 4b5c3228; live flags {} at 12:36 |
| Live fix 3 | the OI fix exposed a crash: 2+ legs joined into a one-token text slot -> 500 on the Compare at 12:06 (6d665132, LegRefs, Tier B PASS) | merge 7fb88e47; live Compare back 12:36 |
| #636 round 6 | independent Opus review found the real cause (rebuild held the DB lock for the whole list; the gate apply waited on it inside the loop, added by round 5); round 6 + follow-up (Tier A PASS, re-check PASS) | merges 68cf98c2, b8060763; D3 table on #636 |
| D3 | before r6: 4.6 s / 34.0 s (stall) / 1.4 s after the candle close; after r6: 1.6 s, 1.3 s, 1.6 s (one not clean: armed 45 s before); 54-56 cycles every minute, 0 lock waits | d3-1104*.log; #636 comment 6625619413 |
| Drawer at 390 px | step 8 leftover: full width, no overflow, live values | screenshot in run log |
| Carry check | not a carry day today (app function: Fri 6 beforeWeekend, Mon 9 beforeHoliday); negative check 15:05 PASS | run log |
| Owner decision | ADR-246: presets kept ("Keep presets for now"), intraday reviewed after two more expiry days; F-101 | 8c1c0384 |
| Issues | deferred #650-#654 staged S6.7 (ba38c233); comments #636, #644 (Compare 11-18 s live), #627 (T-16 margin stop never checked: background has no Kite session; 22 per minute "missing_margin") | issue links in run log |
| Strategy 82 | paper mirror of the owner's NIFTY 29 Dec IC: -6,906 (09:17) -> -7,985.25 (15:31); no trigger crossed; plan attached 09:30 (it had none) | paper book reads |

## PENDING
- Gate + push: `tests_app/test_background_worker.py` on a fresh DB (round 6 DB file) 18 passed 15:32-15:56 (20.5 min);
  then prepush --full (detached) on this commit's head -> push feature/adjustments only on TOTAL PASS. The gate result
  and the push line are recorded in `D:\Abhay\scratch\gclive3\run-log-1104.md` and the memory note
  gcic1-liveday-2026-11-04 (this file is committed before the gate so the gated head is the pushed head).
- Live carry proof: Fri 6 Nov 15:00 (beforeWeekend) or Mon 9 Nov 15:00 (beforeHoliday).
- One more clean D3 crossing on a live day (two clean on r6 today).
- Mockup "Your adjustment settings": review loop owner-set 2026-11-04 (three separate reviewers - UI developer, option-
  strategy expert, mockup expert - every tab above 9/10 from each; the link is updated only once, at the end; then the
  owner's approval). Round 1 (5 tabs): 4.0-8.8. Round 2 (7 tabs, the owner's strategy-level tabs added): 5.5-8.8.
  Round 3 built on strategy 82's real paper fills and the live chain IV smile (15:12); review round 3 next. Files:
  scratchpad mockup-review\r1..r3; briefs D:\Abhay\scratch\gcic1\brief-mockup-*.md. Screen gate (step 0c) stays shut.

## OWNER ANSWERS 2026-11-04 (question tool), this session
- Kite login: done through the app link.
- Intraday preset: "Keep presets for now" -> ADR-246.
- Mockup approval question: "[No preference]" -> treated as not approved.
- Pause: "Stay paused", then the review-loop instruction and "Run it alongside" for the close-out.
- Mockup review loop: "Three, one per skill"; post "Only the final, after >9"; strategy-level screens "Mockup now, scope
  later" (gaps vs today's app, e.g. a paged and filtered strategy list, come as proposed requirements after approval).
- Owner guidance for the reviewers (verbatim in brief-mockup-review.md): judge as an expert option trader with open
  strategies (done adjustments, available adjustments, exit all, exit some legs, add a leg, 10-15+ strategies with pages
  and filters); refer to the Sensibull study.

## OWNER ITEMS (decisions to bring, with numbers)
- T-16 / #627: the plan sheet promises "50 % of max loss or 4 % of margin, whichever comes first" but the margin half never
  runs in the background (no Kite session there). Priority call.
- Default "4 % of margin" stop: on a 1-lot NIFTY condor (margin about ₹45,000 seen live) it fires at about ₹1,800 against a
  max loss of about ₹23,900 - is that the default the owner wants?
- Entry spot is not recorded at the fill: needed for the "Entry distance" roll basis (ADR-243); planned as step 2 of the
  settings contract.

## Findings (this session)
F-101 (live alert counts); spot judged on the request-start clock (third site of the clock-read-before-the-read class:
check-clock-read-once-per-batch, freshness-judged-on-request-start-clock); Compare chain rows without OI; joined lists in
one-token slots (#654); worker DB-lock stall (#636); confirmation carried across a limit change (#653).

## Process lessons
- Start the login from the app link, never kite.zerodha.com (nothing is stored otherwise).
- Before a live day: `alembic current` on ofo_dev vs the code head; the worker failed on a missing table.
- Every process reads DB_POOL_SIZE: the worker and feed need their own (1) under the role's limit of 5.
- A probe must not arm a limit within ~45 s of the crossing it times (plan reaches the worker at its next rebuild).
- A strategy at its daily alert cap cannot produce test records: pick a strategy with cap left.

## NEXT
1. Round 3 mockup review (three fresh reviewers, 7 tabs) -> fix -> repeat until every tab is above 9 from each.
2. Fri 6 Nov / Mon 9 Nov 15:00: carry check live; one clean D3 crossing.
3. Then the "Your adjustment settings" contract (server steps may start; screens only after mockup approval).
