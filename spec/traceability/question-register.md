# Question register: Q1–Q203

Built 2026-09-28 by reading both full ChatGPT chats message by message (not the handoff summaries):

- **T1** = `docs/reference/chatgpt/OFO_chat_full_transcript_2026-09-14_to_16.txt` (first account, Q1–Q97, 284 messages)
- **T2** = `docs/reference/chatgpt/OFO_chat2_second_account_full_transcript_2026-09-16_to_28.txt` (second account, Q81, Q98–Q203, 138 messages)

**Who** — *Owner*: you chose the answer or stated the requirement. *ChatGPT (delegated)*: from T2 #83 on you told
ChatGPT to answer small questions itself "from user perspective" and stop only for real decisions; these are its
answers, which you did not object to. *Superseded*: a later owner decision replaced it. `#n` is the message number.

**Warning about the older files:** the handoffs' Q102–Q148 records (the "continuation" file) were reconstructed by
ChatGPT and do **not** match the real questions — e.g. the real Q102 is "Create Strategy start: two paths", the file
says "Market-data architecture". This register replaces them. Q1–Q97 and Q149–Q203 in the handoffs are closer but
lost details (e.g. Q33A–Q33D, Q35, Q60–Q71, Q81).

| Q | Subject | Answer | Who | Where | Spec |
|---|---|---|---|---|---|
| Q1 | Who controls trades | A — assisted first, automation later | Owner | T1 #3 | ADR-009 |
| Q2 | Primary customer | D — beginner + intermediate | Owner | T1 #5 | ADR-004 |
| Q3 | How a user starts | C — strategy-first + manual builder | Owner | T1 #7 | ADR-005 |
| Q4 | Should the system recommend strategies | B — guided strategy discovery (no AI advisor) | Owner | T1 #9 | ADR-005, ADR-003 |
| Q5 | How much to automate | B — alert + prepare orders (V1) | Owner | T1 #11 | ADR-009 |
| Q6 | Which brokers | Zerodha, Angel One, Upstox, Dhan, Groww, Paytm Money → later changed to Zerodha only (T1 #47) | Superseded | T1 #13, #47 | ADR-001 |
| Q7 | Home screen | B — 'What do you want to do?' action-first home | Owner | T1 #15 | ADR-027 |
| Q8 | Instruments | Yes — NIFTY+SENSEX, six leg types, unlimited combinations | Owner | T1 #17 | ADR-001, ADR-006 |
| Q9 | Live market-data source | B — centralized licensed provider + broker APIs for trading (later revised, see Q171/Q177) | Superseded | T1 #19 | ADR-014 |
| Q10 | How users define a strategy | B — guided/conversational builder + Advanced Manual Builder | Owner | T1 #21 | ADR-005 |
| Q11 | Adjustments | B — guided adjustments + prepared orders | Owner | T1 #23 | ADR-011 |
| Q12 | Where strategy creation starts | B — desired outcome first | Owner | T1 #25 | ADR-005 |
| Q13 | Who the product is for | B — public SaaS | Owner | T1 #27 | ADR-001 |
| Q14 | Desktop / mobile | B — responsive web, no native apps | Owner | T1 #29 | ADR-001 |
| Q15 | Calculations | B — own strategy/risk engine | Owner | T1 #31 | ADR-008 |
| Q16 | Strike selection | C — Conservative/Balanced/Aggressive + Manual Custom | Owner | T1 #33 | ADR-005 |
| Q17 | Entry conditions | D — simple conditions + advanced rule builder | Owner | T1 #35 | ADR-009 |
| Q18 | Exit conditions | D — simple V1, compound later ('explicit exit plan' part superseded by Q153) | Owner | T1 #37 | ADR-009 |
| Q19 | Test before real money | B — simple historical simulation | Owner | T1 #39 | ADR-013 |
| Q20 | What monitoring monitors | B — strategy-health monitoring | Owner | T1 #41 | ADR-010 |
| Q21 | How much the main screen shows | D — simple by default, Advanced mode | Owner | T1 #43 | ADR-004 |
| Q22 | Multiple broker accounts | C — several brokers, one per strategy → void after Zerodha-only (T1 #47) | Superseded | T1 #45 | ADR-001 |
| Q23 | Whose account can be traded | Yes — own Zerodha account only | Owner | T1 #49 | ADR-001 |
| Q24 | Existing positions | B — discover + user groups them | Owner | T1 #51 | ADR-018 |
| Q25 | Alert channels | B — in-app + push + email + WhatsApp | Owner | T1 #53 | ADR-028 |
| Q26 | Order execution | Owner input: protective buys first; hard broker-margin gate before any order | Owner | T1 #55, #57 | ADR-016, ADR-017 |
| Q27 | Partial execution | Owner order: Complete → Retry → Review → Close; no auto-unwind | Owner | T1 #61, #63 | ADR-017 |
| Q28 | Order types | Zerodha-specific execution engine, no generic order-type menu (ChatGPT recommended; owner moved on) | ChatGPT (delegated) | T1 #65–#70 | ADR-017 |
| Q29 | Strategy-only vs individual orders | A — strategy-only | Owner | T1 #71 | ADR-002 |
| Q30 | Modify a live strategy | A — controlled strategy modification (+ 'Strategy Guard', owner #73/#75) | Owner | T1 #75 | ADR-002 |
| Q31 | UX model | A — three levels: Guided / Standard / Advanced | Owner | T1 #79 | ADR-004 |
| Q32 | Change UX level | A — any time; safety rules always enforced | Owner | T1 #81 | ADR-004 |
| Q33 | Risk acknowledgement | Owner replaced it with the strategy outcome table requirement (#83–#98); risk UX later as contextual | Owner | T1 #83–#98 | ADR-008 |
| Q33A | Scenario columns: expiry vs current estimate | C — both, Expiry P&L default | Owner | T1 #111 | ADR-008 |
| Q33B | Scenario range | E — intelligent default + user customization | Owner | T1 #113 | ADR-008 |
| Q33C | Scenario anchoring | Owner: 'B + current market price + 0 P&L' — rounded 100-point grid (index points, not ₹) plus current level and breakevens | Owner | T1 #115 | ADR-008 |
| Q33D | Where current/0-P&L columns go | C — inserted at their actual price position | Owner | T1 #117 | ADR-008 |
| Q34 | Option Chain role | B + multi-select checkboxes, 'Add Selected (N)' | Owner | T1 #119 | ADR-007 |
| Q35 | Where Buy/Sell is chosen | C — both chain and Builder; Builder is default | Owner | T1 #121 | ADR-007 |
| Q36 | Quantity | D — lots primary, exact quantity in Advanced | Owner | T1 #123 | ADR-007 |
| Q37 | Chain sets action + lots | B — chain can; Builder is authoritative | Owner | T1 #125 | ADR-007 |
| Q38 | Chain filters | D — adaptive to UX level | Owner | T1 #127 | ADR-007 |
| Q39 | Expiry in chain | C — Builder sets strategy expiry; chain can explore/import another | Owner | T1 #129 | ADR-007 |
| Q40 | Multiple expiries in a strategy | B — allowed | Owner | T1 #131 | ADR-006 |
| Q41 | Mixed-expiry selection | B — confirm 'Multiple expiries detected' | Owner | T1 #133 | ADR-007 |
| Q42 | Same contract selected twice | B — combine into one row | Owner | T1 #135 | ADR-007 |
| Q43 | Same contract, opposite actions | B — separate legs, no netting | Owner | T1 #143 | ADR-007 |
| Q44 | Contract becomes unavailable | D — suggest alternatives, user picks | Owner | T1 #145 | ADR-007, ADR-016 |
| Q45 | Chain default columns | A — clean default + Advanced Details | Owner | T1 #147 | ADR-007 |
| Q46 | Live refresh | C — hybrid streaming | Owner | T1 #149 | ADR-007 |
| Q47 | Selected legs display | B — persistent Selected Legs summary | Owner | T1 #151 | ADR-007 |
| Q48 | Contract already in strategy | C — ask: increase / keep separate / cancel | Owner | T1 #153 | ADR-007 |
| Q49 | Pre-import validation | B — block serious errors, warn otherwise | Owner | T1 #155 | ADR-007 |
| Q50 | Selections across expiry tabs | B — persist | Owner | T1 #157 | ADR-007 |
| Q51 | Template recognition | A — identify and offer, never auto-convert | Owner | T1 #159 | ADR-007 |
| Q52 | Unmatched combination | A — Custom Strategy | Owner | T1 #161 | ADR-006, ADR-007 |
| Q53 | Buy/Sell in chain | A — Buy/Sell buttons on each contract; never inferred | Owner | T1 #163 | ADR-007 |
| Q54 | Changing lots in chain | A — +/- lot stepper | Owner | T1 #165 | ADR-007 |
| Q55 | Chain payoff preview | A — compact live preview | Owner | T1 #167 | ADR-007 |
| Q56 | Removing a selected leg | D — remove + short Undo | Owner | T1 #169 | ADR-007 |
| Q57 | Where adjustment rules live | C — global defaults + per-strategy overrides. (Three earlier Q57s — Undo duration (T1 #170), primary organizing concept strategy-centric/terminal/hybrid (T1 #174), data-provider strategy (T1 #176) — were paused and never answered.) | Owner | T1 #179 | ADR-011 |
| Q58 | Public live data | A — all behind login | Owner | T1 #181 | ADR-027 |
| Q59 | Public site | A — marketing only | Owner | T1 #183 | ADR-027 |
| Q60 | Free via referral | Yes: 1 referral = permanent free → replaced by '1 referral = 1 month Pro' (T1 #189) | Superseded | T1 #185, #189 | ADR-025 |
| Q61 | Successful referral / direct customers | Two meanings under one number. First (T1 #187): what counts as a successful referral — A, account opened + attributed (ADR-025). Then (T1 #191, owner): direct qualifying customers get full Pro free forever (ADR-024) | Owner | T1 #187, #191 | ADR-024, ADR-025 |
| Q62 | Direct customer billing page | Owner: 'You're already on Pro', payment disabled | Owner | T1 #193 | ADR-024 |
| Q63 | Referral stacking | C — admin-configurable, stacking on by default | Owner | T1 #195 | ADR-025 |
| Q64 | Price | A — ₹600/month + discounted annual | Owner | T1 #197 | ADR-026 |
| Q65 | Annual price ₹5,999? | No — annual price admin-defined | Owner | T1 #199 | ADR-026 |
| Q66 | Payment provider | A — Razorpay | Owner | T1 #201 | ADR-026 |
| Q67 | After 7-day trial | A — Limited/Read-Only | Owner | T1 #203 | ADR-023 |
| Q68 | Pro action while Limited | A — contextual upgrade/eligibility message | Owner | T1 #205 | ADR-023 |
| Q69 | Verify direct customers | Owner: admin list of Client IDs + Zerodha official login proves ownership | Owner | T1 #207, #209 | ADR-024 |
| Q70 | Admin customer list | A — CSV bulk + manual | Owner | T1 #211 | ADR-024 |
| Q71 | Login / registration | Owner: Google login + first-time registration profile | Owner | T1 #213 | ADR-021 |
| Q72 | Mobile verification | Owner: WhatsApp OTP via owner's own system | Owner | T1 #215 | ADR-021 |
| Q73 | Email verification | A — Google email counts as verified | Owner | T1 #217 | ADR-021 |
| Q74 | Date of birth | Optional (owner changed A → optional) | Owner | T1 #219, #221 | ADR-021 |
| Q75 | Location | Optional | Owner | T1 #221 | ADR-021 |
| Q76 | Market experience list | OK — five levels | Owner | T1 #223 | ADR-021 |
| Q77 | Profession list | OK | Owner | T1 #225 | ADR-021 |
| Q78 | Navigation | OK | Owner | T1 #227 | ADR-027 |
| Q79 | When to connect Zerodha | A, revised: fully optional until a broker-dependent function | Owner | T1 #229, #233 | ADR-020 |
| Q80 | After registration | Revised B — open Home directly, no checklist | Owner | T1 #231–#233 | ADR-020, ADR-027 |
| Q81 | Home dashboard | C — hybrid: adapts to new / no active / active-strategy users | Owner | T2 #3 | ADR-027 |
| Q82 | Same Client ID, second Gmail | C — block; offer verified transfer; no second trial | Owner | T1 #237 | ADR-022 |
| Q83 | Transfer verification | D — hybrid auto + admin review | Owner | T1 #239 | ADR-022 |
| Q84 | Shared Client ID | A — one Client ID, one platform account | Owner | T1 #241 | ADR-022 |
| Q85 | Change email | A — allowed in same account | Owner | T1 #243 | ADR-021 |
| Q86 | Old email | A — stops being a login immediately | Owner | T1 #245 | ADR-021 |
| Q87 | Multi-account abuse | A — basic only | Owner | T1 #247 | ADR-022 |
| Q88 | Trial start | A — at registration | Owner | T1 #249 | ADR-023 |
| Q89 | Active strategy after trial | A — keeps being monitored | Owner | T1 #251 | ADR-023 |
| Q90 | Paid Pro expiry | A — same Limited model, no grace | Owner | T1 #253 | ADR-023 |
| Q91 | Live chain when Limited | A — no | Owner | T1 #255 | ADR-023 |
| Q92 | Chain screen when Limited | A — Pro gate + 'Sample · Not Live' preview | Owner | T1 #257 | ADR-023 |
| Q93 | History after expiry | A — kept indefinitely | Owner | T1 #259 | ADR-023 |
| Q94 | Disconnecting Zerodha | A — strategy kept; broker features off | Owner | T1 #261 | ADR-020 |
| Q95 | Reconnecting same Client ID | A — restore association | Owner | T1 #263 | ADR-022 |
| Q96 | Account deletion | A — keep minimal anti-abuse record | Owner | T1 #267 | ADR-022 |
| Q97 | Trial without Zerodha | A — per platform account, basic controls | Owner | T1 #269 | ADR-022 |
| Q98 | Market-data vendor architecture | C — vendor-agnostic from day 1 | Owner | T2 #5 | ADR-012 |
| Q99 | Historical data source | C — live vendor's history if enough, else separate provider | Owner | T2 #7 | ADR-013 |
| Q100 | Simulation depth | C — EOD default, intraday later | Owner | T2 #9 | ADR-013 |
| Q101 | Simulation data granularity | C — flexible; daily close for V1. Owner: simulation is lower priority | Owner | T2 #11 | ADR-013 |
| Q102 | Create Strategy start | C — two paths: Guided / Advanced Manual | Owner | T2 #13 | ADR-005 |
| Q103 | Guided suggestions | C — 2–4 shortlist + 'See more' | Owner | T2 #15 | ADR-005 |
| Q104 | Strategy card | C — layered card | Owner | T2 #17 | ADR-005 |
| Q105 | Market-view input | C — simple first, optional detail | Owner | T2 #19 | ADR-005 |
| Q106 | 'Not sure' view | C + owner refinement: expected lower/upper range for a chosen expiry | Owner | T2 #21 | ADR-005 |
| Q107 | Expiry selection | C — real expiry dates with labels | Owner | T2 #23 | ADR-005 |
| Q108 | Range entry | Owner: pick lists, 100-point steps | Owner | T2 #25 | ADR-005 |
| Q109 | Invalid range | Owner: lower list = current and below; higher list = current and above | Owner | T2 #27, #29 | ADR-005 |
| Q110 | Default range | C — both start at current level | Owner | T2 #31 | ADR-005 |
| Q111 | After range chosen | C — summary + strategies together | Owner | T2 #33 | ADR-005 |
| Q112 | How many strategies | Owner: use preferred strategy types to pick valid setups | Owner | T2 #35 | ADR-032 |
| Q113 | No valid preferred setup | B — preferred first, alternatives second | Owner | T2 #37 | ADR-032 |
| Q114 | Where preferences are set | B — onboarding + Settings | Owner | T2 #39 | ADR-032 |
| Q115 | Preference priority | A — all equal | Owner | T2 #41 | ADR-032 |
| Q116 | Preference UI | C — visual strategy library | Owner | T2 #43 | ADR-032 |
| Q117 | Which strategies listed | C — all, labelled Beginner/Intermediate/Advanced | Owner | T2 #45 | ADR-032 |
| Q118 | On selecting a preference | C — interactive understanding before saving | Owner | T2 #47 | ADR-032 |
| Q119 | Setups per preferred type | C — curated Conservative/Balanced/Aggressive + 'View more' | Owner | T2 #49 | ADR-005 |
| Q120 | Setup presentation | C — layered setup cards | Owner | T2 #51 | ADR-005 |
| Q121 | 'Why this setup' | C — layered explanation | Owner | T2 #53 | ADR-005 |
| Q122 | Comparing setups | C — one at a time + Compare | Owner | T2 #57 | ADR-005 |
| Q123 | Choosing a setup | C — load into Builder as 'Suggested Setup' | Owner | T2 #59 | ADR-005 |
| Q124 | Editing a suggestion | C — fully editable, recalculated live | Owner | T2 #61 | ADR-005 |
| Q125 | Edited outside original range | C — inform + keep/update range/continue | Owner | T2 #63 | ADR-005 |
| Q126 | 'Continue anyway' | C — risk/context summary + acknowledgement | Owner | T2 #65 | ADR-005 |
| Q127 | Keep original assumptions | C — as strategy context + audit history | Owner | T2 #67 | ADR-005, ADR-019 |
| Q128 | Preferences after selection | B — guidance only | Owner | T2 #69 | ADR-032 |
| Q129 | When to show preference alternatives | B — at meaningful changes | Owner | T2 #71 | ADR-032 |
| Q130 | Meaningful change | C — structural or material risk change | Owner | T2 #73 | ADR-032 |
| Q131 | Alternative display | C — persistent area + notification | Owner | T2 #75 | ADR-032 |
| Q132 | Clicking an alternative | C — preview first | Owner | T2 #77 | ADR-032 |
| Q133 | Current strategy while reviewing | C — stays active; alternative in preview | Owner | T2 #79 | ADR-032 |
| Q134 | 'Use this setup' | C — replace, keep previous as history | Owner | T2 #81 | ADR-019 |
| Q135 | History presentation | A — simple activity history | ChatGPT (delegated) | T2 #86 | ADR-019 |
| Q136 | Restore earlier configuration | Yes | ChatGPT (delegated) | T2 #86 | ADR-019 |
| Q137 | Current config on restore | Preserved | ChatGPT (delegated) | T2 #86 | ADR-019 |
| Q138 | History after execution | Kept | ChatGPT (delegated) | T2 #86 | ADR-019 |
| Q139 | History on main screen | No — secondary | ChatGPT (delegated) | T2 #86 | ADR-019 |
| Q140 | Next Builder step | Entry + Adjustment + Exit rules | ChatGPT (delegated) | T2 #86 | ADR-009 |
| Q141 | Must all rules be defined | No — guided, not blocking | ChatGPT (delegated) | T2 #86 | ADR-009 |
| Q142 | Suggest rules | Yes — suggest, don't impose | ChatGPT (delegated) | T2 #86 | ADR-009 |
| Q143 | Auto-activate suggested rules | No — explicit confirmation | ChatGPT (delegated) | T2 #86 | ADR-009 |
| Q144 | Default rule templates | Yes | ChatGPT (delegated) | T2 #86 | ADR-009 |
| Q145 | Rule UI by level | Adaptive to UX level | ChatGPT (delegated) | T2 #86 | ADR-009 |
| Q146 | AND/OR | Yes | ChatGPT (delegated) | T2 #86 | ADR-009 |
| Q147 | Rule complexity | Controlled in V1 | ChatGPT (delegated) | T2 #86 | ADR-009 |
| Q148 | When a rule triggers | Explain + prepare; user decides | ChatGPT (delegated) | T2 #86 | ADR-009 |
| Q149 | Monitor without adjustment rules | C — detect opportunities, labelled as platform-detected | Owner | T2 #87 | ADR-011 |
| Q150 | Where monitoring lives | Both: Strategy (plan) + Live Position | ChatGPT (delegated), owner-raised (owner asked at T2 #87 "Where should the monitoring happen?"; answer and lock are ChatGPT's, T2 #88/#90; the owner's "C" at T2 #89 answered Q153, not Q150) | T2 #87–#90 | ADR-010 |
| Q151 | Define exit/adjustment in strategy | Yes | Owner | T2 #87–#90 | ADR-009 |
| Q152 | Adjustments tied to monitoring | Yes | Owner | T2 #87–#90 | ADR-011 |
| Q153 | Exit/adjustment plan required | C — both optional | Owner | T2 #89 | ADR-009 |
| Q154 | Monitor without exit rule | Yes | ChatGPT (delegated) | T2 #90 | ADR-010 |
| Q155 | Suggest an exit rule | Yes, once, non-nagging | ChatGPT (delegated) | T2 #90 | ADR-009 |
| Q156 | One Strategy Plan view | Yes | ChatGPT (delegated) | T2 #90 | ADR-010 |
| Q157 | Plan editable after execution | Yes, with history | ChatGPT (delegated) | T2 #90 | ADR-002 |
| Q158 | Same numbers on Strategy and Position | Shared engine, different presentation | ChatGPT (delegated) | T2 #90 | ADR-010 |
| Q159 | Risk area, no user rule | B — warning + generic approaches | Owner | T2 #91 | ADR-011 |
| Q160 | Opportunity panel | Asked twice. First (T2 #92): approach names / names + brief explanation / exact strikes — B, names + explanation, no exact strikes (folded into REQ-045 AC-5, REQ-046 AC-3). Then (T2 #98): the four-layer panel | ChatGPT (delegated) | T2 #92, #98 | ADR-011 |
| Q161 | Adjustment metric history | Yes | ChatGPT (delegated) | T2 #100 | ADR-013 |
| Q162 | Leg + strategy data | Yes | ChatGPT (delegated) | T2 #100 | ADR-013 |
| Q163 | Underlying data alone | Yes | ChatGPT (delegated) | T2 #100 | ADR-013 |
| Q164 | Add metrics later | Yes | ChatGPT (delegated) | T2 #100 | ADR-013 |
| Q165 | Collect without rules | Yes | ChatGPT (delegated) | T2 #100 | ADR-013 |
| Q166 | Data Feasibility Test | Yes — mandatory (after owner's scale challenge #101) | ChatGPT (delegated) | T2 #101–#102 | ADR-012 |
| Q167 | Raw data first | Yes | ChatGPT (delegated) | T2 #102 | ADR-012 |
| Q168 | Full tick history | No — four storage tiers | ChatGPT (delegated) | T2 #102 | ADR-013 |
| Q169 | Build history from live feed | Yes | ChatGPT (delegated) | T2 #102 | ADR-013 |
| Q170 | Per-user calculation | No — shared once | ChatGPT (delegated) | T2 #102 | ADR-012 |
| Q171 | Authoritative live data source | Licensed NSE-authorized vendor; owner #107: Zerodha only for orders/positions → later overridden by owner #121 | Superseded | T2 #106–#107 | ADR-014 |
| Q172 | Live-data level to buy / Do TrueData/GFDL cover our needs | Used twice. First (T2 #106): what level of live data to buy — V1 buys no tick-by-tick or full order-book (L2/L3) data unless a demonstrated requirement needs it. Then (T2 #108): TrueData/GFDL technically yes; commercial rights unconfirmed | ChatGPT (delegated) | T2 #106, #108 | ADR-014 |
| Q173 | Vendor checklist first | Yes | ChatGPT (delegated) | T2 #108 | ADR-014 |
| Q174 | Which TrueData plan | Not Velocity; custom commercial API quote | ChatGPT (delegated) | T2 #110 | ADR-014 |
| Q175 | Ask TrueData for quote | Yes — owner emailed TrueData | Owner | T2 #110–#113 | ADR-014 |
| Q176 | Email GFDL | Drafted; owner to send to GFDL sales | Owner | T2 #113–#114 | ADR-014 |
| Q177 | Data options / interim source | First: don't abandon live data, contact NSE (T2 #118). Then owner #121: Zerodha live data as interim — PROVISIONAL until Zerodha confirms in writing | Owner | T2 #118, #121–#122 | ADR-014 |
| Q178 | Single NSE+BSE source / Zerodha setup guide | First: NSE+BSE is a hard requirement (T2 #120). Then: build a guided Zerodha setup feature | Owner | T2 #120, #122 | ADR-014, ADR-020 |
| Q179 | Zerodha permanent data provider? | No — gateway stays vendor-independent | ChatGPT (delegated) | T2 #122 | ADR-014 |
| Q180 | Historical data optional | Yes — disabled/deferred in V1 | Owner | T2 #121–#122 | ADR-013 |
| Q181 | Zerodha connection status | Four separate statuses with guided recovery | ChatGPT (delegated) | T2 #124 | ADR-020 |
| Q182 | Disconnected during monitoring | Pause monitoring; never use stale data | ChatGPT (delegated) | T2 #124 | ADR-015 |
| Q183 | Auto-reconnect | Yes; never auto-executes | ChatGPT (delegated) | T2 #124 | ADR-020 |
| Q184 | Partial data outage | Per-strategy availability | ChatGPT (delegated) | T2 #124 | ADR-015 |
| Q185 | Zerodha before strategy creation | No | ChatGPT (delegated) | T2 #126 | ADR-020 |
| Q186 | Draft without Zerodha | Allow; unlock after connection | ChatGPT (delegated) | T2 #126 | ADR-020 |
| Q187 | Auto-activate on connect | No | ChatGPT (delegated) | T2 #126 | ADR-020 |
| Q188 | Recalculate draft on live data | Yes; never redesign | ChatGPT (delegated) | T2 #126 | ADR-020 |
| Q189 | Definition vs live state | Separate | ChatGPT (delegated) | T2 #128 | ADR-019 |
| Q190 | Strategy versions | Yes | ChatGPT (delegated) | T2 #128 | ADR-019 |
| Q191 | Proposed vs active version | Active only after execution + reconciliation | ChatGPT (delegated) | T2 #128 | ADR-019 |
| Q192 | Partial adjustment execution | Exception state; broker wins | ChatGPT (delegated) | T2 #130 | ADR-017 |
| Q193 | Auto retry | No | ChatGPT (delegated) | T2 #130 | ADR-017 |
| Q194 | Order vs strategy status | Separate but linked | ChatGPT (delegated) | T2 #130 | ADR-017 |
| Q195 | Wait for broker confirmation | Yes | ChatGPT (delegated) | T2 #130 | ADR-017 |
| Q196 | Continuous reconciliation | Yes | ChatGPT (delegated) | T2 #130 | ADR-018 |
| Q197 | Changes outside platform | Detect and require reconciliation | ChatGPT (delegated) | T2 #130 | ADR-018 |
| Q198 | Manual reconciliation | Yes, with safeguards and audit | ChatGPT (delegated) | T2 #130 | ADR-018 |
| Q199 | Execute with a mismatch | No | ChatGPT (delegated) | T2 #130 | ADR-018 |
| Q200 | Strategy state machine | Yes — 12 states drive allowed actions | ChatGPT (delegated) | T2 #130 | ADR-019 |
| Q201 | Explain states | Yes | ChatGPT (delegated) | T2 #130 | ADR-019 |
| Q202 | Activity timeline | Yes — immutable | ChatGPT (delegated) | T2 #130 | ADR-019 |
| Q203 | Explain rule triggers | Yes — exact values | ChatGPT (delegated) | T2 #130 | ADR-019 |

**Totals:** 203 numbered questions + 4 sub-questions (Q33A–D). Owner: 144. ChatGPT (delegated): 58. Superseded: 5. Missing: 0.

## Things in the chats that are not a numbered answer
- T2 #84: ChatGPT briefly answered a batch under wrong numbers ("Q35–Q44": review step, Prepare Orders, final safety
  check, execution states, partial-execution screen). You corrected the numbering, not the content. Kept as proposals
  in ADR-017; where they differ from an owner answer (its partial-execution order put Retry first), the owner
  answer (Q27) wins.
- T1 #57, #61, #69, #73, #101, #175, #177, #183, #189, #191, #235, #265 and T2 #93, #101, #107, #119, #121, #131:
  requirements you stated in your own words (margin gate, Zerodha does the filtering, positioning, data first,
  configurable adjustments, commercial model, anti-abuse, daily Zerodha session, adjustment data from a YouTube
  video, scale 5k→500k, Zerodha only for orders, BSE data, Zerodha interim data, core-first build). All are in the spec.
- Paused and never answered: the first Q57 (how long Undo stays, ChatGPT recommended ~5 s) and the second Q57
  (data-provider strategy) — both superseded by later decisions; Undo duration is an open detail.
