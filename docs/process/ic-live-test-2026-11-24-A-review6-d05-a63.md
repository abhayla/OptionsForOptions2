## A6 item 3 review (2026-11-24): D-05 Not saved line and empty-level hint, commits 6b257fd and d0569fe

Reviewer: fresh-context helper, read-only. `paper-stops.test.js` + `paper-strategies.test.js` 44/44. Verdict: REVISE.

Findings:
1. MAJOR `PaperStops.vue:72`, `PaperStrategies.vue:237`: `goodReads` moves when a refresh reply lands, with no link to
   when that refresh started. A refresh starts, Save fails ("Not saved"), the earlier refresh then succeeds: the line is
   cleared although no refresh began after the failure. Fix: clear only on a good refresh that STARTED after the
   failure (a "refresh started" counter stamped at the failure). Class: a clear signal not ordered against the event
   it clears.
2. MAJOR `PaperStops.vue:125`: `v-if="ceReason && !saved"` hides every reason beside "Saved", not only "Enter at least
   one level": after "Saved: exit above 24500", typing 24500.03 hides "price must be a multiple of 0.05" and Save is
   disabled with nothing saying why. Fix: hide only the at-least-one-level case; the price reason always shows.
3. MINOR same line: a leg-stop "Saved"/"Kept" line also hides the exit hint (intended; covered by finding 2's fix).

Clean: the disabled Save rule is unchanged; leg stops, mixed saves and Already set untouched; no clearing mid-call; the
refresh error banner and `stale` do not unmount PaperStops; a failed or unreadable refresh does not move `goodReads`.

Covers the class: no (findings 1 and 2).
