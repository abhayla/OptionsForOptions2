# GC-3L contract checks (chain rule 3), 2026-10-17 ~23:45 IST

Contract: `goal-contract-GC-3L-2026-10-19.md`, written by GC-3's close-out. Two checks: a precondition check (fresh
Sonnet, read-only) and a full review (fresh Opus, read-only), because GC-3L comes before a live real-money run.

## 1. Precondition check (Sonnet) - no false claims

Every "merged / exists / prints" claim was true: #379, #382, #383, #384 merged (16:49Z-17:57Z); `scripts/live/probe.py`
subcommands and outputs (probe.py:242, 341, 376, 393-405); ADR-108 text; W-107's refusal (execute.py:322, :370);
`/broker/connected` and `/execution/returned` (routes.js:48-49); "Check with Zerodha" (ReturnCheck.vue:35);
`fetch_holdings`, `load_log`, `rates_in_force`; `dev_run.py` refuses non-ofo_dev; #338 #380 #279 #352 open; F-41, OQ-13.

Unclear items and the orchestrator's answer:
- Step 0 runtime checks unrun - REJECTED as a defect: step 0 runs them on Monday by design.
- Kite callback route not found by grep - REJECTED: `broker.py:242-247` (verified tonight for REQ-073 AC-3).
- No frontend login entry point - ACCEPTED: L1 now names the login URL on the API port (the 2026-10-16 path).
- Kite redirect -> `/execution/returned` - REJECTED: W-105's callback sends a no-state hit there (AC-3 verified).
- "Live" without OQ-13 - REJECTED: the contract saves the strategy from the builder while the feed is live.

## 2. Full review (Opus) - NOT READY: 1 CRITICAL, 4 MAJOR, 4 MINOR; all ACCEPTED and applied

1. CRITICAL - no plan for an EXIT that does not fill or is refused (an open position into Wed, #352). Applied: L3 by
   14:30; cancel at 15 min, Check, ONE new owner-confirmed EXIT by 15:10; at 15:15 the owner's L1 answer (a new
   Business-call question at L1: sell by hand on Kite as a recorded deviation, or hold to Wed with no new ENTRY).
2. MAJOR - "Open Kite's page again" re-posts the same basket (BasketForm.vue openAgain, lines 30-34): a double basket.
   Applied: the once-only rule in L2/L3.
3. MAJOR - GC-3 review finding 4 (redirect / state -> login-refusal page is not a stop; read the URL from the browser)
   was dropped. Applied: GC-3's L2 lines restored.
4. MAJOR - a probe crash (private attributes, #386 item 1) is not covered. Applied: any probe exit other than 0 at L1 =
   STOP; `--compare` right after `--save`; L4 probe failure -> screenshots, fix in the next contract.
5. MAJOR - no action for negative funds (#338). Applied: strike so premium x 65 + Rs 100 <= funds; `equity.net` < 0 at
   L3 -> the unfilled-EXIT branch.
6. MINOR - `pnl` without `--tag-prefix` counts every trade of the day. Applied: `--tag-prefix`, no trades in the
   contract today at L1.
7. MINOR - #380/#381 fell between the two triage windows. Applied: step 0.4 covers every open Tier A deferred issue not
   in GC-3's P0 6 table, naming #381 (rule 1) and #380 (ADR-108 (1)).
8. MINOR - rules 4, 7 and "one strategy" only by reference; probe commands lacked `dev_run.py`. Applied in L1-L3 and
   step 0.5.
9. MINOR - the next-contract recommendation ignored a failed run. Applied: chain rule 4 branch; #352, #381, OQ-13 named.

Re-check after the fixes: see section 3.

## 3. Re-checks (same Opus reviewer)

- Re-check 1: NOT READY - all 9 applied, but two NEW MAJORs from the edits: (a) the EXIT cancel + second EXIT
  stretched ADR-108 rule 6 ("Cancel only, on the 15-minute branch" - the ENTRY's), and a hand-sale option departed
  from ADR-002, needing SPEC CHANGE owner questions; (b) "an open position still follows the exit branch" after a STOP
  contradicts P0 rule 3 and cannot work (W-107 refuses any EXIT while drifted). MINOR: a refused EXIT has nothing to
  cancel. ACCEPTED, fixed by removing the cancel/retry and the hand-sale question entirely: an unfilled or refused EXIT
  carries over as NRML under ADR-097's existing consequence ("A test position not squared off before the close carries
  over as NRML; loss stays capped at the premium"), recorded, no further ENTRY, the next contract exits it first
  (#352); Stops say "no further order". No spec change, no new owner question.
- Re-check 2: **READY.** Two MINORs, both ACCEPTED and applied: L3 sells "the held quantity (65 unless partial)";
  `pnl_equal` applies only when flat (carry-over records both figures).
