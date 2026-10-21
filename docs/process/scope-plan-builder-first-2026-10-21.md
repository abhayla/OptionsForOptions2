# Prioritised plan: builder and adjustment suggestions first (2026-10-21)

Status: rev 3. Rev 2 passed independent review round 1 (PASS WITH FIXES, all applied). Rev 3 applies the owner's
feedback of 2026-10-21 evening: plain step names, how a goal contract proves completeness, less effort, Sensibull
references in every item, login kept as it is. Waits for one owner approval; the freeze holds until then.
Spec basis: ADR-165 (owner scope answers 2026-10-21); ADR-030 (core first); ADR-055 (1) (no platform view on strikes or
adjustments until Q211); ADR-152 (Sensibull default and its exceptions); ADR-060 (build on the owner's Kite app);
ADR-150 (3); register rows MR-128, MR-130, MR-140.

**Core:** a strategy the user builds is tracked, and the live feed drives one adjustment detection on it with the right
numbers. **Proof:** on a market day, the owner logs in to Kite; a NIFTY iron condor is built, tracked at live prices
(REQ-109), and one Q253 detection fires from the live feed (threshold lowered for the test) with its condition and
numbers matching a hand calculation.

## Owner feedback applied (rev 3)

1. **Plain names.** Work runs as eight numbered steps with plain names (below), not codes.
2. **Login is not built now.** The app keeps today's Kite login on the owner's Kite app (ADR-060), the same pattern
   Sensibull uses (one platform-owned broker app, the user logs in at Zerodha and is sent back; multi-broker review
   ARCHITECTURE.md L2 pattern A). The owner logs in whenever a test needs live data. Google login, sign-up and
   per-user separation (REQ-012, REQ-014, REQ-016, REQ-125) move to the launch scope; new code takes the user from the
   session and never hard-codes the owner, so adding users later needs no rewrite.
3. **Sensibull reference in every item.** Each item names the Sensibull study screens it copies (`INDEX.md` screen
   numbers in `D:\Abhay\Ventures\competitors\sensibull\2026-10-21\`), and its brief carries the screenshot paths. The
   builder opens them before writing a screen, the reviewer compares the result against them, and a difference is
   either fixed or written down with its reason (ADR-152 exceptions). Screenshots and account data never enter this
   public repo.
4. **Less effort** (measured 2026-10-21: about 196 PRs merged from 2026-10-14 to 2026-10-21; an app-test run averages
   about 7 min and the kit CI about 4 min, so the cost is the NUMBER of PRs, each with its own review, rebase, CI run
   and merge gate, not the length of a run):
   - **One PR per step slice, not per item.** About 2-4 PRs per step, about 25 in total, against about 150 at the old
     rate. Example: REQ-076, REQ-077 and REQ-078 (leg rows, prices, Shift/Width/Hedge) ship as one PR.
   - **Tests grouped:** while building, only the tests of the files changed run locally; the full suites run once per
     PR in CI. No CI run for a work-in-progress push (draft branches are pushed only when the slice is ready).
   - **Reviews by risk, once per PR:** with no order path in this scope, most work is Tier B (one Sonnet review per
     PR). Tier A (fresh Opus) stays only for the engine's money numbers and the live data feed. At most 2 rounds.
   - **No parallel-lock machinery:** one step runs at a time; a second lane only for the adjustment backend from step
     6, which shares little code with the builder screens.
   - **Live checks grouped:** one owner Kite login per live window tests every item that needs live data in that
     step.
   - Size (rev 4, independent efficiency audit 2026-10-21): about 70-110 Claude agent-hours for the full scope, about
     25-30 hours of run time with four parallel lanes, 4-6 working days including two live market-day windows. The
     earlier "5-7 weeks" / "460 agent-hours" figures were wrong: they scaled an order-path week where only 10% of
     changed lines were product code (19.6k of ~194k; 87 of 196 PRs) and counted acceptance criteria, of which about
     35-40% already have code in place. Judgement, not measurement: re-stated after the first lane-day.

## Rev 4: how the work runs (efficiency audit applied; scope and quality unchanged)

- **Four parallel lanes after step 2**, each one Sonnet builder, one PR per feature cluster (about 12-16 PRs in all),
  one integrator merging:
  - Lane A, builder interaction (step 4 leg rows, Shift/Width/Hedge on the server, option chain and flows): ~20 h.
  - Lane B, summary and charts (step 4 numbers, payoff bands, OI bars, held charts switched off): ~15 h.
  - Lane C, live data, tracking and import (steps 3 and 5): ~25 h.
  - Lane D, adjustment engine and alerts (steps 6 and 7): ~30 h; the most new code and the most Tier A.
- **One verifier dispatch per PR** returning every AC block of that PR (deliver skill allows it), not one per item;
  every AC still gets its evidence file.
- **Build and prove on the recorded replay**; group every live check into two market-day windows with the owner's
  Kite login (core proof, then a final live window), instead of weekly logins.
- **Tier A only for money maths, the live feed and detection numbers**; everything else Tier B (ADR-106 item 3).
- **One docs PR per lane at its end** (tracker, handover, findings, evidence), not per item.
- **Lean briefs:** a ~2KB item brief plus a pointer to the common brief; subagents are not sent the memory index.
- The eight steps below stay as the checklist; lanes run steps 3-7 at the same time.

## The eight steps

Each step is one goal contract. Its items are the acceptance criteria (ACs) listed, each with a Sensibull screen
reference where it shows something.

**Step 1 - Clean up and switch off orders** (about 1 day; owner: none)
- Execute switched off by one production switch, refused on the server, with a test that every order route refuses
  (POST to Execute, return, basket); "Start tracking" replaces the button; REQ-109's "Trade this for real" link and any
  "acted on" path of REQ-112 stop at the same switch.
- Held PRs landed (reviewed shas kept; updated from main before the gate): #448 database pool (step 2 needs it), #466
  Option Chain selection, #457 Create Strategy guided flow, #393 My Strategies, #465 history scan, #450 CI split, #474
  worktree guard, #417 tracker check, #424 Windows pytest (review first).
- Held for step 5: #419, #451, #452 (stores the import needs). Parked with label `parked` ("order path, out of scope
  per ADR-165"), branches kept: #478, #470, #463, #456, #455, #454, #453, #421, #420, #418, #394, #459; #459 (instrument
  freshness), #455 (trading-day calendar) and #418 (Kite allow-list) are named as `Copy from:` where later steps need
  them.
- The in-scope Draft/Specified requirements move to Approved (the owner's batch approval).

**Step 2 - Prove the core live** (2-3 days; owner: one Kite login on a market day)
- Build -> Start tracking (REQ-109 AC-1/AC-2) -> one Q253 detection from the live feed -> shown in-app, numbers checked
  by hand. A failure stops the steps after it until it is fixed or re-planned.

**Step 3 - Live data the builder needs** (about 1 week; owner: one Kite login)
- Four indices (REQ-090), fresh instrument list daily (copy from #459), feed health and reconnect (REQ-114,
  REQ-133), late replies dropped (REQ-119), feed in its own process (REQ-113), data pipeline and health (REQ-048,
  REQ-049, REQ-052, REQ-050), historical storage (REQ-051), broker reads and rate limits (REQ-054 read part, REQ-117,
  REQ-118, REQ-053 read part, Kite allow-list from #418), error classes (REQ-065 after #200 is triaged).

**Step 4 - The builder, complete** (about 2-3 weeks; owner: one Kite login per week)
- Leg rows and prices: REQ-076, REQ-077, REQ-078, REQ-080.
- Numbers and charts: REQ-081 with the margin read (REQ-055 read part), REQ-083, REQ-084, REQ-085, REQ-106.
- Option chain and flows: REQ-029/030/031 remainder, REQ-087, REQ-027, REQ-028, REQ-025, REQ-026,
  REQ-024/069/068, REQ-070, REQ-034 (AC-6 per ADR-151), REQ-037, REQ-086, REQ-111, REQ-009.
- Held items built and switched off in production: REQ-079, REQ-082, REQ-091, REQ-107, REQ-105, REQ-108.

**Step 5 - Tracking and Zerodha import** (about 1 week; owner: one Kite login)
- Land #419, #451, #452. REQ-039 state machine, REQ-109 complete, REQ-077 typed fills, REQ-103 read part, REQ-104 +
  REQ-061 import, REQ-060 compare-and-block for imported strategies, REQ-089, REQ-044 read-only part.

**Step 6 - Adjustment engine** (about 2 weeks; owner: the 7 unclear video values, REQ-071)
- REQ-115 workers (never place an order), REQ-116 Notifier path, REQ-041, REQ-045 (every trigger and action, Q253,
  rule editor with defaults and per-strategy overrides), REQ-046 Opportunity panel and Before/After, REQ-047, REQ-071,
  REQ-043, REQ-112. Suggestions shown as the platform's view stay off in production until Q211 (ADR-055 (1)).

**Step 7 - Alerts and daily check** (about 3-4 days; owner: one live window)
- REQ-062 in-app + WhatsApp via the Notifier, REQ-042 alert part only, REQ-110 daily "does Zerodha agree".

**Step 8 - Your adjustment playbooks** (when the owner sends the specifics)
- Each specific becomes a default playbook (content, not new machinery), tested on the recorded replay and live.

## How a goal contract makes sure nothing is half-built or assumed

A goal contract is one `/goal` run that keeps working until its goal is met; one step = one contract. A long step
continues in the next session from the same contract: the contract file is the checklist, so a new session reads
which rows are open and carries on.

1. **Every row is an acceptance criterion**, not a feature name: "REQ-078 AC-3: Shift +1 moves every leg one strike
   step", with its Sensibull screen reference and its test.
2. **A row closes only with evidence written from an independent verifier** (a fresh agent that did not build it),
   never on the builder's word. `trace_check.py` refuses a Verified requirement whose chain or evidence is broken, and
   refuses evidence written by the builder.
3. **Rows have three end states only:** closed with evidence; parked with an issue and the reason (after two failed
   rounds); or blocked on a named owner input. "Mostly done" does not exist. A parked row is carried by name into the
   next contract and shown in every handover until it closes.
4. **No assumption:** every row's brief quotes the requirement text (`check_brief.py` fails on a quote that is not
   verbatim) and the Sensibull screens; anything the spec does not say is asked (business) or decided and written
   down (technical) before building, never guessed.
5. **The contract is DONE only when every row is closed** (or parked/blocked by name) and `tracker_check.py` agrees
   with GitHub; the close-out cannot start while a row has an allowed next step (no early close).
6. **Each session ends with a handover** (DONE / PENDING / BLOCKED / PARKED / NEXT) and a memory pointer, so the next
   session starts exactly where this one stopped.

## Out of this scope (later scopes; nothing deleted)

Order sending: REQ-036, REQ-056, REQ-058, REQ-073, REQ-100, REQ-101, REQ-102, the sending parts of REQ-053, REQ-054,
REQ-055, REQ-060, REQ-103; kill switch; market-hours gate. Login and users (launch scope): REQ-003, REQ-012, REQ-013,
REQ-014, REQ-016, REQ-125, REQ-002, hosting (MR-140). Money and plans: REQ-017-023. Other screens: REQ-008, REQ-010,
REQ-011, REQ-092, REQ-093, REQ-094, REQ-095/096, REQ-131, REQ-132, REQ-129, REQ-130, REQ-004 phone layouts. Before
outside users: REQ-063, REQ-064, REQ-074, REQ-126, REQ-127, REQ-128.

## Owner inputs and when

- Batch approval of the in-scope requirements: before step 1.
- Kite login: step 2 (market day), then about once a week in steps 3-7.
- The 7 unclear video values: step 6. Adjustment specifics: step 8.
- Hosting, Q211, display rights, data permission: before any outside user; held items stay off until cleared.
