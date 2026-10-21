# DRAFT plan after the Sensibull study (2026-10-21) - for owner approval (revision 2)

Core: the Strategy Builder's edit loop on the EXISTING outcome endpoint - a user changes a strategy's legs and the
server's one engine answers with every number fast enough to edit in, on live Zerodha prices.
Proof (step 1, before any Phase 1 build): on a trading day, logged in to Kite, use the endpoints that exist today.
(a) Get live planned entries for four NIFTY contracts of one expiry with typed strikes (an iron condor, e.g. BUY
22400 PE, SELL 22600 PE, SELL 23000 CE, BUY 23200 CE) from `POST /api/strategies/planned-entry`. (b) Send 10
`POST /api/strategies/outcome` requests, each one edit made by changing the legs in the request body (move one short
strike one step, move it back, widen both shorts, change lots 1 -> 2 -> 1, swap a wing, and so on). (c) Measure each
call's wall-clock latency and record all 10 (target: every call under 1 s on live ticks). (d) For one condor and one
2-lot variant, compare `summary.max_loss` with a hand calculation that INCLUDES charges and lots: (wider wing width -
net credit per unit) x lot size (65) x lots + `summary.charges` (the round-trip charges inside max profit / max loss,
`backend/ofo_app/routes/outcome.py:282`), equal to the paisa. (e) Send one request with `view: "estimated_now"` for
the same legs and confirm a "now" payoff comes back (the API returns ONE view per call, `outcome.py:151`,
`PayoffOut` `:265-267`). Recorded as evidence rows. If latency or the max-loss match fails, Phase 1 stops and is
re-planned around the failure (no UI is built on a slow or wrong loop).

Status: DRAFT. Nothing here is approved, and no spec file was changed. All other work stays FROZEN until the owner
approves a version of this plan. Evidence for every "OFO2 has / lacks" claim is in `gap-list.md` (row ids B1..G12).
Sensibull facts are in `README.md` (screen numbers; section 1.7c is the measured preset matrix).

## Why this plan

- The owner's feeling that the project is "going directionless" is fair. Since 2026-10-16 almost every contract
  (GC-1 .. GC-6) has been about the order path (baskets, reconciliation, tags, kill switch). That work is real and
  safe, but a user who opens the builder today gets five dropdowns per leg, no price while picking, no strike steppers,
  no ready-made shapes, and an expiry-only chart (gap rows B4, B7, B8, B26, B42). Example: building an iron condor
  takes 4 x 5 = 20 dropdown choices in OFO2 against 1 click in Sensibull.
- Sensibull Pro is free for every Zerodha user. OFO2 cannot win by matching its analysis menu. It can win by being a
  builder that is good enough for planning (so the user does not miss Sensibull) PLUS the things Sensibull does not
  do: the strategy as a plan, rule-based monitoring, an execution path that cannot leave a naked leg, and plain
  language for beginners (gap-list "must be DIFFERENT").
- So the order is: builder first (owner's prime focus), then the remaining reviewed safety work, then monitoring (the
  paid reason to exist), then the guided front door.

## Order of work (what may run before what)

1. **Before the core proof:** only #448 POOL-BUDGET (the DB pool sized from the role limit, F-45). Every live outcome
   call uses DB connections, and the role allows 5 in total; the proof would measure a pool bug otherwise.
2. **The core proof** (above).
3. **In parallel, UI-only Phase 1a work** that changes no backend file: the strike stepper UI over the strike list the
   catalogue already returns, and prices shown in the leg picker from endpoints that exist (planned-entry, chain
   socket).
4. **Land the Tier A stack BEFORE the first builder PR that touches `outcome.py` or `backend/ofo/engine`:** #419 ->
   #421 -> #418 -> #420 -> #417 -> #424 -> #394, then #478, #470, then #451 -> #452 (with #393 alongside). Reason:
   these PRs touch shared and engine-adjacent files; the GC-3F handover (lines 41-42) records that "Held PRs branched
   before a kit upgrade all answer RE-REVIEW NEEDED after update-branch (Tier A kit paths checked first); budget one
   narrow re-review per PR." Every builder engine PR merged first would move their bases again and trigger more
   re-reviews.
5. Then the backend parts of Phase 1 (server-side Shift / Width / Hedge, outcome extensions).
6. #450 CI-SPLIT and #474 WT-LINK-GUARD land after the core proof, at any point (they are not on its path).

## Phase 1 - Strategy Builder that is good enough to plan in (first, most detail)

Goal: a beginner or intermediate user can build, read and save any NIFTY / SENSEX strategy as fast as in Sensibull,
and reads its risk in plain words that Sensibull does not give.

**1a. Editing speed** (Sensibull 010-012, 032-038, 101-110). UI-only items first (order item 3), backend items after
the Tier A stack (order item 4).
| Feature | Gap row | Sensibull | Kind | OFO2 rule that shapes it |
|---|---|---|---|---|
| Strike -/+ stepper on each leg, over the catalogue's strike list | B7 | 011 | UI only | Next / previous strike from the list the catalogue returns, never typed |
| Leg picker with LTP (and OI) per strike from existing endpoints | B42 (part) | 032-038 | UI only | Prices come from the platform only (ADR-012) |
| Multiplier | B10 | 107 | UI only | - |
| Analysis-only leg toggle ("exclude from numbers") | B11 | 101-103 | UI + request | DIFFERENT: an excluded leg never leaves the plan; Execute is refused while any leg is excluded (ADR-002, ADR-017) |
| Pick legs from the Option Chain (B / S, lots) and import into the builder | B43 | 065 | Held PR #466 | REQ-030 Approved |
| Shape name on the leg list ("Iron Condor", "Custom Strategy") | B5 | 011 | Backend (Tier A: outcome reply) | `ofo/strategy/matching.py` already exists |
| **Shift / Width / Hedge, computed on the server on real strikes** | B8 | 101-110 | Backend (Tier A) | ADR-008; strikes snap to the catalogue's real strikes; disabled for an unknown shape; gated by S2 |
| Straddle / strangle quick picks (50-200 points from ATM) | B42 (part) | 038 | Backend + UI | Places strikes by rule from ATM: gated by S2 |
| Ready-made shapes that load into the builder | B4 | 010-012 | Backend (Tier A) + UI | Gated by S2; Sensibull's placement rules are in README 1.7c |

**Second proof inside 1a (before the Shift / Width / Hedge UI is built):** a server function, given real legs and the
live catalogue, returns the shifted / widened / re-hedged legs for a NIFTY iron condor (strike gap 50) and a SENSEX
iron condor (gap 100), and refuses with a catalogue message when a target strike is not listed. Proof: run it against
the day's real catalogue for both indices and feed the returned legs to the outcome endpoint; the reply's max loss
changes by the expected width x lot size.

**1b. Reading the outcome** (Sensibull 012-021, 125-129)
| Feature | Gap row | Sensibull | Kind | OFO2 rule that shapes it |
|---|---|---|---|---|
| "Now" curve on the payoff chart + hover with now / expiry P&L | B26, B27 | 013, 125 | Two calls per edit, or a Tier A API extension returning both curves | Labelled an estimate (REQ-034 AC-6). It overlays the two existing modes; it is NOT a third ADR-120 mode |
| Net premium Pay / Get, charges breakdown, reward / risk | B14, B15, B19 | 012, 022, 126 | Engine extension (Tier A), then display | The browser computes nothing (ADR-008) |
| Expected move (1 SD / 2 SD) band on the chart | B29 | 013 | Engine extension (Tier A), then display | Defined in REQ-027 (Q254: spot x ATM IV x sqrt(calendar days to expiry / 365)); REQ-034 AC-4 (line 30) already uses "expected move" for the default range |
| POP | B20 | 012 | Engine extension (Tier A), then display | Owner decision D4 (wording under ADR-055) |
| Warnings as codes: weekend / holiday decay, unhedged short, low liquidity / wide spread, expiry day | B50 | bundle 2.3 | Engine extension (Tier A), then display | Text from the reviewed catalogue (ADR-003 Q226). Lesson from README 1.7c: Sensibull flagged liquidity on every preset, so the flag meant nothing; OFO2 warns only on a measured condition |
| ATM IV and IV percentile in the header | B40 (part) | 026 | Backend | Data-feasibility test first (ADR-012) |
| Target level / target date what-if | B18, B36, B37 | 020 | Engine (Tier A) | ONLY if SPEC CHANGE S1 is approved; otherwise not built |

**1c. Keeping and sharing** (Sensibull 115-118)
| Feature | Gap row | Notes |
|---|---|---|
| My Strategies list (PR #393) | B46 | Reviewed; lands with the Tier A stack |
| Builder history / undo on screen (API exists) | B48 | OFO2-only strength (REQ-070) |
| Share a read-only link to a plan | B47 | Uses the existing draft link (W-073) |
| Learn page "Open in Builder" | X5 | Depends on B4 |
| "Prices have changed since you saved" marker and an explicit re-price action | - | Sensibull keeps save-time prices and marks the drift (README 1.7b); OFO2 already keeps planned entries (ADR-075); show the drift, never silently re-price |

OFO2 differentiators kept and made visible in Phase 1 (already built; checked in the exit criteria): plain-language
max profit / loss including charges (ADR-071, W-075), UX levels (ADR-004), margin shortfall shown in the builder
(B23), underlying locked while legs exist (B51), per-leg scenario table (B30), live push at most once a second (B52).

Exit criteria (all with evidence rows):
- The core proof and the second proof pass on a trading day.
- On the owner's account, an iron condor, a bull call spread and a short strangle are each built, edited with the new
  controls and saved, with screenshots at phone and desktop width (W-055 check).
- Every number on the screen comes from the outcome reply (the existing no-client-maths scan stays green).
- Tier A review on anything in `outcome.py`, the engine, or a module the Execute route imports; Tier B elsewhere; at
  most 2 rounds per item.

Explicitly NOT in Phase 1: IV editing and IV offset (B38), OI overlay on the chart (B28), TradingView chart (B41),
strategy price history (B35, ADR-066), Manual P&L (B44), stocks / BANKNIFTY (B3), dark theme, social share buttons.

Rough size (re-estimated): 1a ~8-10 days (UI-only part ~3 days; server Shift / Width / Hedge with its proof ~4-5
days; shape name and ready-made loader ~2 days if S2 is approved), 1b ~5-6 days (most items are Tier A engine
extensions), 1c ~2 days; one builder plus reviews. The Tier A stack landing (order item 4) runs alongside and is not
counted here.

## Phase 2 - Remaining safety work, then make execution feel safe (about 3-4 days)

Goal: the remaining reviewed execution safety work is on `main`, and executing from the new builder is calm.
Scope: #455 MKT-HOURS, #463 KILL-SWITCH, #459 INSTR-FRESH, #453 TOKEN-RETURN, #454 DUP-TAG, #456, #465 (land earlier
if the merge gate shows they overlap files a Phase 1 engine PR changes); Mindful pre-trade check-in on Execute (X3:
today's count, a short pause, "Have you checked your exit plan?"); Execute risk tiers (E5, ADR-140); paper tracking of
a saved plan (D2: P&L since saved, paper exit; Sensibull shows "Profit left / Loss left" for held trades, README 1.7b).
Exit: one live 1-lot two-basket entry and exit (ADR-117) from a strategy built in the new builder, owner present,
holdings unchanged, 0 reconciliation mismatches. NOT: new order features, slicing, intraday products.

## Phase 3 - Monitored against the user's own rules (the paid reason to exist, ~2 weeks)

Goal: a saved, executed strategy is watched against the user's rules and the user is told, with the exit basket
already prepared (ADR-009 assisted, not autonomous).
Scope: REQ-043 four health colours (P6), one rule family first - "index crosses a level" and "loss reaches my max
loss" (REQ-041, ADR-064 `max_loss`) -> in-app alert + WhatsApp through the shared Notifier (REQ-062, X7) -> prepared
exit basket the user places on Kite (REQ-042); the Positions screen part 1 (P1, W-111 branch). Technical choice to be
made in the phase (not an owner question): whether a rule can also be mirrored as a Zerodha GTT / ATO the user
confirms, since ADR-134 says broker features are linked, not rebuilt.
Exit: a real rule fires on a trading day, the WhatsApp is delivered (terminal status read), the prepared basket
matches the plan. NOT: automatic orders, adjustment suggestions (REQ-045/046).

## Phase 4 - The guided front door (~1 week) - GATED on the legal check under S2

Goal: a beginner who does not know strategy names gets to a planned strategy in the builder.
Scope: Guided create (PR #457, W-119) re-reviewed against this study (Easy Options 080-087, Expiry Trades 160-165),
plain "How this trade works" bullets next to a loaded plan (W3), risk-labelled variants ("lower risk / wider range")
instead of Sensibull's Defensive / Aggressive / "YOLO" (W2), never profit-ranked (ADR-003, ADR-055 (3)). The variants
place strikes by rule, so this phase does not start until S2 / D2 is answered and the legal check is done.
Exit: three real users (or the owner role-playing three profiles) reach a saved plan from "where do you think NIFTY
will go?" in under 2 minutes each. NOT: a profit-ranked wizard (W4), trade ideas or verdicts (A7).

## Later (not planned in detail)

Multi-user sign-in and Google login (G2, master plan Stage 5); analysing existing positions in the builder (B49,
W-083 blocked); including existing positions in the margin figure (B24); chain Greeks / IV views (C2); market context
data (B40, A1-A6); product analytics (G11); paid plans (S3 / D1, deferred).

## Held work (GC-3F handover 2026-10-21 + open PRs) - recommendation per item

Merging reviewed PRs is a technical call (owner rule 2026-10-16); this list is information. Every merge goes through
`merge.py <pr> --reviewed-sha <full sha>`.

| PR / branch | What it is | Recommendation | Reason tied to this plan |
|---|---|---|---|
| #448 POOL-BUDGET | DB pool sized from the role limit (F-45) | Merge first, before the core proof | The only item allowed before the core proof (order item 1) |
| #419 -> #421 -> #418 -> #420 -> #417 -> #424 -> #394 | mismatch store, next-day plan, gate fixes, never-split, tracker check, Windows pytest hook, return-route fix | Merge in this order, before the first builder PR touching `outcome.py` or the engine (order item 4) | All reviewed at the shas in the handover; landing them first avoids repeated RE-REVIEW NEEDED (handover lines 41-42) |
| #424 (#403, in the stack above) | Windows local pytest, a hook change | Reviewed PASS, Tier A: tracker row REVIEW-424 "read-only Opus round 1 PASS on 1a4a28bb460043e15853b2af5ef999104324b0e4" (build-ahead-tracker.md:143; row #403 at :70). The handover lists 5889145c8576df4035c72876c1267bfc1749ef55, which differs: confirm the handover sha matches the reviewed sha; narrow re-review only if the gate answers RE-REVIEW NEEDED | - |
| #417 TRACKER (in the stack above) | `tracker_check.py` | Merge if the build-ahead tracker stays the tracking tool, else drop | Tier B PASS (tracker row TRACKER) |
| #393 W-109 My Strategies | saved list + Completed filter | Merge with the stack | It is gap row B46 |
| #478, #470 (#380-2, net-roundtrip) | one reconciler in both money routes; earlier-day round trip | Merge after #394, before builder engine PRs | Tier A, money routes |
| #451 -> #452 (#313 order-book store) | migration 0020 + store | Merge in the existing stack order, after #419, with the reviewed shas the tracker names (152fe396ce31c4b2b34bedb833fc2da0fab079e9 for #451, a9049a2820b2321616e0af17525ff920cf567c21 for #452); #451 may need its own Tier A migration pass if the gate asks | Tracker row #313 (build-ahead-tracker.md:48): "NARROWED owner-accepted 2026-10-20 (ADR-134 rule; ADR-138 cut list approved): the store keeps only fills carrying our tag + adopted lots ... never Kite's whole book"; fresh Opus round 2 PASS on a9049a2 |
| #466 W-120 chain selection | Option Chain B/S + Zerodha permission per contract | Merge after one narrow re-review, Phase 1a | It is gap row B43 |
| #450 CI-SPLIT | per-job path filters | Merge after the core proof, any time | Cuts CI time for many small builder PRs; not on the proof's path |
| #474 WT-LINK-GUARD | refuses links into the main checkout | Merge after the core proof, any time | Protects the checkout during parallel builder work; not on the proof's path |
| #455, #463, #459, #453, #454, #456, #465 | execution safety rails and small checks | Merge in Phase 2 (earlier if they overlap a Phase 1 engine PR's files) | Decided by ADR-119 / ADR-127 etc.; protect the Phase 2 live run |
| #457 W-119 Guided create | ADR-121/122/124 flow | Hold; re-review in Phase 4 after S2 / legal check | Re-check against Easy Options / Expiry Trades |
| `build/W-111-positions` (PR #410 closed by GitHub) | Positions part 1 | Redo as a new PR in Phase 3 | Passed review; Positions belongs to the monitoring phase; merge main in first |
| #488 TRIM-STRUCT (parked) | far-strike trim guard | Keep parked | Needs an owner approval for a new external NSE fetch in the daily path |

## SPEC CHANGE proposals (each needs an owner yes / no; nothing is changed until then)

**S1 - SPEC CHANGE to ADR-120 (1): allow a target level and a target date, not IV.**
Quoted text: "(1) No what-if sliders (spot, implied volatility or days to expiry) in the Strategy Builder in V1;
REQ-034 AC-6 stays as written: two modes only, "At Expiry" and "Estimated Now"."
Proposed: add a target index level box and a target date stepper (each trading day up to expiry), computed by the
server and labelled an estimate; keep IV fixed (no IV what-if).
Text that would change with it:
- REQ-034 AC-6: "Scenario columns switch between 'At Expiry' (default, exact) and 'Estimated Now' (model-based,
  labelled as an estimate) (Q33A = C)." -> a third, labelled "Estimated on <date> at <level>" view.
- ADR-120 consequence: "The Builder (S1) offers the At Expiry / Estimated Now toggle only. Sensibull, TradingView and
  OptionStrat have what-if sliders; this product does not in V1, and a later change is a new decision." -> replaced
  by the new decision row.
Why: the most common planning question is "what if NIFTY is at X on Friday?", and today the only answers are "now"
and "at expiry". Sensibull evidence: 020 (target slider +6.1% -> 24392, "Date: 4D to expiry"), every number
recomputes; TradingView and OptionStrat do the same (docs/design/screens-research-2026-10-19-part2.md).
Note: the Phase 1b "now" curve on the chart is NOT this change; it draws the existing Estimated Now mode.

**S2 - SPEC CHANGE to ADR-055 (1): strikes placed by a fixed, published rule (ready-made shapes, quick picks,
Shift / Width / Hedge, guided variants).**
Quoted text: "(1) suggestions stay educational and generic - setups are shown as templates the user completes, with no
platform-picked strikes, stop-losses, targets or adjustment instructions presented as the platform's view".
Proposed: the platform may place strikes by a fixed, published rule, never by a market view, labelled "Strikes placed
by a fixed rule - change them", and the user must touch or confirm the strikes before Save. It covers four features:
(1) ready-made shapes loading at starting strikes (B4); (2) straddle / strangle quick picks at 50-200 points from ATM
(B42); (3) Shift / Width / Hedge moving every strike by a step (B8 - user-started, but the platform chooses the new
strikes); (4) Phase 4's risk-labelled guided variants (W2).
Why: without placed strikes a template is just a name and the user still makes about 20 choices. Sensibull evidence:
011-012 (one click = BUY 23000 CE / SELL 23200 CE); the measured matrix (README 1.7c) shows the rule is mechanical:
ATM = nearest strike, second strike about 1% of spot away (NIFTY 200, BANKNIFTY 500, SENSEX 400), condor shorts one
distance either side of ATM. OFO2 would publish its rule in the same plain way.
Risk: this is a compliance reading (ADR-055 waits on Zerodha compliance and the legal review Q211). Recommendation:
ask the legal reviewer before building items (1), (2) and (4); item (3) can be built behind the decision because it
only moves strikes the user already chose.

**S3 - SPEC CHANGE to ADR-023 (design intent only, NO build; deferred until Q260 / Q211 are answered).**
Quoted text (ADR-023): "Without another entitlement the account becomes Limited/Read-Only, never locked: history and
settings stay, active strategies keep being monitored with live data and alerts, but new strategies, execution of new
trades, the live Option Chain and new simulations need Pro".
Proposed intent: the reverse split - planning (builder, saving, the live chain) free for every signed-in user; Pro
covers monitoring, rules, alerts and prepared baskets. Note this is not a small edit: today ADR-023 gives monitoring
of active strategies to Limited users for free and charges for new strategies, so the proposal swaps which side is
paid.
Why it cannot be built now: ADR-055 (2) says "the paid plan, free Pro for the owner's account-opening clients and
referral rewards (ADR-024, ADR-025, ADR-026, ADR-038) are not built further and do not go live"; spec F-26 records
that an Authorised Person "shall not charge any amount from the clients"; ADR-144 (2) says "No rupee amount, plan
name, trial length or referral reward appears on any public page while ADR-055 (2) holds", and ADR-146 shows "Plan:
Free during early access". So S3 is recorded only as product intent for the day Q260 / Q211 are answered.
Why the intent matters anyway: Zerodha users already get Sensibull's builder free (README 11), so charging for
planning would compete on Sensibull's strongest, free ground.

**S4 - Not recommended now: strategy price history chart (ADR-066).**
Quoted text: "shows users no historical market data (REQ-047 AC-1 unchanged)". Sensibull 017 shows ~2 weeks of the
strategy's combined price. Recommendation: keep ADR-066 as it is; the display-rights question with Zerodha is not
worth raising for a low-value chart (gap row B35, value L).

## Owner decisions needed (business calls only, recommended answer first)

- **D2 (S2) - May the platform place strikes by a fixed, published rule** (ready-made shapes, quick picks,
  Shift / Width / Hedge, guided variants)? Recommended: yes, with the label above; legal check first for ready-made,
  quick picks and guided variants; Shift / Width / Hedge may proceed. Business / compliance call.
- **D3 (S1) - Target level and target date in the builder?** Recommended: yes for level and date, no for IV. Product
  scope call (it reverses ADR-120).
- **D4 - Show POP (probability of profit)?** Recommended: yes, labelled "a model probability from today's prices, not
  a forecast"; ADR-055 (1) bars showing an "expected return ... as a performance claim", and POP is a probability, not
  a return - but it is the owner's (and the legal reviewer's) reading. Business / compliance call.
- **D5 - Approve the phase order** (Builder -> remaining safety work -> monitoring -> guided). Recommended: yes. The
  alternative (monitoring before the builder) sells the paid feature sooner but leaves the planning screen every user
  sees first in today's state.
- **D1 (S3) - What would be paid - DEFERRED.** Not asked now: ADR-055 (2), F-26, ADR-144 and ADR-146 keep every paid
  plan off until Q260 / Q211 are answered. Recorded as design intent only.

## Findings to register in the next docs PR (not done here; this branch changes no spec file)

- Correct spec F-51: logged in, Sensibull DOES have guided flows (Easy Options: UP / NEUTRAL / DOWN -> three variants;
  Expiry Trades: where will it close -> target ladder; Strategy Wizard: target + date). F-51 was based on public pages
  only.
- Sensibull's builder showed no margin-shortfall warning (Margin Needed above Available, `margin_shortfall` null);
  OFO2 already warns (B23).
- Sensibull sends only ticked legs ("Trade <n>") - a partial-strategy send path; the class OFO2's ADR-002 / ADR-117
  exclude.
- Sensibull's compute API uses lots in one call and units in another (README 12) - a quantity-unit class.
- Sensibull places preset strikes by a mechanical ATM rule, detects only 16 shapes, has no SENSEX futures presets,
  and its FINNIFTY calls calendar preset fails (README 1.7c) - evidence for S2.
