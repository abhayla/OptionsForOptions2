# Owner questions and notes, GC-ICSAFE (opened 2026-11-10 evening for the 11 Nov run)

Plain words first. Each entry says what is asked, what I recommend and why. Nothing here blocks the run.

## Q1. Please approve the demo-ready checklist (standing direction step 2)

**What it is:** `docs/process/demo-ready-checklist.md`, a draft list of everything Zerodha must see before we reapply
for multi-user access. Part A is Zerodha's own ten written asks (ticket 403947, finding F-31). Part B is the nine
things that must work on screen first (ADR-060 and the goal sentence of the standing direction).

**What I am asking:** is this the right finish line? Three choices:

1. **Approve as written (my recommendation).** Why: every row is either Zerodha's own words or a step of the journey
   you already approved on 10 Nov; nothing was added from my side. Each state is a measurement or says `unmeasured`.
2. Approve with changes: tell me the rows to add, drop or reword.
3. Not yet: tell me what is missing.

**What you will notice when reading it:** most of Part A is "not written" or `unmeasured`. That is honest, not a
fault of the list: the answers to Zerodha can only be written after a second person can log in on a hosted link and
one real order has gone through (rows B1 and B5). Those two are standing direction step 4 and still need your
decisions on host, spend and lifting the paper-only rule (ADR-281).

**One correction to the plan:** the contract said F-31 has nine asks. Counted from the ticket text there are ten
(the API list and the "is use limited to these five" question are separate asks). All ten are in the list.

Spec basis: finding F-31 (`spec/findings.md`), ADR-060, `docs/process/standing-direction.md` step 2 ("The owner has
approved the list").

## N1. To do in December: load the 2027 market holiday list (nothing to answer now)

**What a user would see without it:** from 1 Jan 2027 the app treats every day as "no market": no prices checked, no
practice fills, no warnings. The holiday list in the app covers 2026 only.

**Why it cannot be done today:** NSE publishes the next year's list in December.

**What to do, once NSE has published (a 10-minute step; a session can do it when you say "load the 2027 holidays"):**
add the 2027 F&O holidays to `backend/ofo/market_calendar.json` from the same source the 2026 list came from. The
file names it: NSE's holiday page https://www.nseindia.com/resources/exchange-communication-holidays (its data
address is in the file's `source` line), section "Equity Derivatives (F&O)".

**What this run adds so it cannot be missed:** from 1 Dec 2026 the app shows a banner on every screen and sends you
one phone alert a day until the list is loaded; and a date with no list reads "the market calendar has no dates for
2027", not "market closed".

**One change from what issue 686 proposed, told as information:** the issue wanted the app to refuse to start from
1 Dec without the 2027 list. I did not build that: it would stop a working app in December on days the calendar
still covers, before NSE has even published. A loud daily warning does the same job without stopping you.
