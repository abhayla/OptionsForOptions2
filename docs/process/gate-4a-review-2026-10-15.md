# Stage 4a gate review (draft, 2026-10-15 evening)

## Second re-run 2026-10-16 10:20-10:25 IST (main 48d75a7, live Kite, ofo_dev): **PASSED**
Main then carried the fixes for the first re-run's defects: D-1 (PR 300), D-2 (PR 302) and D-3 (PR 299). Evidence is in
`docs/research/gate4a-2026-10-16/rerun/`. An independent Opus checker ran it; the orchestrator re-read `d8.log`,
`outcome-1..3.json`, `repro_spot.json` and `draft-results.json`.

Strategy: an iron condor on NIFTY expiry 2026-10-19 (SELL 23350 CE, BUY 23550 CE, SELL 22950 PE, BUY 22750 PE).

- **D8 (payoff equals the ADR-008 formula on live inputs): PASS.**
  - 3 calls, 65 s apart. Each call: 27 graded cells plus 144 scenario cells, 0 mismatches (`d8.log`: "call 1/2/3
    COMPUTED True 27 0").
  - The spot moved every call: 23134.5 at 10:20:23, 23133.9 at 10:21:28, 23127.55 at 10:22:33.
  - TOTAL rows graded per ADR-076: Entry Rs 4,140.50 Cr; Current 3,477.50 / 3,484.00 / 3,412.50 Cr; entry minus
    current equals P&L (663.00 / 656.50 / 728.00).
  - Sensibull cross-check not run (no access; ADR-056 makes it a cross-check only).
- **Live data never frozen (D-1): PASS.** The release+acquire repro gave 59 frames in 60 s, 59 distinct spot
  times, all COMPUTED.
- **The saved draft reloads unchanged: PASS.** Draft 10: all 4 legs priced by the leg picker (35.60 / 11.55 / 49.00 /
  20.45), each with its capture time. `equal_screen_before_after True`, `field_diffs []`,
  `stored_equals_screen True`, `all_entries_present True`.
- **Screenshots of every state: taken** (live, stale leg, API unreachable, no draft; 1280 and 390, no sideways
  scroll). #232 items 1, 2 and 4 are gone; item 3's remainder is in issue 297.
- **No fake prices (D-3): PASS.** The far 28700 CE with last price 0 shows "no live quote" and "—", never Rs 0.00 or
  -100%.
- **Phase-0 checks (section 1): all recorded**, unchanged from 2026-10-08/15.
- **Open, not blocking** (issue 297):
  - "Contract details not available" on legs opened from a draft link;
  - the raw symbol in a duplicated notice;
  - the margin note asking for a Kite login although a session exists;
  - the Loss line drawn at 0 across the profit zone;
  - the far leg's health reads "available" while its last price is empty.
- **Next:** stage 4b (one real order -> confirmation -> reconcile). Open first: the W-080 guard redesign (issue 271)
  and the F-39 margin-rule decision.

## Re-run 2026-10-16 09:16-09:45 IST (main 640a47b, live Kite, ofo_dev): **NOT PASSED**
Evidence: `docs/research/gate4a-2026-10-16/` (verdict.md, results.json, outcome-1..3.json, repro_spot.json,
draft-results.json, shots-report.json, 10 screenshots). Run by an independent Opus checker; the frozen-spot evidence was
re-read by the orchestrator from the files.
- **D8 formulas: PASS.** 3 live calls (09:20:26, 09:21:31, 09:22:36), each 27 graded cells + 144 scenario cells, 0
  mismatches; TOTAL rows per ADR-076: Entry Rs 4,793.75 Cr; Current 4,137.25 / 4,225.00 / 4,098.25 Cr; entry minus
  current equals P&L (656.50 / 568.75 / 695.50). The grader flags the old plain-sum Current Value (11105.25 vs 4228.25).
- **Draft save -> reload -> reopen: equality PASS, gate PARTIAL** (draft 9; only 2 of 4 legs had a planned entry, D-2).
- **Screenshots: taken** (8 states at 1280 and 390). #232 items 1, 2, 4 gone; item 3 partly (no `NSE_FO:` ids; links
  show "Contract details not available"; raw symbols in the notice box).
- **Blocks the gate - D-1:** an instrument released by one socket and acquired by another stops ticking while the reply
  stays COMPUTED/live (spot 22982.45 at 09:23:39 for 26 s while legs ticked; D8's spot_at 09:20:15 in all three calls).
  Finding `live-subscription-lost-on-release-reacquire`. Fix in progress (branch fix/live-resubscribe-freeze).
- D-2 leg picker gets no price for a contract no socket holds (same path, under investigation); D-3 a last price of 0
  valued as a price (fix in progress, branch fix/zero-ltp-not-a-price); D-4 the live market reads the Kite session
  only at API start, so a login after start leaves it NOT_CONNECTED until a restart (seen at 09:18; issue filed).
- Minor: stray "estimated from spot" fragment and a duplicated notice; "Margin ... needs your Kite login" shown with a
  session; the payoff chart's Loss line drawn at 0 across the profit zone.
- **To pass:** D-1 fixed and proven live, then D8 again with a moving spot, and the draft check with all 4 legs priced.

## 2026-10-15 draft (superseded by the re-run above)

Verdict: **NOT YET PASSED.** Two gate checks were run at 11:55 IST on code that three later merges the same day
changed (#212 proxy, #211 TOTAL Cr/Dr, #216 planned entries saved), and the Save Draft screen (W-071) did not exist yet.
Those checks must be re-run on current main; the run is ready to go as soon as W-071 merges, in the next market session
with the owner's one daily Kite login.

Gate source: `docs/process/master-plan-2026-10-07.md` section 4a, "Gate". Evidence for the 11:55 run lives outside the
repo in `D:\Abhay\Ventures\ofo-kite-ticks\2026-10-15\gate4a\` (`results.json`, `shots-report.json`, 8 screenshots, draft
GETs); a copy goes into the repo with the re-run.

## 1. Every Phase-0 check recorded with pass or fail (ADR-030)
| Check | Result | Record |
|---|---|---|
| Live ticks over the WebSocket, 30 min | PASS | spec/findings.md (2026-10-08) |
| Full NIFTY and SENSEX chain rebuild | PASS (bid/ask on 216/216, 208/208, 334/336, 271-328 contracts) | spec/findings.md |
| Our Greeks against Kite's | NOT POSSIBLE (Kite has no Greeks); internal check PASS with the forward (ADR-061) | spec/findings.md |
| Stale or missing data flagged, never shown as live | PASS (feed-stale flagged 6.3 s after a forced pause, 2026-10-08 14:51); browser-side: W-065 two-holder fallback guarded (PR #235) | spec/findings.md; finding liveness-from-shared-subscribers |
| Forced reconnect | PASS (2.2 s) | spec/findings.md |
| History persisted | PASS | spec/findings.md |
| Fan-out to 100/1,000 simulated users from recorded ticks | PASS on the replay (W-059) | handover 2026-10-08 |
| Licence status | recorded (F-23, F-31) | spec/findings.md |
| Next-morning token expiry | **PENDING**: watcher running since 15:50:34 on the 11:47 token (`token-watch-2026-10-15.json`), 1-minute probes 04:00-09:00 on 2026-10-16 | to be recorded as an F-id |

## 2. Payoff equals the ADR-008 formula on live inputs (D8), Sensibull as a cross-check
- 11:55 run: 3 live calls x 38 comparisons; 36 per call matched by hand, 0 mismatches; the 2 TOTAL rows (Entry Value,
  Current Value) were recorded as "convention not defined" - ADR-076 (#211) has since defined them (net with Cr/Dr).
- Sensibull: not run (no access); ADR-056 makes it a cross-check only.
- **Re-run needed** on current main so the TOTAL rows are graded against ADR-076.

## 3. The saved draft reloads unchanged
- 11:55 run: definition equal across save / GET / GET (draft 948), but planned entry and capture time were NOT stored
  (harness finding F3) - #216 (ADR-075) fixed that afterwards, and the screen had no Save Draft action.
- **Re-run needed** through the screen once W-071 merges (its Playwright core proof is the same check in CI).

## 4. Desktop and mobile screenshots of every state (REQ-067 AC-4)
- 11:55 run: 8 screenshots (live, stale leg, API unreachable, no draft; 1280 and 390).
- They show #232: the leg picker's error (cause confirmed: the pre-#212 proxy rewrite, harness finding F2), a broken
  message fragment, raw instrument ids and ISO times. **Re-take on current main**; items 2-4 of #232 are to be decided
  in this review (recommendation: 2 blocks the gate as wrong wording on the main screen; 3-4 fixed before the 4b demo).

## Re-run plan (next market session, one owner login in a private window)
1. Token-expiry result read from the watcher; F-id recorded.
2. API from main on 8765 with `DATABASE_URL = DEV_DATABASE_URL` (ofo_dev, ADR-078); owner logs in.
3. D8 on 3 live calls incl. TOTAL rows per ADR-076; draft save -> reload -> reopen through the screen (W-071);
   8 screenshots of every state on current main.
4. Copy results + screenshots into `docs/research/gate4a-<date>/`; write the verdict here.
