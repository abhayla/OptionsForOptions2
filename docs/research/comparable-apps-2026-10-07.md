# Comparable apps: how they work, what they charge, what they are registered as (2026-10-07)

Stage 1 research, streams S2a and S2b (master plan 2026-10-07). This file is the narrative and the comparison matrix;
the record is `spec/findings.md` (F-13 to F-16, F-22, F-24). All pages read 2026-10-07, public pages only, no logins.

**How to read the cells.** Each cell says where it came from: **P1** = the company's own page, terms, docs or a
regulator/exchange document; **P2** = the company's blog or help; **P3** = third party (unverified); **Inf** =
inferred from a page element. **✔** = re-read from raw text by the orchestrator; cells without ✔ are the research
agent's reading, not re-checked. "unknown (tried …)" means it was looked for and not found in the time box.

## 1. Matrix

| App (operator) | What it does | Orders reach the broker how | Brokers | Data source | Price | Regulatory status (checked) | SEBI/exchange action |
|---|---|---|---|---|---|---|---|
| **Sensibull** (Riskilla Software Technologies Pvt Ltd) | Strategy builder (25+ templates), payoff and Greeks, positions, basket orders, draft portfolios, option chain, OI charts, "mindful trading" pause (P1) | Through the broker's login; Zerodha describes it as Kite API integration (P3, 2019); re-login frequency unknown | Multi; Zerodha plus others (names in images; P3 list unverified) | Signed-out chain: "Login with your broker for real-time prices" (P1) | Free plan; "Pro Plan ₹0 /month" on the Zerodha tab ✔ (P1); others unverified | **SEBI RA INH200006895 = RISKILLA SOFTWARE TECHNOLOGIES PRIVATE LIMITED, valid 30 Jul 2025 - 29 Jul 2030** ✔ (SEBI register) | none found (search, not exhaustive) |
| **Streak** (Streak AI Technologies Pvt Ltd) | Rule-based strategies, scanners, backtests, scalper (P1) | Terms say Streak does not auto-trade; orders placed manually by the user (P1 per agent; ✘ page did not load for the orchestrator - **not re-checked**) | Zerodha ("Login with Kite", Inf) | "authorized third-party providers" (P1, agent) | Free (title); fair-use caps (P1, agent) | Says it is not a broker, IA or RA (P1, agent) | none found |
| **Tradetron** (Neutrino Trading Pvt Ltd, per SEBI) | No-code algo bots, strategy marketplace, "Live Offline" simulation (P1) | "fire orders straight into your account" via broker API (P1) | 100+ brokers (P1) | unknown | ₹0 to ₹7,500/month by bots (P1) | none stated | **SEBI examined "TradeTron and other algo platforms"; a broker associated with it fined ₹2,00,000 on 25 Mar 2026** ✔ (F-15) |
| **Opstra** (Definedge Securities, a broker) | Builder, backtester, simulator, chain with Greeks (P1) | Likely through Definedge's own broking (Inf/P3) | Definedge only (P3) | Free 15-min delay, paid real-time (P3) | Free app; Pro price unknown | Broker reg. INZ000301132 (P1 app listing) | none found |
| **Quantsapp** (Quantsapp Pvt Ltd; RA proprietor) | 106+ tools, optimizer, repair, chain, builder with margin, alert orders (P1) | Native execution with the user's broker; FAQ says static IP is mandatory; sells "Static-IP execution from ₹250 a month" (P1) | 20+ brokers (P1) | Footer: "NSE authorised real-time data vendor (F&O)" (P1 link text) | Free; PRO ₹19,999/yr; PRO+ ₹39,999/yr (P1) | RA INH000006332 held by an individual proprietor, not the company (P1 disclaimer) | none found |
| **AlgoTest** (Oraph Pvt Ltd) | Backtests, forward tests, live algo, signals, RA-algo marketplace (P1) | User pastes own broker API key/secret (P1/P2) | "70+ brokers" (P1) | not stated | Credits: ₹499-₹14,999 packs; live algo 100 credits per 28 days (P1) | **NSE empanelled algo provider, White Box, "on provisional basis", NSE/INVG/71820, 16 Dec 2025** ✔ (F-14) | none found |
| **Dhan Options Trader** (Raise Securities, a broker) | Chain with orders, 10+ strategies, payoff (P1) | Broker's own app (P1) | Dhan only | Own feed; signed-out "delayed by 15 mins, login to check live prices" ✔ | Free; ₹20/order (P1) | Broker INZ000006031; RA INH000023357 (P1 footer) | none found |
| **Upstox** (broker) | Option chain with Greeks, IV, PoP; strategy selector (P1) | Broker's own app | Upstox | Signed-out "Price is delayed" (P1) | - | Broker INZ000315837 (P1) | Parent RKSV: SEBI settlement order 3 Nov 2023 (P1; terms not read) |
| **Angel One** (broker) | Strategy builder through a Sensibull partnership (P2) | Broker; Sensibull for strategies | Angel One | Own feed | - | Broker, RA INH000000164, IA INA000008172 (P1 footer) | SEBI adjudication, ₹6,00,000, technical glitches and APs (P1, agent read the order) |
| **OpenAlgo** (open source) | Self-hosted multi-broker API bridge, 36 broker plugins (P1) | Runs on the trader's own machine with the trader's own API key; "single-user tool, not a multi-tenant SaaS" (P1) | 34 securities brokers (P1) | User's broker feed | Free | Not a registered entity (P1). **Licence AGPL-3.0** ✔ (F-13) | none found |

## 2. Option-chain screens (cell 13)

| App | Columns seen | Signed out |
|---|---|---|
| Upstox | LTP, Delta, Gamma, Theta, Vega, IV, Volume, OI, PoP; strategy selector; data download (P1) | delayed |
| Dhan | not read (signed-in only) | "delayed by 15 mins" ✔ |
| Sensibull | not visible | login prompt only (P1) |
| Opstra | Price, Volume, OI, Greeks per page copy (P1) | blank page |
| Angel One | LTP, change, OI, OI change %, volume, IV, Greeks (P2 snippet) | unknown |
| Quantsapp | OI change, Delta, LTP, strike on a labelled "sample data" demo (P1) | demo only |

Pattern: no one shows a live chain to signed-out visitors; brokers show a delayed one (F-16).

## 3. How they handle SEBI's 2025 algo rules

- **Streak** stopped executing at all (orders placed manually; agent-read terms, not re-checked).
- **Quantsapp** sells static-IP execution and calls multi-leg execution "non-algo" (P1, its own claim).
- **AlgoTest** became an empanelled white-box provider (provisional) ✔.
- **OpenAlgo** stays single-user and self-hosted; the trader brings their own static IP (P1).
- **Brokers' own apps** (Dhan, Upstox, Angel One) are the broker's front end and outside the vendor rules.

Our product sits where these rules bite hardest: a hosted multi-user service preparing orders for many users (F-17,
F-18, Q259).

## 4. What to copy and what to avoid (opinion, labelled)

- **Copy:** a "mindful trading" confirmation before execution (Sensibull); a free tier with named limits; a simulation
  mode that places no orders (Tradetron "Live Offline"); showing payoff, Greeks and margin before sending to the broker
  (Quantsapp); labelling sample data clearly.
- **Avoid:** "winning strategies", "best-fit", "Rank 1" or return wording (F-15, F-25, ADR-003); any marketplace of
  third-party strategies with return claims (the exact case SEBI penalised); "Exchange Empanelled" wording without
  "provisional"; forcing users to open a new broker account.

## 5. Gaps (not closed in the time box)

- Opstra's own pricing and chain pages (blank signed out); Sensibull's re-login frequency and its non-Zerodha price.
- Streak's terms page did not load for the orchestrator - its "no execution" claim is not re-checked.
- NSE's full list of empanelled algo providers (page loads by script); BSE's list.
- SEBI order searches were web searches restricted to sebi.gov.in, not SEBI's order database: "none found" is a check,
  not proof.
- Raw files: session scratchpad `raw/S2a`, `raw/S2b` (not committed: third-party pages).
