## A6 item 3 round 2 review (2026-11-24): D-05 commits 3f66dc5 and e40a6c2

Reviewer: fresh-context helper, read-only; paper-stops 27 + paper-strategies 19 = 46/46. Covers the class: yes.

"Reads never overlap" holds: `usePaperRefresh.js:19` refresh() returns while `reading` is set; the timer, the Refresh
button, mount and refreshNow() all pass through it; a queued read starts in `finally` after show(). So
`goodReadStart = readsStarted` inside show() is that read's own number.

Findings:
1. MINOR `PaperStrategies.vue:240,255`: the no-overlap guarantee lives in another file and is stated only in a comment;
   structural option: capture `const n = ++readsStarted.value` in read() and hand it to show(). Not a current defect.
2. MINOR `PaperStops.vue:60-68,77`: a cancel() failure stamps the read count but its error does not start "Not saved",
   so a good refresh never clears it (as before this change; not a Save, outside the owner decision).

Checked: a failure while a read is in flight keeps the line (only the next read clears it); a failed or unreadable
refresh never moves `goodReadStart`; leg-stop and keep failures stamp the same way; typed levels survive a failed
save; a remount resets error and stamp; beside Saved only the at-least-one-level reason hides.
