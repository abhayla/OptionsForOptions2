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

## Q2. OK to register this app with the shared Notifier on the server? (needed for the warnings to your phone)

**What you get:** a message on your phone when the background watcher stops during market hours, when it comes back,
and once a day in December until the 2027 holiday list is loaded.

**What is checked (10 Nov 21:00):** the Notifier's public door answers from this PC (`notifier-health`: HTTP 200 in
0.95 s). What is missing is this app's own entry: the Notifier only accepts messages from apps it knows, each with
its own key. This app has none yet.

**What I need your OK for, because it is a change on the production server and creates a new secret:**
one new project block in the Notifier's `config.yaml` on the server, one new key in its `.env`, and a reload of the
Notifier process (`pm2 reload notifier`, the documented onboarding step, about 5 minutes; other apps' alerts are
not touched). The key then goes into this project's local `.env`, never into the repo.

1. **Yes, register it; "watcher stopped" goes to WhatsApp, the daily calendar reminder to Telegram or email (my
   recommendation).** Why: a stopped watcher means no loss alarm, so it should reach you at once; the calendar
   reminder is not urgent and should not use up WhatsApp messages.
2. Yes, but everything to one channel: say which.
3. Not now: the warning code stays built and unit-tested, and nothing is sent until you say so.

Until you answer, option 3 is what happens: the client and the watcher check are built and tested against a fake
Notifier, and row c25 ("one real test warning on your phone") stays PARTIAL.

Business call: only the owner approves a change on the production server and where his own alerts go.
Spec basis: REQ-115 AC-6 (heartbeat and Notifier alert), ADR-285 (1) (calendar warning through the shared
notifier); the Notifier onboarding steps in the owner's private notes.

## Q3. OK to delete one old work folder that still holds unsaved notes? (clean-up, not urgent)

**What:** the folder `OptionsForOptions2-OptionsForOptions2-gc-icguide` (the finished GC-ICGUIDE run, merged as PR
#687) has 13 unsaved lines in `owner-questions-2026-11-09.md`. The safe removal tool refused it for that reason, and
this run's rules forbid deleting a folder with unsaved work.

**Checked (10 Nov 21:06):** all 10 non-empty lines of those notes are already saved on this run's branch, word for
word (0 missing). Nothing would be lost.

1. **Yes, delete it (my recommendation).** Why: its work is on main, its notes are saved elsewhere, and it holds
   about 5,400 files of disk for nothing.
2. Keep it.

Until you answer it stays. Business call: none in the product sense; it is asked only because deleting unsaved work
is an irreversible act this run may not take on its own.
Spec basis: none: the spec says nothing about work folders (searched: worktree, work folder); the rule is in the
run's hard stops.

## N3. Please keep this PC unlocked while the screen checks run (11 Nov)

**What happened (11 Nov 01:40):** I started the test-data screens to do the three screen re-checks (rows c17, c18,
c19). The pages loaded, but Chrome could not take a single picture: the PC was locked, and a locked screen draws
nothing. Every screen row needs pictures as its evidence, so none could be done. The servers were stopped again.

**What I need:** when you log in to Kite from 09:00, leave the PC unlocked (screen on, no lock) while I run the live
checks (c10, c11) and, after 15:30, the three test-data screens. I never type your Windows password.

**Why this matters beyond tonight:** the session of 10 Nov morning reported "Chrome stopped drawing any tab" and
blamed low memory. It was very likely this same cause. Two sessions lost time on it.

## N2. For your information: the faster test database (PR #688) is reviewed and will merge when its checks are green

The earlier session told you this would not merge before you had seen it. This is that notice; nothing to answer.

**What it is:** a tooling change only. Each test run used to build a fresh test database in about 3 minutes; it now
copies a ready-made one in about 5 seconds (measured tonight on the real server: first run 293 s, second run 5 s).

**What the strict independent review found (10 Nov, two rounds):** one real problem and seven small ones. The real
one: the fast path skipped a safety check that the slow path runs every time (it confirms the app's database login
has not been given extra powers on the server shared with the other production app). That is fixed, re-checked by a
second independent review (verdict: pass) and proven on the real server. Three small leftovers are filed as issue
#691; none can touch a database the tool did not create.

**Not done:** the clean-up of the 8 old throwaway test databases still waits for your OK from the 9 Nov notes.

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
