# Builder sequence (top to bottom, one row at a time) - 2026-10-22

Decision: ADR-168 (owner 2026-10-22). Contract: `goal-contract-builder-sequence-2026-10-22.md`.
This file is the status table. The run edits ONE row's Status when that row closes, then prints the whole table.

Rev 2 (independent architect review 2026-10-22, verdict REVISE, all findings applied): the owner's 59-row list grew to
63 rows. Added because a listed row depends on them: REQ-117 and REQ-118 (broker reads), REQ-113 (feed process),
REQ-050 (shared computation, needed by REQ-106), REQ-052 (data sourcing, needed by REQ-105/108). Moved: REQ-089 before
REQ-138, REQ-107 before REQ-091. Removed to the later adjustments contract: REQ-037 (its AC-4 prepares and executes
adjustment orders). REQ-006 and REQ-007 became row 16 (UX levels removed, ADR-168 (4)). Row 63 is the close-out.

**Status words:** `Not started`, `In progress`, `Done`, `Done (live check pending)`, `Done (switched off: <hold>)`,
`Done (AC-x deferred: <where>)`, `Waiting on owner (<question>)`, `PARKED (#issue)`, `Superseded`. The text in
brackets after `Not started` is the starting state (2026-10-22, from the requirement files and the run-1 handover; not
re-tested).

**Chunks** (8; 6a and 6b merged by the efficiency review) are the PR / full-CI / review points. Tier: A = fresh Opus review of the chunk PR (money maths, live data,
engine-driven figures, migrations, auth/tokens); B = Sonnet review. Every row also gets its own independent verifier.

**Deferred acceptance criteria** (out of this contract's scope by ADR-165 / ADR-168 (1); the row closes as
`Done (AC-x deferred: ...)` when everything else passes):
- Order sending in REQ-053, REQ-054, REQ-055 (read parts only here) - order-path scope, not built (ADR-165).
- Order-update stream in REQ-113, REQ-114 (price socket only here; the order-update part needs REQ-060 reconciliation) - order-path scope.
- REQ-001 AC-1 BANKNIFTY/FINNIFTY part - closes at row 46 (REQ-090).
- REQ-109 AC-6 delayed-price mode - closes at row 58 (REQ-105); AC-8 alerts on paper strategies - adjustments contract.
- REQ-140 AC-3 imported-strategy part - import contract (REQ-104).
- REQ-015 AC-5 reconcile part ("validates and resynchronises": Trigger.AFTER_RECONNECT) - needs REQ-060
  reconciliation, order-path scope like REQ-113/REQ-114's order-update stream (added 2026-10-22 at row 2; the
  positions re-read after a reconnect IS built).
- REQ-107 parts that read REQ-047 adjustment data - adjustments contract.

| # | W | REQ | Name | Priority | Chunk | Tier | Status |
|---|---|---|---|---|---|---|---|
| 1 | W-129 | REQ-001 | Scope: underlyings and leg types (NIFTY/SENSEX now; BANKNIFTY/FINNIFTY at row 46) | Prerequisite | 1 | B | Done (AC-1 deferred: BANKNIFTY/FINNIFTY part, row 46; MINORs #512) |
| 2 | W-130 | REQ-015 | Zerodha connection (Kite login, reads only) | Prerequisite | 1 | A | Done (live check pending: AC-5 network drop, row 63; AC-5 reconcile part deferred: order path; AC-3 rewritten by ADR-169; MINORs #513) |
| 3 | W-131 | REQ-054 | Broker adapter, read part | Prerequisite | 1 | A | Done (AC-1 basket and reconcile parts deferred: order path; MINORs #514) |
| 4 | W-132 | REQ-117 | Broker adapter capability flags | Prerequisite | 1 | A | Done (AC-3 feature part for REQ-100/102/103 deferred: bound when built; MINORs #515) |
| 5 | W-133 | REQ-053 | Contract eligibility: daily instrument list, valid strikes and expiries (read part) | Prerequisite | 1 | A | Done (before-execution repeat: order path; MINORs #516) |
| 6 | W-134 | REQ-048 | Market-data pipeline (prices reach the server, never the browser directly) | Prerequisite | 1 | A | PARKED (#517) - AC-1..AC-4 pass; AC-5 credential scans to redesign |
| 7 | W-135 | REQ-049 | Data health: fresh, stale and missing prices labelled honestly | Prerequisite | 1 | A | Done (MINORs #518; picked up #513) |
| 8 | W-136 | REQ-050 | Shared computation (market-wide figures computed once) | Prerequisite | 1 | A | PARKED (#519) - AC-2 passes, AC-4 deferred (ADR-053); AC-1/AC-3 correct in code, 30 of 40 key parts unguarded |
| 9 | W-137 | REQ-113 | Price feed in its own process (price socket part) | Prerequisite | 1 | A | Done (AC-4 and the order-event parts deferred: order path; AC-5 two-user browser test deferred: one-user API; live restart check pending, row 63; MINORs #520) |
| 10 | W-138 | REQ-118 | Zerodha rate limits for read calls | Prerequisite | 1 | A | Not started (unmeasured) |
| 11 | W-139 | REQ-114 | Price feed health check and reconnect (price socket part) | Prerequisite | 1 | A | Not started (not built) |
| 12 | W-140 | REQ-072 | Index spot price | Prerequisite | 1 | A | Not started (verified) |
| 13 | W-141 | REQ-032 | Calculation engine | Prerequisite | 1 | A | Not started (verified) |
| 14 | W-142 | REQ-033 | Expiry and live P&L formulas | Prerequisite | 1 | A | Not started (verified) |
| 15 | W-143 | REQ-028 | Shape templates and shape matching | Prerequisite | 1 | B | Not started (built) |
| 16 | W-144 | REQ-038 | Save a strategy and load it back exactly | Prerequisite | 1 | A | Not started (verified) |
| 17 | W-145 | REQ-006 + REQ-007 | Remove UX levels: one full screen for everyone; spec rewrite first (ADR-168 (4)(5)) | P1 core | 2 | B | Not started |
| 18 | W-146 | REQ-035 | Strategy table: every leg's P&L at each level | P1 core | 2 | A | Not started (verified) |
| 19 | W-147 | REQ-080 | Leg picker: strikes with live prices, futures, depth popup | P1 core | 2 | A | Not started (basic picker only) |
| 20 | W-148 | REQ-076 | Leg rows: strike -/+, lots, multiplier, leave a leg out, shape name | P1 core | 2 | A | Not started (built on branch W-126) |
| 21 | W-149 | REQ-077 | Entry prices: typed price, Reset Prices, "price has moved" mark | P1 core | 2 | A | Not started (not built) |
| 22 | W-150 | REQ-034 | Outcome view and scenario levels | P1 core | 2 | A | Not started (mostly built) |
| 23 | W-151 | REQ-119 | An old reply never draws over a newer edit | P1 core | 2 | A | Not started (not built) |
| 24 | W-152 | REQ-133 | Old live frames dropped; a new screen waits for its first price | P1 core | 2 | A | Not started (not built) |
| 25 | W-153 | REQ-055 | Margin check, read part (Zerodha's margin for the plan) | P1 core | 3 | A | Not started (partly built) |
| 26 | W-154 | REQ-081 | Money summary: net premium, charges, margin, reward/risk | P1 core | 3 | A | Not started (partly built on branch W-127) |
| 27 | W-155 | REQ-135 | Clear all legs, days to expiry, "Prices as of" stamp, lone futures leg | P1 core | 3 | A | Not started (not built) |
| 28 | W-156 | REQ-070 | Builder history and restore | P1 core | 3 | B | Not started (server only) |
| 29 | W-157 | REQ-134 | Name a strategy, Save As, rename, saved list with search | P1 core | 3 | B | Not started (not built) |
| 30 | W-158 | REQ-078 | Shift / Width / Hedge | P2 | 4 | A | Not started (built on branch W-126) |
| 31 | W-159 | REQ-085 | Warnings and "How this trade works" | P2 | 4 | A | Not started (not built) |
| 32 | W-160 | REQ-136 | Figure definitions and the projections note | P2 | 4 | B | Not started (not built) |
| 33 | W-161 | REQ-029 | Option chain display and live data | P2 | 4 | A | Not started (partly built) |
| 34 | W-162 | REQ-030 | Pick legs from the option chain into the builder | P2 | 4 | B | Not started (partly built, PR #509) |
| 35 | W-163 | REQ-031 | Option chain live strategy preview | P2 | 4 | A | Not started (partly built, PR #509) |
| 36 | W-164 | REQ-083 | Payoff chart extras: "now" curve, hover, SD bands, OI bars | P3 | 5 | A | Not started (partly built on branch W-127) |
| 37 | W-165 | REQ-084 | What-if (level, date, IV) and the Greeks panel | P3 | 5 | A | Not started (partly built on branch W-127) |
| 38 | W-166 | REQ-137 | Payoff table and SD table | P3 | 5 | A | Not started (not built) |
| 39 | W-167 | REQ-089 | Manual P&L entries | P3 | 5 | A | Not started (not built) |
| 40 | W-168 | REQ-138 | Builder settings saved per user | P3 | 5 | A | Not started (not built) |
| 41 | W-169 | REQ-139 | Header with the day's change and OHLC | P3 | 5 | A | Not started (not built) |
| 42 | W-170 | REQ-106 | Market context strip: ATM IV, PCR, max pain, VIX | P3 | 5 | A | Not started (not built) |
| 43 | W-171 | REQ-111 | Private notes on a strategy | P3 | 6 | B | Not started (not built) |
| 44 | W-172 | REQ-086 | Share a read-only link | P3 | 6 | B | Not started (partly built) |
| 45 | W-173 | REQ-087 | Option chain display options | P3 | 6 | B | Not started (partly built, PR #509) |
| 46 | W-174 | REQ-090 | Adds BANKNIFTY and FINNIFTY (also closes REQ-001 AC-1) | P3 | 6 | A | Not started (not built) |
| 47 | W-175 | REQ-024 | Guided strategy creation (Create Strategy screen) | P3 | 6 | B | Not started (partly built) |
| 48 | W-176 | REQ-026 | Expected market range input | P3 | 6 | B | Not started (built) |
| 49 | W-177 | REQ-068 | Strategy preferences | P3 | 6 | B | Not started (built) |
| 50 | W-178 | REQ-025 | Strategy discovery and preferences | P3 | 6 | B | Not started (not built) |
| 51 | W-179 | REQ-027 | Strike selection modes (rule-placed part held, Q211) | P3 | 6 | B | Not started (not built) |
| 52 | W-180 | REQ-069 | Suggested setups (rule-placed part held, Q211) | P3 | 6 | B | Not started (not built) |
| 53 | W-181 | REQ-109 | Start tracking (paper P&L) | Tracking | 7 | A | Not started (merged; live proof pending) |
| 54 | W-182 | REQ-140 | Profit left and loss left for a tracked strategy | Tracking | 7 | A | Not started (not built) |
| 55 | W-183 | REQ-079 | Ready-made shapes and quick picks (held, Q211) | P4 held | 8 | B | Not started (built, switched off) |
| 56 | W-184 | REQ-082 | Probability of profit (held, Q211) | P4 held | 8 | A | Not started (built, switched off) |
| 57 | W-185 | REQ-052 | Market-data sourcing and licensing (needed by rows 58, 62) | P4 held | 8 | B | Not started (unmeasured) |
| 58 | W-186 | REQ-105 | Delayed prices before a Zerodha login (held; needs REQ-016 approved first) | P4 held | 8 | A | Not started (not built) |
| 59 | W-187 | REQ-051 | Historical price storage (needed by rows 60-61) | P4 held | 8 | A | Not started (not built) |
| 60 | W-188 | REQ-107 | IV and OI history charts (held, display rights) | P4 held | 8 | B | Not started (not built) |
| 61 | W-189 | REQ-091 | Strategy price history chart (held, display rights) | P4 held | 8 | B | Not started (not built) |
| 62 | W-190 | REQ-108 | Events calendar, FII/DII (held, data source) | P4 held | 8 | B | Not started (not built) |
| 63 | none (no requirement) | - | Close-out: every "live check pending" criterion proven in one live window; handover for the next contract (adjustments incl. REQ-037, alerts, import) | Close-out | 8 | - | Not started |
