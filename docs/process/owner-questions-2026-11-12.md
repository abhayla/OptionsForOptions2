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
