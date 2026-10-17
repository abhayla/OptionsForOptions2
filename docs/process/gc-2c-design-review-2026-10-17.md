# GC-2c items 1-2: independent design review record

Reviewer: fresh Opus agent, read-only (Explore type), not the author; run 2026-10-17 ~06:35 IST on the orchestrator's
design note (D1-D6: plan number from Zerodha's book, plans in memory, Execute route, return route, split). Raw output
below, verbatim, then the orchestrator's decision on each finding. The design that was built is ADR-105 and the
briefs `brief-W-093.md`, `brief-W-094.md`, `brief-W-095.md`.

## Reviewer output (verbatim)

**Verdict: UNSOUND as written.** I found 2 CRITICAL problems (each can put a duplicate order on the account) and 5 MAJOR ones (wrong state, or a spec contradiction). Every attack below is worked out by hand from the code; I ran nothing.

**Answers to Q1-Q4**
- **Q1 (D2, plan number minted from today's Kite book):** not safe. It has no lock and no "one plan at a time" rule (findings 1, 2). The OFS1 vs OFS12 worry does not apply: `parse_tag` matches the whole tag, so `OFS12V1L0` decodes as strategy 12 (basket.py:58, :104). A plan left open past the trading day is finding 8.
- **Q2 (Execute press = confirm):** this does not contradict ADR-019 Q191 ("active only after confirmed execution + reconciliation", ADR-019.md:54). It is not a SPEC CHANGE, but finding 4 must be fixed.
- **Q3 (is D3(a) enough after a restart?):** no; see findings 2 and 7.
- **Q4 (the W-093..W-095 split):** finding 9.

**Findings**

1. **CRITICAL: two EXIT presses produce two live exit baskets.** Sequence: the user presses EXIT twice, or once in each of two tabs. Both requests read an empty Kite book, so both mint V2 and both build basket `OFS1V2L0`. EXIT creates no domain version, so the record refuses nothing. The reduce-only check compares against `active_legs`, which is unchanged, and ignores orders already in flight (context.py:25-27). If the user places both, the buy-back runs twice and leaves a new long position. A sequential re-press mints V3, with the same result. **Fix:** allow one plan in flight per strategy (the same idea as partial.py's one-live-preparation rule OD-h, :40), checked and minted under a per-strategy lock with no await between check and mint (finding `state-read-after-await`). Refuse a new plan while today's book holds any open order tagged for this strategy.

2. **CRITICAL: D3(a) checks positions but not open orders.** Sequence: ENTRY V1 is placed as LIMIT orders that rest unfilled. The app restarts. Positions are flat, so D3(a) passes. The user presses ENTRY again, the mint gives V2, and both baskets later fill: a double entry. **Fix:** the restart guard also blocks when today's book has any non-terminal order whose tag decodes to this strategy.

3. **MAJOR: `assess()` cannot handle a closed basket or an exit the way D5 claims.**
   - Basket orders the book never registered are flagged as unknown orders (partial.py:234-235).
   - Registered orders are flagged as missing once the 60-second grace window passes (partial.py:257-259; OD-i, :42). A user who closes the Kite page therefore gets RECONCILIATION_REQUIRED, not the partial state REQ-073 AC-3 asks for.
   - For an EXIT, a held line of -75 against a planned BUY is a wrong-side mismatch (partial.py:275-278). A finished exit (held 0) counts as fully "remaining" (:375-376), so it reads NOT_EXECUTED.
   - **Fix:** an assessment shaped for exits (target = active position minus the exit), plus a grace rule written for the basket hand-off.

4. **MAJOR: a proposal can get stuck pending forever.** ENTRY runs propose then confirm. If the user closes the Kite page, or a gate fails after propose, `_refuse_while_blocked` refuses every later propose or edit (versions.py:826-831), and nothing withdraws the proposal. **Fix:** build the basket first, then propose+confirm. Add an explicit path that closes the proposal (an `apply_result` FAILED when nothing was placed, decided from a fresh read). Use the plan number as the attempt identity the `fill-not-exactly-once` note calls for (findings JSON:22).

5. **MAJOR: dropping orders whose plan is not "in flight" loses real fills.** D5 keeps only orders whose tag matches a plan in flight. Once a re-press replaces the plan, the old basket's fills are discarded. That is the W-041 X1 case (fill-not-exactly-once.json:54). It also conflicts with ADR-050 4(d), "record orders placed outside the platform as external, never drop them" (ADR-050.md:51). **Fix:** treat every tag for this strategy minted today as live until it reaches a terminal state.

6. **MAJOR: Zerodha's net position is account-wide, not per strategy.** Three wrong states follow:
   - D3(a) blocks an entry whenever another strategy or a standalone position holds the same contract. REQ-060 AC-7 says "standalone ... are not mismatches" (REQ-060.md:33).
   - D5's "Zerodha's net is flat" never becomes true, so the strategy never exits.
   - `apply_result` given the account-wide net returns MISMATCH, which sticks (versions.py:805-808).
   - **Fix:** go through reconciliation `record_report` / `mark_exited_broker_flat`, which handles shared contracts (resolution.py:118, :231, :371), not `mark_exited` directly.

7. **MAJOR: SPEC CHANGE, unlabelled.** ADR-050 4(b) says "persist the order intent before sending" (ADR-050.md:49). ADR-054 applies item 4 to the basket path (ADR-054.md:8). D3 keeps plans in memory only. After any restart, an open strategy can no longer be exited from the platform. **Fix:** persist the plan counter and the plan intent (one small table), or label the departure SPEC CHANGE and ask the owner.

8. **MINOR: a plan open at the end of the day can block a strategy for good.** If the user returns the next day, GET /orders and trades are empty while positions exist, so the ledger and Zerodha disagree and the strategy stays blocked. Separately, tag numbering restarts after a restart, so `OFS1V1` can name two different plans on two days. **Fix:** close plans at market close with a final read; a persisted counter (finding 7) fixes the reuse.

9. **MINOR: the split.** An exit order's book `version_id` (`v1`) and its tag (`V2`) are two numbering systems on one order (model.py:186, :455-457). This must be written down explicitly. The core proof (matching by tag) sits in the last item, W-095. Core-first wants it as step 1: replay the real reply file `orders-151006.json` through parse_tag and the matcher inside W-093. W-093 changes the order-safety allow-list, so it is Tier A.

| Claim | Evidence (read this session) |
|---|---|
| Exit gate ignores orders in flight | context.py:25-27 |
| Grace window and unknown-order mismatches | partial.py:42, 234-235, 257-259 |
| assess is shaped for entries only | partial.py:275-278, 375-376 |
| Pending proposal blocks further proposals | versions.py:826-831 |
| Spec requires intent persisted and external orders kept | ADR-050.md:49-51; ADR-054.md:8 |
| Standalone positions are not mismatches | REQ-060.md:33 |
| Tag decoding is exact | basket.py:58, 104 |
| Kite tag survives a modify in Kite | unverified |

Verdict: UNSOUND

## Decisions (orchestrator)

| # | Decision | Applied as |
|---|---|---|
| 1 CRITICAL | ACCEPTED | One open plan per strategy, enforced by a partial unique index; the number is minted under the strategy row lock held to commit (W-094); Execute also refuses while Zerodha's book holds a non-terminal order tagged for the strategy, an unknown status word counting as non-terminal (W-095). ADR-105. |
| 2 CRITICAL | ACCEPTED | Plans are persisted (W-094), so a restart loses nothing; the open-order check of 1 covers resting LIMIT orders after a restart. |
| 3 MAJOR | ACCEPTED | The return route (W-096) gets its own hand-off classification for a closed or partly placed basket and for exits; `assess()` is not reused as is. |
| 4 MAJOR | ACCEPTED | The Execute route (W-095) never touches the in-memory record; the return route proposes/applies only from a fresh Zerodha read, with an explicit "nothing placed" close path (plan closed `nothing_placed`). |
| 5 MAJOR | ACCEPTED | Every stored plan's tags are matched until terminal; an order tagged for the strategy with no stored plan is recorded as external, never dropped (W-096). |
| 6 MAJOR | ACCEPTED | Reconciliation by strategy through `resolution.py` (`record_report` / `mark_exited_broker_flat`), never account-wide net into `apply_result` / `mark_exited` (W-096). W-095's reconciliation block also goes through the reconciliation module. |
| 7 MAJOR | ACCEPTED | No departure: the plan counter and intent are stored (migration 0016, W-094) before the basket is returned (W-095). |
| 8 MINOR | PARTLY ACCEPTED | Tag reuse is fixed by the stored counter and a UNIQUE tag column. The close-of-day read is a deferred issue. |
| 9 MINOR | ACCEPTED | ADR-105 records the two numbering systems; W-093's core test also asserts `parse_tag` on the real OFS1V1L0 / OFS1V2L0 rows. |
