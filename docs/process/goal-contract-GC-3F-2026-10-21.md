# Goal contract GC-3F (Wed 2026-10-21; Tue 2026-10-20 is a market holiday): the basket tag first, then the 4b fixes

Chain: `goal-chain.md` (rules, scorecard, tracker rules 8-9). Written 2026-10-19 by GC-3L's close-out from the live
results (`session-handover-2026-10-19-gc3l.md`), replacing GC-2f's `goal-contract-GC-3F-draft.md`. Rows:
`build-ahead-tracker.md`. **Checked:** chain rule 3's full fresh Opus review ran in GC-3L's close-out (2026-10-19 ~11:25
IST): GO WITH FIXES, 2 CRITICAL / 3 MAJOR / 3 MINOR, all accepted and applied in this text.
**Owner needed: once** - item 1's live proof (Kite login in a private window, typed go, Place on Kite's page). Cost of
that proof, measured on GC-3L's identical round trip: gross -22.75 + charges ~48 (entry 23.82, exit 24.43) = about
Rs 71 at today's premium; needs funds >= the entry's premium + charges (GC-3L: Rs 508 on Rs 1,000).
**Cap: lock + 7 h, never after 17:30 IST.** Live steps 09:15-15:30 IST only. Budget per item below; at budget a worker
stops and reports done / not done / next command.
**Same-day option (owner decision pending at writing time):** if the owner approves the tag fix as a same-day GC-3L
item, it lands under GC-3L and this contract starts at item 2 (item 1's live proof still runs here if GC-3L could not).

Core: every tag the product writes into a Kite basket - entry and exit, any strategy id, any plan version, any leg -
is at most 8 characters, alphanumeric, unique per order, and the reconciler decodes it back to (strategy, plan, leg).
Proof: (a) a failing test first on the real tag builder (strategy 11 version 1 leg 0 -> today's `OFS11V1L0`, 9
characters, must fail before the fix), then a property test over large ids and versions (no tag > 8, no two equal,
round-trip decode); (b) live, in market hours: a 1-lot entry and exit (NIFTY 2026-10-27 CE, the GC-3L recipe) on a
strategy with id >= 10 - Kite accepts the basket (no `tag should be max 8 characters`), Check closes entry `filled` and
exit `exited`, 0 mismatches, `probe.py pnl --tag-prefix <new prefix>` pnl_equal exit 0, `probe.py audit` chain verified.
A failed proof STOPS items 1 and 3 (both depend on tags); items 2, 4, 5, 6 continue. Record the output and re-plan.

## Item 1 - basket-tag-exceeds-publisher-limit (core, Tier A; finding `basket-tag-exceeds-publisher-limit`, ADR-054)
Measured 2026-10-19 10:19:48: strategy 11 plan 1 tag `OFS11V1L0` -> Kite basket `tag should be max 8 characters`
(InputException), nothing placed. `make_tag` (`backend/ofo/execution/basket.py:89-97`) allows 20 (the API's limit);
Kite Publisher's basket page allows 8. Today's format breaks at strategy id >= 10 or version >= 10.
- Class: every tag built for a basket (entry, exit, Retry/Complete re-baskets) for every strategy id, plan version and
  leg index; size today: any strategy id >= 10 (strategy 11 already exists on ofo_dev) or version >= 10.
- Fix (technical call; review-applied constraints, 2026-10-19):
  - **Self-decoding, never a lookup-only id** (review M1): `book_floor` (`execute_plan.py:66-80`) decodes strategy and
    plan from Zerodha's book without the database, and `probe.py:371` filters by prefix. Shape, e.g.: `Q` + strategy (4
    base-36 chars, ceiling 1,679,615) + version (2, ceiling 1,295) + leg (1, ceiling 35) = 8; above a ceiling the builder
    REFUSES, never truncates. Uppercase letters and digits only (Kite's tag case-handling is unmeasured; today's refusal
    was about length only).
  - **No ambiguity with old tags** (review C2): the new grammar's first character is not `O`, so the old and new
    patterns can never match the same string; old `OFS<s>V<v>L<i>` tags (8 chars or less exist live: `OFS9V1L0`,
    `OFS9V2L0` in Zerodha's book 2026-10-19) keep their old meaning - a test proves `parse_tag` decodes every old tag of 8
    chars or less to its old (strategy, plan, leg).
  - **Always a migration** (review C1): `0016_execution_plans.py:232` hard-codes `CHECK (tag = 'OFS' || strategy_id ||
    'V' || plan_number || 'L' || leg_index)`, so ANY new format is refused by the database. Item 1 ships migration 0019
    (down_revision 0018, its own PR) whose CHECK accepts the old OFS grammar OR the new one; existing rows stay valid. #419
    (0018) and #421 merge BEFORE item 1's migration: item 2's merges up to #419 run first, before market hours.
  - **Spec and store** (review M2): reword REQ-073 AC-2 ("at most 20 alphanumeric characters" -> the 8-character rule,
    spec-first R4, same PR); `execution_plan_store.py:211-218` rebuilds the tag with `make_tag` and requires equality -
    ofo_dev's strategy 11 plan 1 row (`OFS11V1L0`, nothing_placed) must still load. One limit, 8: the 20-character API
    path is dead code under ADR-100 (no API orders) and is removed, not kept.
- Reviewer checklist: generated tag length over the whole id range; uniqueness across strategies sharing a contract;
  exit and re-basket paths use the same builder; a refused id never yields a truncated tag; old tags still parse.
- Budget: 60 min, 120 tool calls (Tier A). Findings checked: basket-tag-exceeds-publisher-limit,
  shared-callback-treats-every-return-as-login.

## Item 2 - held PRs, in order (each: `gh pr update-branch N`, `python tools/merge_when_green.py N` foreground,
`python scripts/orchestrator/merge_audit.py`)
`lock/gc-3l` is gone once GC-3L's close-out merges, so the GC-2f/2g/2h holds lift; GC-5S's held PRs likewise merge only
after `lock/gc-3l` is gone (true from that merge) and follow this list's order where they touch the same files.
First the two PARTIAL steps from GC-2h: #421 (#352-1) last review round, then CI; #424 (#403) fresh-Opus review (a
hook change). Merge order (each once): #395 (#370 pool budget, FIRST - removes the e2e flake), #394, #393, #396, #397
(+ its ofo_dev proof), #399, #398 (W-108), #410 (W-111), #408, #419 (migration 0018, own PR), #421, #418, #420, #417,
#424. Up to #419 runs before 09:15 so item 1's migration 0019 can follow it.
**GC-5S's held PRs** share `frontend/src/router/routes.js` and `openapi.json` with #393, #397, #399, #410: THIS session
merges them, after #410, in GC-5S's item order, each with `gh pr update-branch N` first; GC-5S does not merge its own
while this contract runs.
Step 0.5 (ADR-111) does NOT apply: GC-3L ended flat (0/0 units, plan 2 exited).

## Item 3 - #380 option C (ADR-109), steps 2.2 and 2.3 (Tier A, `fix-380-draft-2026-10-18.md`)
2.2 one reconciler in both routes via `reconcile_attribution.attribute_and_compare` (T3), triggers as reads (T4),
shorts-first exit baskets (#389, T8), expired legs via settlement (T6), #423 (the route derives Zerodha's net). Needs the
owner's OQ-GC2h-2 answer first; without it, 2.2 parks and 2.3 is skipped. 2.3 partial actions (ADR-109 (3)), the
3-action reconcile screen (ADR-109 (4)), the rejection reason (T9); #390 if it fits. Real-data proof: the GC-3L replies
in `ofo-kite-ticks/2026-10-19/replies-after-exit` (plan 1 filled, plan 2 exited, 0 mismatches).

## Item 4 - far-strike trim judged structurally (Tier A; finding `daily-list-trims-far-strikes-trips-truncation-guard`)
Measured 2026-10-19: the daily list refused by ADR-058 (2179 of 4064, 53.6%) and ADR-059 (262 of 470 for 2026-10-19);
the stale list then made the Execute gate refuse every order; one forced update (added=210 seen=4714
newly_unlisted=2683 retired=396 delisted=2287) unblocked it. ADD a structural truncation test as a SECOND pass that
may accept a list the percentage guards refuse: near-the-money band intact per expiry, index rows and every segment
present, every dropped strike far from spot, none held by an open position or strategy leg; cross-check NSE's contract
file when it loads. ADR-058/059 stay in force (review: ADR-058 itself changed the owner's Q244 rule and was marked
"SPEC CHANGE for the owner's review", so this is not a pure technical row). The new ADR is labelled SPEC CHANGE, quotes
Q244 and ADR-058/059, records the owner's 2026-10-19 data-issue delegation, and is shown to the owner as information.
REMOVING the percentage guards outright is a business call: ask it as one question (owner rule 2026-10-19 on
conflicting business requirements), never decide it here. Failing test first on the real 2026-10-19 list.
Budget: 60 min, 120 tool calls.

## Item 5 - ofo_app connection limit vs pool (Tier A: DB role; finding `db-role-connection-limit-below-pool-size`)
`ofo_app` rolconnlimit 5; one API's pool can reach 15; PR #427's e2e first failed 4/4 with TooManyConnectionsError.
Held PR #395 already changes `db.py`, `config.py`, `app-tests.yml` and adds `test_db_pool_budget.py` (review M3); the role
is created with `CONNECTION LIMIT 5` in `app-tests.yml:121/232/425`, not by a migration, and that PostgreSQL also serves
IPODhan production. So: check #395 covers the class (pool max + overflow per process <= rolconnlimit, CI's two API
processes counted), and ADD only a startup check that logs loudly when the pool max exceeds the role's rolconnlimit.
Pool settings only; no migration or role change. Budget: 30 min, 60 tool calls.

## Item 6 - outcome multi-expiry 500 -> catalogue error (Tier B; finding `outcome-multi-expiry-unhandled-500`)
POST /api/strategies/outcome on a 2-expiry draft raised MultiExpiryError -> 500. Map it (and any typed domain error the
route raises) to a catalogue error with a user message; test posts a two-expiry draft and asserts status + message.
Budget: 30 min, 60 tool calls.

## Item 7 - W-111 part 2 (P&L/risk on Positions) - only after #400 decides where those figures come from; else carried.

## Stops
Item 1's core proof fails; a Tier A item red after 2 review rounds (park with an issue, chain rule 4); OQ-GC2h-2
unanswered (item 3 step 2.2 parks); a live step outside 09:15-15:30 IST.

## Carried, not in GC-3F
#400 (ADR-008, GC-3G), #401 (Disconnect CSRF, Stage 5), #402 (wording), #404 (evidence passes), Q272 (account-only
control - ask now that GC-3L is done), F-41's return shape on Finish (unmeasured; Finish is an owner-only click).
