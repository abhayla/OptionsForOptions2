# Surprise register (Stage 1, 2026-10-07)

Every risk found in Stage 1 that could block or reshape the product. Facts are in `spec/findings.md`; decisions are
asked in Stage 2 one at a time. Impact words: **blocks core** (Stage 4 cannot finish as designed), **blocks launch**,
**reshapes feature**, **adds cost**, **none**.

| SR | Risk, in one line | Findings | Impact | Owner decision? | Question |
|---|---|---|---|---|---|
| SR-01 | Our server sending a user's confirmed orders through the Kite API makes them "algo orders"; we would need exchange empanelment and broker-hosted strategies | F-17, F-18, F-11, F-12 | **blocks core** (Stage 4b as designed) | yes | Q259 |
| SR-02 | One static IP may serve one client or one family only, so one server cannot place orders for many unrelated users | F-12, F-19 | **blocks core** (same path as SR-01) | yes | Q259, Q258 |
| SR-03 | Zerodha's free "offsite order execution" (user places our read-only basket on Kite's own page) may avoid SR-01/02, but its algo status is unconfirmed | F-22 | reshapes feature (execution UX) | yes (after Zerodha answers) | Q259 |
| SR-04 | Live option prices cannot be shown to signed-out visitors without an NSE/BSE licence; even 15-min delayed data is a paid product | F-23, F-16 | reshapes feature (public site, REQ-010) / adds cost | no (REQ-010 AC-1 already says no live data without login) | - |
| SR-05 | Showing a connected user's own Kite data inside our SaaS needs Zerodha's written permission and possibly exchange approval | F-23 | **blocks core** at launch (Stage 4a proof on the owner's own account is not affected) | yes | Q210, Q204 |
| SR-06 | Exchange contract numbers are reused after expiry; our stored identity (segment, number) can later point at another contract | F-21 | **blocks core** data integrity (before 4a stores strategies) | yes | Q262 |
| SR-07 | An Authorised Person may not charge clients and may not give incentives for account opening or subscription plans: free Pro for the owner's clients, referral rewards and the owner selling Pro are exposed | F-26 | **blocks launch** (Stage 8 business model) | yes | Q260 |
| SR-08 | Suggested setups, strike and adjustment suggestions on a paid plan may count as "research" needing RA registration | F-24, F-25 | reshapes feature / **blocks launch** of those features | yes | Q261 |
| SR-09 | Any past or expected return shown for a strategy exposes Zerodha and the owner (a broker was fined over TradeTron) | F-15, F-25 | reshapes feature (simulation, REQ-051; wording, REQ-005) | yes | Q261 |
| SR-10 | DPDP Rules apply from 13 May 2027 (72-hour breach report, 1-year logs); CERT-In 6-hour reports and 180-day logs apply now | F-27 | adds cost (requirements in Stage 3) | no | - |
| SR-11 | Payment gateways list "securities ... related financial products" and the bank may refuse; e-mandate and GST rules apply | F-28 | adds cost / risk at Stage 8 | no (requirement in Stage 3) | - |
| SR-12 | Ads on Google/Meta for an investment-related product need verification and SEBI registration or exemption | F-28 | adds cost (marketing) | no | - |
| SR-13 | A live contract's strike can change under the same number (corporate actions) | F-21 | reshapes feature (catalogue history; Q257 already keeps revised terms with history) | no | - |
| SR-14 | Kite's websocket caps (3,000 instruments x 3 connections per API key) would cap the whole app if one platform key were shared | multi-broker doc §4 | none under per-user keys (ADR-014) | no | Q204 |
| SR-15 | Comparable apps either stopped executing (Streak, agent-read), became empanelled (AlgoTest, provisional), are brokers themselves (Dhan, Upstox, Angel One) or are single-user self-hosted (OpenAlgo) - none is a hosted multi-user order router without empanelment | comparable-apps doc §3, F-14 | context for Q259 | no | Q259 |
| SR-16 | OpenAlgo's code is AGPL-3.0; copying it would force our backend open | F-13 | none (decision already "ideas only") | no | - |

Count: 16 risks; 9 need an owner decision across 6 questions (Q204, Q210, Q258-Q262 overlap as listed).
