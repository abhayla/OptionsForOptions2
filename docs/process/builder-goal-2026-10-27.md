# Builder goal: owner answers (2026-10-27)

Owner, ~09:35 IST: "make sure you are focused towards making the strategy builder screen fully functional, similar UI
as Sensibull and obviously option chain screen will also be important for the strategy builder screen to be fully
functional ... Do not deviate from it." Scope and process answers live here (project spec-first R4: a decision row only
for what the product does); each is written the turn it is given.

| # | Question | Answer | Recorded |
|---|---|---|---|
| Q1 | What counts as done for this goal? | **Gap list + live walk**: every builder, strike-drawer and option-chain region in `docs/design/ui-study-2026-10-26.md` (UI-100..UI-214) checked on the running screen against the Sensibull screenshot and matching; every builder/chain requirement (rows 33-38, 40-42, the #582 and #583 fixes) built and walked live; edits within REQ-078 AC-1's 95th percentile of 1,000 ms. | 2026-10-27 |
| Q2 | Sensibull features the spec lacks (UI study section d: Easy Options 080-083, Strategy Wizard 070-075, Draft Portfolios 084-092 / 220-224, stock underlyings 240-249): join this goal? | Owner, verbatim: **"Yes everything same as Sesibull and our requirement will be additional"**. Recommendation was "none now"; the owner chose all. This is a SPEC CHANGE to ADR-193 (1) ("Sensibull screens for features the spec does not have ... are NOT built under this decision"). Open before it becomes a decision row: how far "everything" reaches (Q2a), and two clashes the owner must settle (Q2b Strategy Wizard vs ADR-003; Q2c stock underlyings vs REQ-001 / REQ-090). | 2026-10-27, pending Q2a-Q2c |
| Q2a | How far does "everything" reach for this goal? | **Builder + chain related**: every Sensibull feature that lives in or feeds the builder and option chain (Easy Options 080-083, Strategy Wizard 070-075, Draft Portfolios 084-092 / 220-224, stock underlyings 240-249, OI pages 140-144 / 214, IV chart 151, options/straddle charts 146-147). Other Sensibull screens (screener, FII/DII, calendars, watchlist, plans) are a later goal. Order placing stays out (ADR-165). | 2026-10-27 |
| Q2b | Strategy Wizard / Easy Options vs ADR-003 | **Not asked: settled by the spec.** REQ-025 (Strategy discovery, Approved) is the spec's version of both: AC-2 "Results are shown as 'Strategies you could consider', never as the trade to take", AC-3 preferences order results; ADR-193 (2) keeps "our own decision-support wording (ADR-003)"; the owner's Q2 answer says our requirements are "additional". So both are built with Sensibull's inputs, filters and columns, in ADR-003 / REQ-025 wording, never "Most Profitable" or "Choose this". Correction: UI study section d listed both as "none" for spec status; REQ-025 covers them. | 2026-10-27 |
| Q2c | Stock options (Sensibull 240-249, "any F&O stock by search") vs ADR-157 "Stock options ... are not in scope" | **Indices only, no stocks**: ADR-157, REQ-001 AC-1 and REQ-090 AC-1 stand unchanged; stock options are not planned. The four approved indices (NIFTY, BANKNIFTY, FINNIFTY, SENSEX; row 46) are in this goal, because Sensibull's builder and chain offer all four (Q2 / Q2a). Recommendation was "indices now, stocks next". | 2026-10-27 |
| Q3 | Option chain: full Sensibull layout? | **Not asked: settled** by Q2 / Q2a ("same as Sensibull", builder and chain related) and ADR-193 (1): the chain gets the Sensibull layout (UI study b.3, UI-210..UI-214) in this goal, with rows 33-35. | 2026-10-27 |
| Q4 | When does the owner review? | **Not asked: settled** by the owner's standing rule (memory plan-review-then-approval): the gap list is the plan; independent review; one owner approval; then build first, check once at the end. | 2026-10-27 |

## Include / exclude for this phase (owner, ~10:20 IST: "It is focused only on strategy builder. Ask me questions what to include and exclude")

| # | Question | Answer | Recorded |
|---|---|---|---|
| P1 | Option Chain SCREEN in this phase, or only the builder's strike drawer and its link? | **Chain screen too**: rows 33-35 and the Sensibull chain layout (UI-210..UI-214) are in this phase (ADR-196 stands). Recommendation was "drawer + link only". | 2026-10-27 |
| P2 | Separate Sensibull screens that feed the builder (Strategy Wizard 070-075, Easy Options 080-087, Draft Portfolios 084-092 / 220-224, OI pages 140-144 / 214, IV chart 151, options/straddle charts 146-147): in this phase? | **None this phase**: all four groups move to the next phase, order chosen then. This phase = builder screen + strike drawer + option chain. ADR-196 (1) amended the same turn. | 2026-10-27 |
| P3 | Sensibull's "Add Booked P&L" toggle (catalogue line 46, setting screen 025) = row 39, REQ-089: in this phase? | **In this phase**: row 39 is built (a typed booked amount with a note, on its own labelled line, added to the payoff). Recommendation was "out, comes with real fills". ADR-196 (4) amended. | 2026-10-27 |
| P4 | BANKNIFTY and FINNIFTY in the builder and chain this phase (row 46, REQ-090 AC-1, REQ-001 AC-1)? | **All four in**: row 46 is built in this phase (values from the exchange files; a weekly-only shape refused on a monthly-only underlying). Already Approved in the spec: no spec change. | 2026-10-27 |
| P5 | Sensibull's builder price chart with OI profile (screen 027; REQ-107, held for display rights): in this phase? | **Placeholder now**: the builder shows Sensibull's chart button and a "Coming soon: price chart" card (UI-021); the chart and the IV percentile figure are built after the owner confirms display rights and the chart licence. ADR-196 (4) amended. | 2026-10-27 |

| P6 | CORRECTION of P3: P3's question named "Add Booked P&L" but described Sensibull's typed "Manual P/L" (screens 010, 112-114, 242; REQ-089). Sensibull's real "Add Booked P&L" (screen 012) is a chart toggle adding the P&L of CLOSED legs of a tracked strategy. In this phase? | **Out this phase**: comes with tracking / positions. P3's "in" stands for the typed Manual P/L (REQ-089, row 39). | 2026-10-27 |

| P7 | Share (Sensibull "..." > Share > social networks / Copy Link; REQ-086, row 44): in this phase? | **Out this phase**: waits for sign-in (multi-user) and a compliance check of public posting. The "..." menu gets Save / Save As / Rename working (REQ-134) in this phase. | 2026-10-27 |

| P8 | Builder Positions tab: list the user's Zerodha positions and load ticked legs into the builder (Sensibull catalogue line 122; REQ-104, REQ-044, REQ-061)? | **In, read-only**: REQ-104 import + grouping into a strategy + load into the builder, never attached without the user, no orders (ADR-165). New builder-sequence rows needed (about 2-3). ADR-196 (4) amended. | 2026-10-27 |
| P9 | The builder's 4th bottom tab (Sensibull "Drafts"; ours "Tracked", REQ-109 row 53; row 54 REQ-140 profit/loss left) | **Keep Tracked, prove it**: the Tracked tab stays; row 53's live proof runs in this phase; row 54 comes with tracking / positions later. | 2026-10-27 |

| P10 | P8 "Positions tab, read-only" clashes with REQ-104 AC-2/AC-3 (attach to a strategy, "reconciled at once (REQ-060)"; REQ-104 blocked behind REQ-061) - how does the tab work this phase? | **Analyse only**: list Zerodha positions; ticked ones load into the builder as a draft to analyse, entered at Zerodha's average price; nothing attached or saved as an app strategy, no reconciliation. REQ-104 attach/grouping and REQ-060/061 come with the orders phase. Needs a short new requirement first. ADR-196 (4) amended. | 2026-10-27 |

| P11 | #583 I-5: after hours, may a new leg take its entry from the last close (Sensibull does)? | **"Same as sensibull"**: entries from the last close and every number (At Expiry, Estimated Now, Greeks, IV) from closing prices, under the ADR-177 banner with the close labelled. SPEC CHANGE to REQ-077 AC-9, written as ADR-197. Recommendation was "last close, labelled; Estimated Now and Greeks unavailable". | 2026-10-27 |

Applied without a question (settled): POP (REQ-082) and ready-made shapes (REQ-079) are held by Q211, which the owner
decided on 2026-09-29 is "not a blocker for building": built and shown in development, switched on in production after
the compliance review. The Strategy chart (REQ-091, held for display rights) follows P5: a placeholder card.

Not asked, settled by the spec or this morning's list: the strike drawer's Straddles / Strangles tabs (UI-201, REQ-079
quick picks) are in; the builder info panel (rows 41-42, REQ-139 / REQ-106) is in; India VIX under REQ-106 needs
REQ-072 AC-1's "two index rows" wording extended (a spec wording fix, done with row 42).

## The goal, as understood (>95%)
Make the Strategy Builder, its strike drawer and the Option Chain fully functional and laid out like Sensibull: every
Sensibull feature that lives in or feeds those screens, plus our own requirements on top, in our brand and ADR-003
wording; the four indices, no stocks, no order placing (ADR-165). Done = the gap list (every region and feature,
Sensibull screen number, matches / differs / missing) all "matches", walked live, edits within 1,000 ms at p95.
Nothing outside this goal is started until it is done; the pre-push gate (owner's first process item) finishes.

Settled by the spec, not asked: ADR-193 (scope = screens the spec has; Sensibull-only features go to the owner one by
one); Q211 does not block building (owner 2026-09-29), so ready-made shapes are built; REQ-078 AC-1 sets the speed
target; row 39 (REQ-089, typed Manual P/L) was first left outside this goal, then brought IN by P3 (see P3 / P6);
strategy expiry per Q39 = C.
