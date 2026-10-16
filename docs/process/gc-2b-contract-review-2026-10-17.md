# GC-2b contract: independent review record (chain rule 3)

Reviewer: fresh Opus agent, read-only (Explore type), not the author; run 2026-10-17 ~01:20 IST on main at 6ba9194
(the third review; reviews 1 and 2 are summarised in `session-handover-2026-10-17-gc2a.md`, item 8). Raw output below,
verbatim, then the orchestrator's decision on each finding.

## Reviewer output (verbatim)

1. MAJOR - The core proof cannot run in CI from the files the contract tells step 1 to copy. Item 1 says the contract
key comes "from the catalogue" (line 52), but step 1 copies only the six reply files (lines 25-28). The repo's
catalogue slice has 0 rows for this contract (line 73). `proof.py` gets the contract from the recorder's
`instruments.json` (proof.py:64, RESULT.md:61), and that file sits outside git. Fix: also copy a slice of
`instruments.json` holding token 12080386 into the fixtures, with a header naming its source. - goal-contract:25-28,52,73; proof.py:27,64

2. MAJOR - The time plan only fits the cap at the low end. After both give-way parks, items 1 + 2 + tail = 2-2.5 +
1.5-2 + 1.5 = 5.0-6.0 h. At the top estimate that is exactly 6 h, with no room for a second review round. Item 5b's
trigger ("before item 2 if a verifier will run") is ambiguous. Tier A delivery runs a verifier, and so does item 5, so
5b looks always triggered while also being second in the park order. Say plainly whether 5b runs by default. - goal-contract:9-12,93-94

3. MINOR - "`order_timestamp` is time-only" is true only for trades. In the orders replies it is a full datetime
("2026-10-16 12:20:50"). A fresh session could wrongly apply the rule to orders. - goal-contract:53-54; orders-151006.json order_timestamp

4. MINOR - Kite's flat row reports `unrealised -130` with `realised 0`. Line 20 asks the test to name the field it
compares, but does not warn that "realised" is 0 on this row. A builder could assert realised = -130 and fail. - positions-151006.json

5. MINOR - Line 20 has literal backslash-escaped quotes (\"-130.00\"). It also cites the card's "-130.00", while the
card's own text says "-130.0". - goal-contract:20; W-091.md:23,37

6. MINOR - goal-chain.md:15 still says "8-hour cap". The contract overrides it explicitly (line 5), so this is
acceptable as is. - goal-chain.md:15

Checks that passed: trade ids 4484194 and 5966618, 65 units and NIFTY26O1923650CE match the trades files; `pnl -130`
matches positions-151006.json; `instruments.json` has 1,293 rows and contains the contract; "DA1707" appears only in
the two orders files; DB access only through fixtures (tests_app/conftest.py:66-71); nothing needs the owner except
through the owner-questions file.

Verdict: READY WITH CHANGES

## Decisions (orchestrator)

| # | Decision | Applied as |
|---|---|---|
| 1 MAJOR | ACCEPTED | Step 1 also copies the `instruments.json` row(s) for the contract (token 12080386) into the fixtures, header naming the source. |
| 2 MAJOR | ACCEPTED | 5b runs by default only as its workaround (delete a stale snapshot after confirming no verifier runs); its FIX is optional and second to park. With items 3/4/5 parked, items 1 + 2 + tail fit at the low and middle estimates; at the top estimate item 2 parks after its decision row and core test, named in the handover. |
| 3 MINOR | ACCEPTED | "time-only" scoped to the TRADES reply; the orders reply's `order_timestamp` is a full datetime. |
| 4 MINOR | ACCEPTED | The test compares Kite's `unrealised` (-130) on the flat row; `realised` is 0 there - never assert realised = -130. |
| 5 MINOR | ACCEPTED | Escaped quotes removed; the card's text cited as written ("-130.0"). |
| 6 MINOR | REJECTED | `goal-chain.md`'s prompt block must stay word-for-word the /goal text (chain rule 2); the contract's line 5 already says its 6 h cap governs. The reviewer marked it acceptable as is. |
