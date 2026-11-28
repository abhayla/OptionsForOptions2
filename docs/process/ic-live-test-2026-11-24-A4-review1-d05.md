## A4 review 1 (2026-11-24): D-05 last fix, commit ef733f08

Reviewer: fresh-context helper, read-only, diff only. Class: every path to a paper exit from the paper list while
prices are paused (REQ-109 AC-5). Verdict: no CRITICAL, no MAJOR. `frontend/tests/paper-strategies.test.js` 19/19.

Paths traced in `PaperStrategies.vue`: Exit button disabled while `stale` (l.122) and `ask()` refuses while stale
(l.273); a confirm already open when a refresh fails or comes back unreadable is closed by `fail()` (l.242) and the
`show()` unreadable branch (l.229); keyboard: the Modal handles only Escape and the Tab trap; no exit-all in this
component; compact mode has no exit buttons; the parent `v-if` chain cannot hide the reason line while stale. Server:
`POST /paper/strategies/{id}/orders` reads live prices itself (`_server_exit_prices`, `backend/ofo_app/routes/paper.py`
960-985) and refuses with `tracking_exit_prices_not_live` (409); tests at `tests_app/test_strategy_tracking_list.py:242,274`.

Findings:
1. MINOR `PaperStrategies.vue:283`: the new `if (stale.value) return cancelExit()` cannot run (every stale path nulls
   `confirm` first, so `doExit` returns at `!c`). Harmless defence in depth. Class: yes.
2. MINOR `PaperStrategies.vue:229,242`: closing the confirm while a POST is in flight drops the dialog; if that POST
   ends "unknown", the "unknown outcome, open Orderbook" notice (ADR-017) is not seen. A repeat exit is still refused
   by the server's EXIT_EXCEEDS_OPEN check under the row lock. Not run. Class: no (different class).
3. MINOR `PaperStrategies.vue:122`: `stale` means "refresh failed", not "server reports PAUSED"; a group the server
   marks PAUSED keeps an enabled Exit, and the refusal comes after Confirm (server 409). The server checks only the
   named legs: exiting a live leg while another leg is unpriced is accepted. AC-5 reading (per named leg) to confirm.

Covers the class: yes for the screen (every paper-list exit path passes `ask()`/`doExit()`, stale-gated; confirm nulled
on a failed or unreadable read); the server refuses independently. Not in this class: builder `PaperBookPanel` exit,
`TrackingPanel` exit, trigger fires while paused.
