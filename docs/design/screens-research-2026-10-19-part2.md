# Screens research, part 2: the remaining screens (2026-10-19)

Owner brief (2026-10-19): every screen must be in the plan, with content and layout taken from research on similar apps,
and all research must be documented in the repo so it can be referred to later. This is part 2 of
`docs/design/screens-research-2026-10-19.md` (the morning note, 10 screens); it covers the rest. The business
requirements stay fixed.
Method: public web pages only; nothing logged into; "not found" where a page does not state something; (SS) marks facts
from a search summary; wireframes are OUR proposals; the spec wins every conflict. Three research runs studied Sensibull,
Kite, Dhan, Upstox, Angel One, AlgoTest, Opstra, Quantsapp, Stockmock, Streak, Tradetron, TradingView and OptionStrat, and
checked each screen against the REQ and ADR text.
Honest limit: most vendor pages describe features, not pixel layouts. No logged-in layout and no 390 px behaviour was seen
for any app (section A12 lists what was not verified). Facts marked SS come only from a search summary.
Look and feel (font, colours, card style): follow `D:\Abhay\GLOBAL.md` section 3 "Design & UX preferences" (by path only).
Every screen brief cites `Design basis: docs/design/screens-research-2026-10-19[-part2].md section <name>`.

## Sections

A1 Strategy Builder; A2 Create Strategy (guided); A3 My Strategies + History tab; A4 Execute review; A5 Orders;
A6 Positions in depth; A7 Adjustments; A8 Public landing; A9 Sign-up / login / profile / security / delete;
A10 Billing / Free eligibility / Referrals / Complimentary Pro; A11 Zerodha connection + Broker & Market Data;
A12 Not verified. Then "Shared states and screen rules" and "Orchestrator decisions".

---

### A1. Strategy Builder (REQ-034, 035, 068, 069, 070; ADR-003, 008, 056)
**Exists today:**
- `frontend/src/pages/StrategyBuilderPage.vue` plus 12 components in `components/strategy/` (StrategyTable, LegRow,
  PayoffChart, SummaryCards, MarginLine, StrategyHeader, StrategyActions, AdvancedDetails, StrategyFooter, LegPicker,
  SaveDraftBar, PnLCell).
- **Not in `REAL_PAGES`**, so the nav item `strategies-strategy-builder` shows the placeholder (`routes.js:9-21`; finding F-49).
- No "Estimated Now" toggle found.

**(a) What the apps do:**
- **Sensibull:** the graph switches to a table showing Target Day and Expiry Day P&L, with a target selector, an
  interval dropdown, a Target Date slider and a "Show %" toggle
  (https://blog.sensibull.com/2023/07/06/payoff-table-on-strategy-builder-analyse-widgets/). A forum says the
  target-day curve shifts with IV (https://tradingqna.com/t/sensibull-payoff-graphs-wrong-on-target-date/92019, SS,
  anecdotal).
- **AlgoTest:** shows the payoff, max P/L, breakevens and 4 Greeks instantly, starting from the live chain.
- **Dhan:** a live payoff, a Hedge Benefit margin view, and a Greeks toggle (decimal or per-lot). Templates include
  Iron Condor, Iron Fly, straddles and spreads, and custom strategies can be saved
  (https://algotest.in/blog/option-strategy-builder-algotest-vs-dhan.md; competitor-written).
- **Angel One InstaTrade:** predefined and custom tabs, Max Profit, Max Loss and Margin, and payoff and Greeks views
  (https://www.angelone.in/news/product-updates/angel-one-options-strategy-builder).
- **TradingView:** a payoff line plus a T+0 line plus a Greek line; what-if by time shift and IV shift, with defaults
  +5 days and ±10% IV; custom scenarios can be stored
  (https://www.tradingview.com/blog/en/what-if-scenarios-in-options-strategy-builder-54290).
- **OptionStrat:** a days-to-expiry slider and an IV shock slider (https://optionstrat.com/tutorials/options-builder,
  SS).
- **Upstox:** shows breakeven and margin (SS; the page returned HTTP 500).
- **Quantsapp and Stockmock:** a builder exists, but its layout was not found.

**(b) Content:**

| Item | Serves |
|---|---|
| Header: name, underlying, expiry, "Suggested Setup"/"Draft" state, spot with its time | REQ-069 AC-5; REQ-049 AC-4 |
| Plain-language outcome first: can lose / can make / starts losing at | REQ-034 AC-7 |
| Summary: max profit, max loss, breakevens, net credit/debit, margin, charges (all from the server) | REQ-034 AC-1; REQ-024 AC-2; ADR-008 |
| Payoff graph with current-level marker, same engine as the table | REQ-034 AC-2, AC-8 |
| "At Expiry" (default) / "Estimated Now" toggle, labelled an estimate | REQ-034 AC-6 |
| One table: legs plus scenario columns, sticky left columns, current and 0-P&L columns | REQ-035 AC-1..3; REQ-034 AC-5 |
| Level gating: Guided hides IV and Greeks; Standard adds % and breakevens; Advanced adds Greeks and IV | REQ-035 AC-7; ADR-056 |
| Leg editor: picker of listed contracts, lot stepper, remove, Undo | REQ-035 AC-8; REQ-070 AC-4 |
| "Related to your preferences" (guidance only); an alternative opens a preview with "Review setup" | REQ-068 AC-5, AC-6 |
| Range-departure prompt: Keep / Update / Continue anyway | REQ-069 AC-7 |
| Save draft; link to Execute (no order button) | ADR-002 |
| Scenario column step and range customisation | REQ-034 AC-4 |

**(c) Wireframes:**
```
Strategy Builder   Iron Condor (Suggested Setup)   NIFTY 24,350 @11:42
You can lose 8,175 | You can make 6,825 | Start losing below 22,909 / above 23,491
Max P 6,825 | Max L 8,175 | BE 22,909/23,491 | Margin .. | Charges ..
[ At Expiry | Estimated Now(est.) ]            Legs [+ Add leg]
 payoff graph (marker at current)      | Related to your preferences
 Leg Act Strike Qty Entry LTP .. |22,900|CURRENT 23,047|0-P&L .. | Status
 [Undo] [Save draft]                                   [Go to Execute]
390px: name+state, spot, Lose/Make, BE, graph, toggle, table scrolls in its card,
collapsible Legs/Related/Details, bottom bar [Save draft][Execute]
```

**(d) Dropped:**
- "Best strategy" labels or ranking (ADR-003).
- Order buttons (ADR-002).
- Browser-side maths (ADR-008).
- Greeks or IV at Guided/Standard (REQ-035 AC-7).
- **SPEC CHANGE (owner Q4):** what-if sliders for spot, IV and days. REQ-034 AC-6 has two modes only, and REQ-026 AC-5
  bans slider input for the range. **Decided 2026-10-19: no sliders in V1 (ADR-120).**

### A2. Create Strategy, guided (REQ-024, 026, 028, 068, 069)
**Exists today:** none (`strategies-create-strategy` is a placeholder).

**(a) What the apps do:**
- **Angel One:** predefined/custom tabs, with setups described as bullish, bearish or neutral.
- **Dhan and AlgoTest:** template lists (URLs above).
- **Sensibull, Upstox, Quantsapp, Stockmock, Opstra:** a guided objective, market-view or range wizard was **not
  found**. Ours is a spec design (finding F-51).

**(b) Content:**

| Item | Serves |
|---|---|
| Two path cards: Guided Strategy Builder / Advanced Manual Builder | REQ-024 AC-1, AC-6 |
| Six objectives, including "I already know my strategy" | REQ-024 AC-3, AC-4 |
| Market view: bullish / bearish / neutral / big move / not sure, plus optional detail | REQ-024 AC-7 |
| "Not sure" path: expiry first, then lower and upper pick lists starting at the current level | REQ-026 AC-1..6 |
| Result line "Based on your expected range of X-Y by <expiry>, here are strategies you could consider" | REQ-026 AC-4 (waits on legal review Q211) |
| 2-4 cards plus See more: name, view, max P/L, breakevens; "View details" | REQ-024 AC-8 |
| Setup cards Conservative / Balanced / Aggressive, "Why you're seeing this", Compare | REQ-069 AC-1..4 |
| Preferred types first; if none fit, say so | REQ-068 AC-4 |
| Level label Beginner / Intermediate / Advanced | REQ-068 AC-2 |
| Template library as data, plus Custom | REQ-028 AC-3, AC-4 |
| Advanced path opens an empty Builder | REQ-024 AC-5; REQ-035 AC-8 |

**(c) Wireframes:**
```
Create Strategy
[Guided - Help me build] [Advanced Manual - I know what I want]
Step 1 Objective: (Earn premium)(Limit risk)(Rises)(Falls)(Big move)(I know my strategy)
Step 2 View: (Bullish)(Bearish)(Neutral)(Big move)(Not sure)  [optional detail v]
Step 3 Expiry [This Week - 24 Sep v]  Lower [..v]  Upper [..v]
Strategies you could consider: [card][card][card]  [See more]
390px: one step per screen, "Step 2 of 4", full-width choices, Back always visible
```

**(d) Dropped:**
- "Top picks", "Best for you", ranking by expected profit (ADR-003).
- Probability of profit stated as a promise (ADR-008).
- Typed numbers, a slider, or a pre-filled range (REQ-026 AC-3, AC-5).
- Flag: suggested setups with specific strikes may count as research under SEBI rules (Q261); the wording is
  provisional.

### A3. My Strategies + History tab (REQ-070, 044 AC-2, 037 AC-5)
**Exists today:** a placeholder; held PR #393 (W-109).

**(a) What the apps do:**
- AlgoTest and Dhan let you "save custom strategies", but the list layout was not found.
- Sensibull's saved-strategy UI was not found.
- TradingView stores what-if scenarios, not strategy versions.
- No app was verified to have automatic history with restore.

**(b) Content, My Strategies** (no AC defines the list):

| Item | Serves |
|---|---|
| Groups: Saved drafts / Live / Completed | no AC; supports REQ-009 nav and the GC-5S drafts decision |
| Row: name, underlying, expiry, server status, times; max P/L as server strings or "—" | ADR-008, ADR-010 |
| Actions: Open, Duplicate, Delete draft (owner Q5) | no AC; Delete decided 2026-10-19, ADR-118, REQ-070 AC-6 |
| Draft with no price: "Draft — Live data not connected" | REQ-049 clarification |
| Search and filter by underlying/expiry | no AC |

**Content, History tab:**

| Item | Serves |
|---|---|
| 3rd tab, not shown by default | REQ-070 AC-5 |
| Plain-word rows ("Original suggested setup", "User modified strike") with time | REQ-070 AC-2 |
| Original range, the generated setup, each change, the final setup | REQ-069 AC-8 |
| Restore saves the current version first; Undo after each change | REQ-070 AC-3, AC-4 |
| Modification versions kept; history survives execution | REQ-037 AC-5; REQ-070 AC-5 |

**(c) Wireframes:**
```
My Strategies                      [Create Strategy]  Search [..]
Saved drafts (3)
| Iron Condor Oct-27 | NIFTY | 27 Oct | Draft - Live data not connected | MaxP .. MaxL .. | [Open][Duplicate][Delete]
Live (1) / Completed (2)
Strategy > [Planning][Live Position][History]
 History: 11:40 Original suggested setup | 11:52 User modified strike [Restore]
390px: cards with an overflow menu; History as a vertical timeline with Restore per row
```

**(d) Dropped:**
- Manual version names (REQ-070 AC-2).
- History on the main screen by default (REQ-070 AC-5).
- One-tap Exit or Repeat on a row (ADR-002).

### A4. Execute review (REQ-055, 056, 058, 073, 036; ADR-016..019, 054)
**Exists today:** `ExecuteStrategyPage.vue` (at `/strategy/:id/execute`):
- waits for live prices;
- has "Prepare entry/exit orders";
- has an orders table (Side, Qty, Contract, Type, Price, Tag);
- shows no margin, charges, max P/L or sequence view in lines 1-120.

`ExecutionReturnedPage.vue`: "Back from Kite" with a "Check with Zerodha" button and no auto-run.

**(a) What the apps do:**
- **Kite basket** (https://support.zerodha.com/category/trading-and-markets/kite-features/basket-order/articles/kite-basket-orders; finding F-50):
  - It shows "Required margin" and "Final margin" (SS example: 50,343.68 vs 38,913.68).
  - It places orders in basket sequence. The sequence changes the required margin but not the final margin.
  - For F&O, buy options first.
  - Rejected orders are re-run by hand; no fee.
  - "Include existing positions" can show a required margin of 0.
  - Partial-failure handling: not stated.
- **Sensibull:** a forum post says the first basket order must be a buy (unconfirmed).
- **Others:** basket review layout not found.

**(b) Content:**

| Item | Serves |
|---|---|
| Strategy name, underlying, expiry, leg count, "Zerodha" | REQ-056 AC-5 |
| Plan number, entry or exit | REQ-073 |
| Order rows: leg, action, contract, qty, LIMIT, price, tag, sequence number | REQ-056 AC-8; REQ-073 AC-1/2 |
| Sequence note: protective buys first; exits buy back shorts first, then sell longs | REQ-056 AC-3; REQ-058 Q238 |
| Margin required vs available, "planning estimate; Zerodha's figure is authoritative" | REQ-055 AC-1/3 |
| Margin short: no basket; offer change quantity / review / add funds | REQ-055 AC-4 |
| Max loss, max profit, current P&L (server strings) | REQ-056 AC-5; ADR-008 |
| Charges estimate, labelled | REQ-056 AC-8; ADR-082 |
| Risk message by level; no generic "I understand" box | REQ-056 AC-6 |
| "Ready to execute": order count, margin, max loss | REQ-056 AC-9 |
| "Open on Kite" (on click only), then "Check with Zerodha" | REQ-073 AC-1/3 |
| "Every trade follows a strategy" | REQ-036 AC-4 |

**(c) Wireframes:**
```
Execute Strategy: Iron Condor Oct-27  (plan 2, ENTRY)
Margin (estimate)  Required 1,10,000 | Available 2,40,000
Max loss 5,900 | Max profit 4,100 | Charges ~ 310 (est.)
# Side Contract     Qty Type  Price  Tag
1 BUY  24100 PE     75  LIMIT 29.90 Q0B1201
2 BUY  24600 CE     75  LIMIT 31.40 Q0B1202
3 SELL 24200 PE     75  LIMIT 58.00 Q0B1203
[Ready to execute: 4 orders]  [Open on Kite]  [Cancel]
390px: margin line, max P/L, orders as cards, sticky [Open on Kite]
```

**(d) Dropped:**
- A "Place order" button that sends orders (REQ-073 AC-4, ADR-054).
- A Market/Limit/SL menu (REQ-056 AC-7).
- Drag-reorder (the engine owns the sequence, REQ-056 AC-2).
- The "Include existing positions" toggle.
- **Conflicts (owner Q2, Q3):** REQ-056 AC-4 vs REQ-073 AC-1; REQ-056 AC-7 vs REQ-073 AC-1. **Decided:** Q2 = two
  baskets (ADR-117); Q3 was already decided by the owner in ADR-080 (3) and ADR-095 (pro rata): "current market
  conditions" = the per-leg executable LIMIT; "price protection" = the tolerance split pro rata across leg LIMIT prices.

### A5. Orders (REQ-057, 058, 073; ADR-017)
**(a) What the apps do:**
- **Kite:** interim statuses pass quickly, and an API 200 does not mean executed
  (https://kite.trade/forum/discussion/comment/6807/, SS).
- **Upstox:** tabs All / Working / Inactive / Filled / Cancelled / Rejected; the reason is in Order Details
  (https://upstox.com/help-center/how-to-check-the-orders-in-upstox-trading-view-255126/, SS).
- **Angel One:** Executed / Pending / Rejected / Cancelled; the reason is under Order History
  (https://www.angelone.in/knowledge-center/trading-account/list-of-order-status-on-your-angel-one-trading-account,
  SS).
- **Others:** not found.

**(b) Content:**

| Item | Serves |
|---|---|
| Tabs: Pending, Executed, Failed/partial, Execution history | nav.js; REQ-009 |
| Row: strategy + plan, contract, side, qty ordered/filled, price, status, last update | REQ-057 AC-1 |
| Only the 7 status words: Prepared, Submitted, Pending, Partially Executed, Executed, Rejected, Cancelled | REQ-057 AC-1 |
| "Submitted, not yet executed" is shown as pending, never as a position | REQ-057 AC-2 |
| Failed/partial shows Zerodha's reason, with the REQ-058 buttons | REQ-058 AC-1/2/6 |
| Partial entry: Complete Strategy / Retry Failed Leg / Review Manually / Close Partial. Partial exit: Complete exit / Review manually | REQ-058 AC-2; ADR-109 |
| Close Partial lists the cancels as instructions with a Kite link | REQ-058 Q223 |
| History: all plans, filter by strategy and date, tag match | REQ-073 AC-2/3 |
| "Strategy-linked orders only. No order-entry form." | REQ-036 AC-2 |
| Data age plus a "Check with Zerodha" refresh | REQ-073 AC-3 |

**(c) Wireframes:**
```
Orders  [Pending] [Executed] [Failed/partial] [History]    Filter: strategy v  date v
Strategy       Contract    Side Qty  Filled Status           Updated
Iron Condor 2  24600 CE    BUY  75   75     Executed         11:42:07
Iron Condor 2  24200 PE    SELL 75   0      Rejected: <Zerodha reason>   [Retry Failed Leg]
390px: one card per order; status+time; reason; action buttons below
```

**(d) Dropped:**
- Row cancel/modify buttons (ADR-054; show an instruction plus a Kite link instead).
- Automatic retry (REQ-058 AC-6).
- A standalone order list (REQ-036 AC-1).

### A6. Positions in depth (REQ-044 AC-3, 060 AC-7, 061; ADR-109, 110)
**(a) What the apps do:**
- **Kite:** overall P&L on the Positions tab, day P&L via Info, and a Day's P&L column. F&O uses a FIFO entry price,
  and the buy average covers all of that day's trades
  (https://support.zerodha.com/category/console/portfolio/holdings/articles/intraday-pnl ;
  https://zerodha.com/z-connect/updates/track-your-overnight-positions-with-days-pl-on-kite-web, SS).
- **Sensibull:** groups positions by underlying, lets users name groups, filters by expiry, and exits all legs or one
  by one (https://blog.sensibull.com/2022/09/02/trade-better-with-sensibull-positions-page/).
- **Others:** columns not found.

**(b) Content:**

| Item | Serves |
|---|---|
| Tabs: Current, Strategy-linked, Adjustment opportunities, P&L/risk | REQ-044 AC-3 |
| One group per strategy with server status and net P&L | REQ-044 AC-3/4 |
| Row: contract, Zerodha qty, average, LTP + time + health, P&L (day and overall only if the server sends both) | REQ-049 AC-4 |
| Outside lots: "Bought outside this app; not part of any strategy" | ADR-109; REQ-060 AC-7 |
| Open-plan row "Order placed - waiting for Check with Zerodha", qty "not yet confirmed", link to Execute | ADR-110 |
| Standalone lots: add to a strategy / new strategy / leave standalone (not monitored) | REQ-061 AC-2/4 |
| Only row action: "Open strategy" | REQ-044 AC-3 |
| Mismatch/blocked badge, reason, Reconcile link | REQ-060 AC-3/6 |

**(c) Wireframes:**
```
Positions [Current][Strategy-linked][Adjustment opportunities][P&L/risk]
Strategy-linked
 Iron Condor Oct-27  (o) Watch            P&L +1,240.00        [Open strategy]
  SELL 24500 CE  -75  avg 70.20  LTP 62.10 @11:42 (o)  +607.50
Outside lots (not part of any strategy)
  BUY 25000 CE  +65   avg 41.00  LTP 38.00 @11:42      -195.00  [Group into a strategy]
390px: cards per group; each contract on 2 lines
```

**(d) Dropped:**
- Row Exit/Add/Convert buttons (ADR-002, REQ-044 AC-3).
- Browser-computed P&L (ADR-008).
- Merging two strategies' lots into one row (REQ-060 Q224; the flat-contract lift of ADR-116 is one audited action, not a merged row).

### A7. Adjustments (REQ-037, 045, 046; ADR-011)
**(a) What the apps do:**
- **Sensibull:** you adjust from Positions through the Builder and see the P&L impact. It has Strike Controls (Shift,
  Width, Hedge) and a Conditional Exit (2025) that closes everything when the index crosses a level
  (https://blog.sensibull.com/2025/06/06/introducing-conditional-exits/, SS).
- **AlgoTest:** "one-click adjustments" (its own blog, SS).
- **All apps:** no Before/After overlay found. Others: not found.

**(b) Content:**

| Item | Serves |
|---|---|
| List rows: "Adjustment opportunity detected" or "Your rule was triggered"; several grouped | REQ-045 AC-1/8 |
| Layer 1 "Why detected": condition, distance, rule, time, data state | REQ-046 AC-1/5 |
| Layer 2 "Current state": P&L, max P/L, breakevens, Greeks, margin, DTE, IV/OI/LTP | REQ-046 AC-2 |
| Layer 3 "Possible approaches": generic, no recommendation | REQ-046 AC-3; REQ-045 AC-5/6 |
| Layer 4 "Next step": the user picks; the platform builds it; strikes editable | REQ-046 AC-4; Q255 |
| Before/After: legs, P&L, risk, margin, Greeks, breakevens, payoff, charges | REQ-037 AC-2/3 |
| "This action changes your strategy's risk profile" | REQ-036 AC-5 |
| Confirm → Execute; a new version is kept | REQ-037 AC-4/5 |
| Playbooks (global plus per strategy) | REQ-045 AC-7 |
| Same list under Positions > Adjustment opportunities | REQ-045 AC-9 |

**(c) Wireframes:**
```
Adjustment opportunity detected - Iron Condor Oct-27   Why am I seeing this?
1 Why: NIFTY 24,350 is 0.4% from short 24,500 CE (limit 0.5%)  11:42:07 (o)
2 State: P&L -4,088 | max loss 8,175 | BE 24,180/24,520 | DTE 8
3 Approaches: [Roll call spread] [Add hedge] [Exit] ...   (no recommendation)
4 Before | After  legs, P&L, margin, Greeks, payoff   [Edit strikes] [Confirm, go to Execute] [Dismiss]
390px: four stacked cards; Before/After as two tabs; sticky Confirm
```

**(d) Dropped:**
- Conditional Exit / rule-triggered orders (ADR-002).
- "Best adjustment" or ranked candidates (ADR-003).
- One-tap roll (REQ-037 AC-4).
- Legal review Q211 still applies.

### A8. Public landing (REQ-010, ADR-027, ADR-055)
**(a) What the apps do:**
- **Sensibull:** the root is "Login to Continue" with Zerodha / Angel One / Upstox / ICICI Direct plus Google, and
  sections for features, testimonials and Free/Pro pricing (https://sensibull.com/).
- **Dhan/Upstox:** show delayed prices when logged out (spec F-16; ours is stricter and shows none).
- **Opstra:** not found.

**(b) Content:**

| Item | Serves |
|---|---|
| Product explanation | REQ-010 AC-2 |
| Every screenshot or payoff stamped "Sample · Historical" | REQ-010 AC-2, AC-3 |
| Pricing block | REQ-010 AC-2 |
| FAQ, including "we never ask for your Zerodha password" | REQ-015 AC-6 |
| Sign up / Log in | REQ-010 AC-2 |
| Disclaimer footer | ADR-003 |

**(c) Wireframes:**
```
[Logo] How it works  Pricing  FAQ  [Log in]
Plan options strategies. See every outcome.  [Sign up]
[payoff chart  SAMPLE · HISTORICAL]
How it works (3 cards) | Pricing | FAQ | Footer: disclaimer, Terms, Privacy
390px: stacked, hamburger menu
```

**(d) Dropped:**
- Live or delayed tickers, a chain preview, returns claims (REQ-010 AC-1, ADR-055).
- Profit testimonials.
- Broker-login buttons.

**Exists today:** none (`/` redirects to `/home`).

### A9. Sign-up / login / profile / security / delete (REQ-012, 013, 014, 003, 018 AC-1)
**Scope note (owner, 2026-10-19: "Ignore google signin and signout in this plan"):** these screens are out of the
GC-6 plan and stay on the tracker as `stage-5` rows. The research is kept here so it can be used then.

**(a) What the apps do:**
- **AlgoTest:** mobile OTP, no password (https://algotest.in/pricing).
- **Sensibull:** broker login plus Google; the session ends with the broker session
  (https://algotest.in/blog/sensibull-review-2026-features-pricing-and-who-its-for.md).
- **Upstox:** mobile plus PIN plus OTP; trusted 30 days on a device and 7 days in a browser; 5 wrong PINs block the
  account
  (https://help.upstox.com/support/solutions/articles/251690-how-do-i-login-using-my-mobile-number-, SS).
- **Dhan:** account closure process conflicting (SS).
- **All apps:** no sessions list, no 2FA page and no in-app delete found.

**(b) Content:**

| Item | Serves |
|---|---|
| "Continue with Google" | REQ-012 AC-1 |
| Mobile + WhatsApp OTP, resend, attempt limit | REQ-012 AC-2, AC-3 |
| Required: name, experience (5 options), profession (10 options), consents. Optional: date of birth, city. Never an address | REQ-012 AC-4..7 |
| After sign-up: Home "Pro trial day 1 of 7", no Zerodha prompt | REQ-018 AC-1; REQ-008 AC-1 |
| Profile and change email | REQ-013 AC-1, AC-2 |
| Delete account: what is kept vs erased | REQ-013 AC-3 |
| Security: Google email, mobile status, logout | no AC |
| Invite-only message | REQ-003 AC-2 |

**(c) Wireframes:**
```
Create your account (centred card 440px)
[G Continue with Google]   1 Google ok  2 Mobile  3 About you
Mobile +91 [__________] [Send OTP]   OTP [ ][ ][ ][ ][ ][ ]  Resend 28s
Experience [v]  Profession [v]  [ ] I accept Terms/Disclaimer
390px: full width, "Step 2 of 3"
```

**(d) Dropped:**
- Asking for a Zerodha password or PIN (REQ-015 AC-6).
- Mobile as the trial key (REQ-014 AC-5).
- Broker-only login (REQ-015 AC-1, AC-7).
- Device fingerprinting (REQ-014 AC-7).

**Exists today:** none; there is no user-auth backend route.

### A10. Billing / Free eligibility / Referrals / Complimentary Pro (REQ-017..023, ADR-055)
**ADR-055 holds** the paid plan, complimentary Pro and referral rewards until Zerodha compliance answers (Q260).
REQ-022 and REQ-023 are Specified only, so these screens are **shells**.

**(a) What the apps do:**
- **AlgoTest:** Free Rs 0; PRO Rs 4,000/month or Rs 19,999/year; PRO+ Rs 8,000/month or Rs 39,999/year; no trial
  stated (https://algotest.in/pricing).
- **Sensibull:** Pro is Rs 0 for Zerodha users and about Rs 800/month for other brokers (third-party).
- **Streak:** free for Zerodha users (SS, secondary).
- **All apps:** no read-only-after-trial mode, invoices page or referral reward found.

**(b) Content:**

| Item | Serves |
|---|---|
| Status line "Pro trial: day 3 of 7, ends 26 Oct" | REQ-017 AC-3; REQ-018 AC-1 |
| After trial: "Limited (read-only)", plus what you keep and what is locked | REQ-018 AC-2..5, AC-11 |
| Pro Rs 600/month; annual price set by admin | REQ-023 AC-1, AC-2 |
| Contextual Subscribe / Check Free Eligibility buttons, no popups | REQ-018 AC-9 |
| Complimentary: "You're already on Pro", Rs 0, payment disabled | REQ-019 AC-3, AC-4 |
| Free Eligibility options; "Zerodha Partner Benefit" wording | REQ-022 AC-1..3 |
| Referral reward days, stacking | REQ-021 AC-1, AC-6 |
| Client ID never shown | REQ-019 AC-6 |
| Invoices | no AC; supports REQ-023 AC-4 |

**(c) Wireframes:**
```
Subscription & Billing
Plan: Pro trial   ends 26 Oct   After trial: Limited (read-only)
Keeps: monitoring, alerts, history   [Subscribe to Pro] [Free Eligibility]
Invoices: none yet
390px: stacked, keeps/locked collapsible
```

**(d) Dropped:**
- A grace period (REQ-023 AC-4).
- Card capture before Razorpay is live.
- Copied prices.
- Wording that implies an incentive for account opening (Q260).
- "Best plan".

### A11. Zerodha connection + Broker & Market Data (REQ-015, 014 AC-8/10)
**(a) What the apps do:**
- **Sensibull:** the connection is the login; it lists the Kite permissions it asks for (SS).
- **AlgoTest:** a static IP is needed for order execution (Rs 250/month shared, Rs 750/month dedicated); viewing needs
  none (https://algotest.in/pricing).
- **All apps:** no guided Kite app setup found.

**(b) Content:**

| Item | Serves |
|---|---|
| Contextual "Connect your Zerodha account to continue..." | REQ-015 AC-1, AC-2 |
| Guided setup, 7 steps | REQ-015 AC-3 |
| End state lines, including "Historical market data: Not currently available" | REQ-015 AC-3 |
| Four statuses: Connected / Partially connected / Disconnected | REQ-015 AC-4 |
| Last sync; Reconnect, Disconnect | REQ-015 AC-4, AC-8 |
| "Session expires daily" | REQ-015 AC-5, AC-7 |
| "We never ask for your password, PIN or OTP" | REQ-015 AC-6 |
| Trial-already-used notice; association transferred | REQ-014 AC-8, AC-10 |

**(c) Wireframes:**
```
Settings > Broker & Market Data
 Account connection   (o) Connected
 Live market data     (!) Partial: <why>
 Position sync        (o) Connected
 Execution readiness  (x) Disconnected
 Last sync 11:42  [Reconnect][Disconnect]   Historical data: Not currently available
390px: same rows stacked
```

**(d) Dropped:**
- Credential or token fields in the browser (REQ-015 AC-6, AC-9).
- A silent reconnect that places an order.
- Broker session = platform session.

### A12. Not verified (honest list)
- No logged-in layouts and no 390 px behaviour for any app.
- Sensibull's saved-strategy UI.
- Layouts for Opstra, Quantsapp, Stockmock, Groww, Fyers and Dhan.
- Kite's Orders tab names.
- Zerodha's list of rejection reasons.
- Official pricing for Opstra, Stockmock and Tradetron.
- The Upstox builder page (HTTP 500).
- Several facts come only from search summaries (marked SS).

---

## Shared states and screen rules (independent usability review 2026-10-19)

Three independent reviewers (broker-app expert, usability, delivery/platform) read the screen plan. The usability
review's accepted findings are these. They apply to every screen in the build order below.

**Build order (journey 1 is completed end to end before anything else):**
1. S1 Builder.
2. S2 Chain selection, S3 Create Strategy (guided) and Home state 1 (new user), in parallel.
3. S5 Execute, built now and merged after Wednesday's merges (backend-touching parts).
4. S6 Orders, S7 Positions, plus the post-Kite landing page.
5. S4 My Strategies, then journey 2: S9 Alerts, then the Live Position tab, then S10 Adjustments.
6. S8, the rest of S11, S12, S13.

**Shared states every screen must handle (one component each, a tracker row each):**
- **Market closed / stale:** "Market closed. Prices are from <time>." On Execute, this state also disables the action
  (D8, ADR-119).
- **Zerodha session ended:** a blocking card on S5, S7 and the Live Position tab with "Reconnect to continue". After
  reconnecting, the user returns to the same screen, with the last sync time shown (REQ-015 AC-5).
- **Two-basket middle state (D3, ADR-117):** a stepper on S5, S6 and the Live Position tab: "Step 1 of 2 Buys / Step 2
  of 2 Sells (locked until Zerodha confirms the fills)". Plus two states:
  - "Buys filled. Sells not placed yet. Your position is not complete."
  - "A buy failed. Sells stay locked."
  These are REQ-056 AC-11.
- **Return from Kite:** "Checking with Zerodha…", then one of three outcomes: done, "no change detected yet", or
  failed with a Retry.
- **Empty state per screen**, each with a button to the next step:
  - S4: "No saved strategies yet. [Create Strategy]".
  - S6: "No orders yet."
  - S7: "No open positions."

**Rules on every screen:**
- Colour plus a word on every status chip, including the 7 order status words.
- 44 px tap targets.
- Only one sticky bar visible at a time on a phone.
- At Guided level: plain glosses ("LIMIT (price you set)"), basket tags hidden, and "Today's estimate" as the visible
  label for Estimated Now.
- **"Check with Zerodha" keeps its spec wording** (REQ-073, F-41). The first-visit hint explains it once. (A reviewer's
  suggestion to rename it was rejected for that reason; a gloss is added instead.)

**Screen-specific additions:**
- **S5 reading order:** one plain sentence first ("You will place 2 buy orders now; worst case loss ₹5,900"), then
  margin and charges, then the order table, collapsed on a phone.
- **S1 acceptance:** the menu item, "Open in Strategy Builder" from S2, and the S3 result cards all open the same page.
- **S9 acceptance:** clicking an alert row goes to Live Position, then Adjustment, then Execute. Back never leaves the
  strategy. If S10 isn't built yet, the link goes to the Live Position tab's own button, never to a placeholder.
- **Every action button has a destination:** "Reconcile" and "Group into a strategy" on S7, and "Duplicate" on S4. On
  an executed strategy, S4 shows "Can't delete: orders were sent" instead of Delete (D5, ADR-118).
- **One end-to-end test of journey 1 at 390 px:** Home, Create Strategy, Builder, Execute, Kite return page, Orders.
  This is a close-out gate.

## Orchestrator decisions

Owner decisions of 2026-10-19 (question tool) that change what a screen shows. Each is written into the spec as an ADR
and REQ text (spec-first R4); this note records only the effect on screens.

| Decision | Effect on screens | Written in |
|---|---|---|
| D3 two baskets | S5 Execute shows basket 1 (protective buys) then, after "Check with Zerodha" confirms the fills, basket 2 (the sells), re-priced fresh with the new max loss and credit shown before Kite opens; S6 Orders and the Live Position tab show the stepper and the two middle-state sentences; "Complete Strategy" on S6 builds basket 2; Kite is never re-opened for a basket whose tagged orders exist | ADR-117; REQ-056 AC-4, AC-11; REQ-073 |
| D4 no what-if sliders in V1 | S1 Builder keeps the two-mode toggle (At Expiry / Estimated Now) and no spot / IV / days slider, although Sensibull, TradingView and OptionStrat have them | ADR-120; REQ-034 AC-6 unchanged |
| D5 delete only never-executed drafts | S4 My Strategies shows Delete (confirm + Undo) on drafts only; the deleted draft is hidden everywhere and kept for audit; a strategy that ever sent a basket shows "Can't delete: orders were sent" | ADR-118; REQ-070 AC-6 |
| D8 market hours | S5 Execute disables its action outside 09:15-15:30 IST on NSE trading days with "Market closed. You can review your plan; execution opens at 09:15 on <next trading day>."; planning, the Builder and saving keep working; the holiday list is dated data | ADR-119; REQ-056 AC-12 |

Also settled, with effects on screens: D2 (ADR-116) lets S7 Positions offer one audited "Kite flat, mark exited for
every holder" action for a shared contract that Zerodha shows flat (any non-flat state stays blocked); D7 (ADR-120)
keeps a mismatch badge sticky on S7 until a recorded resolution. D6 (Google sign-in and sign-out out of this plan)
makes S12 the public landing and FAQ only and keeps A9 as `stage-5` rows. S13 stays shells while ADR-055 holds.
