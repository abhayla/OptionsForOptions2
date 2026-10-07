# Compliance research: algo rules, F&O rules, advice, data, privacy, Authorised Person rules, payments (2026-10-07)

Stage 1 research, streams S1a and S1b plus the orchestrator's core proof (master plan 2026-10-07). Narrative only; the
record is `spec/findings.md` F-11, F-12, F-15, F-17 to F-20, F-22 to F-28, and questions Q258 to Q262. **This is a
reading of primary texts, not a legal opinion**; Q211's legal review still decides.

## 1. Verdict per hypothesis

| # | Hypothesis | Verdict | Findings |
|---|---|---|---|
| H1 | Live prices cannot be shown freely | **Proven for signed-out visitors** (SEBI bars sharing real-time prices with platforms; NSE bars redistribution without an agreement; even 15-minute-delayed data is a paid NSE product; "education" needs data 30 days old from 1 Jul 2026). **Unknown for a connected user's own Kite data**: Kite's terms allow platforms for other Zerodha clients "after obtaining the required exchange approvals". | F-16, F-23 |
| H2 | Zerodha's terms beyond Q210 | **Proven**: Kite terms bar public display/redistribution of API content; allow platforms for Zerodha clients after exchange approvals; "not meant for placing fully automated trades (without manual intervention)"; Kite Connect for startups is free for mass-retail platforms ("Do you need approvals? Yes" - agent read). | F-22, F-23 |
| H3 | Suggested setups may need RA registration | **Partly proven, real risk**: the RA definition covers "any other service of similar nature or character"; no tool exemption; Sensibull's operator is a registered RA. No SEBI ruling on tools found. | F-24 |
| H4 | Association rules limit the owner and Zerodha | **Proven**: agents include APs; association includes "interaction of information technology systems"; no association with platforms referring to past or expected algo returns; a broker was fined over TradeTron. | F-15, F-25 |
| H5 | Our order path is "algo" | **Proven on the text**: every API order is an algo order even if user-confirmed; providers must be empanelled; strategies run on the broker's servers; static IP one client/family; in force for all brokers from 1 Apr 2026. | F-11, F-12, F-17, F-18, F-19 |
| H6 | DPDP duties | **Proven**: operative rules from 13 May 2027; breach report within 72 hours; logs kept 1 year. | F-27 |
| H7 | Contract numbers are reused | **Proven on data**: 4,768 of 65,265 NSE numbers reused within two months; Zerodha docs agree. | F-21 |
| H8 | SEBI F&O rules reshape the product | **Proven, compatible**: one weekly expiry per exchange (NIFTY Tuesday, SENSEX Thursday), lots 65 and 20, upfront premium, extra margin on expiry day. Nothing found that bans weekly index options (no consultation found - weak check). | F-20 |
| H9 | Payments | **Partly proven**: Razorpay lists "Securities ... related financial products" and bank discretion; RBI e-mandate ₹15,000 and 24-hour notice; GST registration above ₹20 lakh. SaaS GST rate unknown. Not re-read by the orchestrator. | F-28 |
| H10 | Other launch rules | CERT-In 6-hour reports and 180-day logs **proven**; Google/Meta financial-ad verification **proven** (agent read); PaRRVA limits verified past performance to IAs/RAs/algo services; **index-name licensing unknown**. | F-25, F-27, F-28 |
| H11 | AP rules limit selling Pro | **Proven against the plan as written**: an AP "shall not charge any amount from the clients"; no incentives for account opening or subscription plans. A narrower AP rule is only a proposal (6 Aug 2026). | F-26 |

## 2. What this means for the product (plain words)

1. **Placing orders (core, Q259).** Our server sending users' orders through the API makes us an algo provider under
   the 2025 framework: empanelment, broker-hosted strategies, algo IDs. Zerodha's "offsite order execution" (the user
   places our prepared, read-only basket on Kite's own exchange-approved page) is the candidate way around it, free,
   but only Zerodha can confirm it is non-algo.
2. **Showing prices (core, Q210/Q204).** No public live chain. A connected user's own data inside our app needs
   Zerodha's written permission and possibly exchange approval.
3. **Business model (Q260).** Free Pro for clients who opened through the owner, referral rewards for account openings,
   and the owner selling Pro to clients all collide with AP rules as written.
4. **Suggestions (Q261).** Specific strikes, stops and adjustment suggestions on a paid plan may be "research".
5. **Identity (Q262).** Add the expiry to the contract identity before any strategy is stored.
6. **Compatible:** weekly NIFTY/SENSEX options exist; lots 65/20; expiry read from the file (already our rule).

## 3. Sources (all read raw 2026-10-07; files in the session scratchpad `raw/`, not committed)

- SEBI: CIR/2025/0000013 (4 Feb 2025, retail algo); CIR/2025/132 (30 Sep 2025, all brokers from 1 Apr 2026);
  CIR/2024/132 (1 Oct 2024, F&O measures); CIR/2025/76 (expiry days); circular of 24 May 2024 (real-time price data);
  May 2026 circular (30-day lag, forwarded by NSE/COMP/74156); 29 Jan 2025 circular and FAQs (association); RA
  Regulations 2014 consolidated to 25 Nov 2025; IA Regulations; Master Circular for Stock Brokers (17 Jun 2025);
  PaRRVA circular (29 Apr 2026); adjudication order Order/JS/YK/2025-26/32256 (25 Mar 2026); RA register entry
  INH200006895.
- NSE: INVG67858 (5 May 2025, implementation standards); INVG69255 Annexure I (22 Jul 2025, operational modalities);
  FAQ of 3 Nov 2025; INVG70309 (empanelment criteria); INVG71820 and INVG72657 (provisional empanelments); FAOP70616
  (NIFTY lot 65); FAOP60133/FAOP48511 (token ranges); COMP/55482 (Code of Advertisement, 2 Feb 2023); data sharing
  policy, pricing file (Mar 2026), delayed-data tariff, non-display policy; bhavcopies 3 Aug - 6 Oct 2026.
- BSE: notice 20250506-3 (implementation standards); F&O bhavcopies.
- Zerodha: kite.trade/terms, /startups, /docs/connect/v3 (basket, publisher, market-quotes, exceptions); support
  article on static IP.
- Gazette: DPDP Rules 2025 (G.S.R. 846(E)); DPDP Act 2023. CERT-In directions 28 Apr 2022.
- Razorpay terms; RBI e-mandate circulars; CGST Act s.22; Google and Meta ad policies.

## 4. Unknown (tried, not found in the time box)

BSE market-data policy; Asia Index / NSE Indices rules on showing index names and values; SaaS GST rate; DPDP Act
section commencement dates; Cashfree/PayU lists; later revisions of NSE/COMP/55482; RBI 2025 authentication directions;
whether a multi-user SaaS fits the "algos developed through third parties" client route; the white/black-box category
of a user-defined rule strategy; whether Kite offsite (basket) orders are non-algo. SEBI's own texts disagree on the
date of the 30-day education lag (8 May vs 1 Jul 2026).
