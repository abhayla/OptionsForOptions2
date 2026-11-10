# Demo-ready checklist: what Zerodha must see before we reapply (DRAFT for the owner's approval)

Status: **DRAFT, not approved.** Written 2026-11-10 by GC-ICSAFE row c20 (standing direction step 2, card D-02).
The owner approves the content (question filed in `owner-questions-2026-11-11.md`). Until then this list decides
nothing.

Sources: Zerodha's written asks in ticket 403947 (finding F-31 in `spec/findings.md`), and the parts of the product
ADR-060 says must run end to end before the demo ("live data, the engine, saved strategies, the screens, the owner's
own orders through the Kite basket, and monitoring").

How to read the "State today" column: it holds only what was measured, with where the measurement is written.
`unmeasured` means nobody has checked it; the "Proof needed" column then says how to check. No state here is a guess.

## Part A. What Zerodha asked for in writing (F-31)

F-31 lists ten asks. (The plan for this list said nine; the count from the ticket text is ten, so all ten are here.)

| # | What Zerodha must see | State today | Proof needed | Who does it |
|---|---|---|---|---|
| A1 | The complete workflow, and how trades are executed | Not written. The workflow itself is incomplete: real order placing is on hold (ADR-281, 2026-11-09) | A 1-page walk-through: log in, build an iron condor, hand the basket to Kite, the user presses Execute on Kite's own page (ADR-054), watch, adjust, close. Written after row B5 is true | Session drafts; owner approves |
| A2 | The specific use case | Not written as an answer. The product statement exists (`spec/vision/vision.md`) | 5 to 8 lines taken from the vision: decision support for NIFTY/SENSEX option strategies, never advice (ADR-003) | Session drafts; owner approves |
| A3 | Whether the platform is in Production or Beta ("permissions are granted only for production-ready platforms") | Not production: the app runs on one PC and only the owner can log in (review of 2026-11-10, `docs/process/standing-direction.md`) | The app answers at a public link on a host, and a second person logs in and completes rows B1 to B7 | Owner picks the host and spend; session builds (standing direction step 4) |
| A4 | A demo video showing the complete functionality | unmeasured (no video is known; none can be honest before B1 to B7 hold) | One recording of the whole journey on live prices in market hours, with no cut between steps | Owner records; session prepares the script |
| A5 | The website/application link with demo credentials | No link exists (one PC, same source as A3). Demo login: unmeasured | A link that opens from outside this PC, and a demo account that can log in but cannot see the owner's live data (ADR-060: no other user sees live data from the owner's app) | Owner (host, spend); session builds |
| A6 | The API endpoints required (Holdings, Positions, Orders, Portfolio, Trade Book ...) | unmeasured: no list has been taken from the code | A list produced by a search of the Kite adapter for every endpoint it calls, each with why it is needed | Session |
| A7 | Unique and additional features | Not written. The adjustment guidance for iron condor is built on paper (GC-ICGUIDE, merged as PR #687) | A short list with one screen picture each; only features that work in the video | Session drafts; owner approves |
| A8 | Whether use is limited to Holdings, Portfolio, Positions, Order Book and Trade Book | unmeasured: follows from A6 | A yes/no with the A6 list beside it. Market data (A10) is used as well, so the honest answer is expected to be "no", to be confirmed by A6 | Session |
| A9 | A SEBI RA registration number, if the platform "provides investment research, recommendations, or advisory services" | Decided position: decision support, never advice (ADR-003, ADR-055). Whether every text on the screens keeps to it today: unmeasured in this run | The wording checks pass on the release that is recorded, and a one-paragraph statement of why no RA number applies. Any registration the owner holds: owner states it | Owner (the statement is a compliance call); session runs the checks |
| A10 | The market-data endpoints required (Quote, Historical Data, WebSocket) | unmeasured as a list. One WebSocket carried 1,091 instruments in the 2026-10-08 live check (F-32) | A list from the feed code: which of Quote, Historical, WebSocket are called, how many instruments, how often | Session |

Also in the ticket: "If required, we will schedule a demo call", and the ticket was closed on 2026-10-01, so
reapplying needs it reopened or a new one. Both are the owner's steps.

## Part B. What must work on screen first (ADR-060, and the goal sentence of the standing direction)

| # | What Zerodha must see | State today | Proof needed | Who does it |
|---|---|---|---|---|
| B1 | A person who is not the owner opens the link and logs in | Not possible: only the owner can log in (standing direction, 2026-11-10) | A second person logs in from their own device | Session builds (step 4); owner names the tester |
| B2 | Live market data on the option chain and the builder | Works on the owner's account on this PC (live days 2026-11-02 and 2026-11-04 in the handovers). On a host: unmeasured | Chain and builder show prices with their time on the hosted app, in market hours | Session |
| B3 | Build an iron condor and save it (builder, My Strategies) | Works on paper on this PC (GC-ICGUIDE). With live prices at four expiries: not yet run (rows c10, c11 of this contract) | Rows c10 and c11 done with screenshots | Session |
| B4 | Every P&L and payoff number comes from one engine | Decided and built (ADR-008). Not re-measured in this run: unmeasured | The engine test suites green on the recorded release | Session |
| B5 | The strategy goes to the broker as a real order: basket to Kite, the user presses Execute, the app reads back what was executed | On hold (ADR-281). Never run end to end for a full iron condor | Every leg of one real iron condor at 1 lot submitted, executed and matched with 0 mismatches (standing direction step 4) | Owner lifts ADR-281 and presses Execute; session builds and reads back |
| B6 | Monitoring with no screen open: the loss alarm and the other rules are checked in the background | The margin-based loss alarm was NOT checked on any strategy on the live day 2026-11-04 (#627: 143 log lines "not checked"). Fix is in this contract (rows c22 to c24, proof c40) | One live day where the worker log shows the alarm checked on every open strategy and 0 "not checked for missing margin" lines | Session |
| B7 | Adjust and close a strategy from the screens | Works on paper for iron condor (GC-ICGUIDE). For a real position: never run | One adjustment and one close on the B5 position, each read back from the broker | Owner presses Execute; session |
| B8 | The app keeps working without a hand-push | Three known failures, each measured: the daily contract list is refused until forced (#680), two screens hang when database connections are short (#682), every day from 1 Jan 2027 reads as closed (#686). Fixes are in this contract | Three days of the daily refresh with no force; both screens answer with one connection; a 2027 date is named as "no calendar", and the 2027 list is loaded in December | Session; owner loads the 2027 list |
| B9 | The owner is told when the background watcher stops | Not built (#627 item 3). In this contract (rows c25 to c27) | One real test warning received on the owner's phone, and a stopped watcher raises one warning | Session |

## What this list does not cover

More strategy types (standing direction step 5), SENSEX, billing, and anything Zerodha did not ask for.
