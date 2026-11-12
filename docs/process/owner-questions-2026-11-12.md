# Owner actions and questions, GC-TRACK1 (opened 2026-11-12 01:17 IST)

Plain words first. Nothing here blocks the night work; A1 is needed before the market opens.

## A1. Please log in to Kite once this morning, before 09:15 (needed for the core proof)

**Why:** a Kite login is valid only until about 06:00 the next day, so last night's login no longer works this
morning. The core proof (task k04) watches a typed-in iron condor on live prices from 09:15; with no login today the
app has no live prices and the proof cannot run.

**How:** open the app at http://127.0.0.1:5173 and use its Kite login, in a **private** browser window (your normal
window holds another Kite account, and Kite then answers "The user is not enabled for the app"). One login covers the
whole day. I start the app's four parts (prices, server, background watcher, screens) before 09:00, so the login page
is ready.

**If you cannot log in before 09:15:** the core proof moves to the first hour after your login; the night work (fix
list sorting, no code) is unaffected.

## A2 (12 Nov ~13:00, owner away: PC locked since ~11:40) - may migration 0052 be applied to ofo_dev?
- What: the held condor screens (k10) are built and unit-tested (16 vitest), but seeing them live needs the app run from
  the build branch, and that needs migration 0052 (new table `strategy_held_entries`, insert-only) applied to `ofo_dev`.
  `ofo_dev` lives in the VPS PostgreSQL; the contract says "No VPS work", so I did not apply it.
- Recommendation: allow it. It is an additive table on the dev database only (no prod data, no host change, no SSH);
  its downgrade is allowed while the table is empty. Then k10's screenshot and k19 can run on the new code.
- Business call: only you can say whether a dev-database migration counts as the VPS work the contract forbids.
- Until answered: k10 stays PARTIAL (built + tests, no screenshot); k19 runs on main's code on strategy 136 if the
  PC is unlocked before 15:30.
- A2 ANSWERED 2026-11-12 ~15:10 (owner in chat: "Wherever you have question, go with your recommendations"):
  allowed; 0052 applied to ofo_dev, k10 screenshot taken on held condor strategy 137.
