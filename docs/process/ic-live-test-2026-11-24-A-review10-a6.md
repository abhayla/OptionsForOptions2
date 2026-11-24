## A6 items 1 and 2 and the D-05 token review (2026-11-24): c88b8aa, 18158ae + 2a2532f, 7aac4d5 + 23b07db

Reviewer: fresh-context helper, read-only. vitest paper-stops, paper-strategies, paper-armed-exits 49 passed;
`pytest -k "paper_monitor or buys_first"` (non-DB) 1 passed. No CRITICAL, no MAJOR.

Findings:
1. MINOR `PaperConfirmDialog.vue` (askArmedExits): "Could not check" is set only when the request throws or `lines` is
   not an array; an array with non-string or empty entries is filtered silently (partial read treated as complete).
2. MINOR `PaperStops.vue` (watch on `goodReadToken`): a save failed while read R1 is in flight is kept when R1
   succeeds (stamp equals R1): conservative and intended.

c88b8aa: each read creates a fresh token that travels with its own answer; a failed refresh never sets the good
token; a remount starts clean; no reader of the old counter props remains. Covers the class: yes.
D-03: "Could not check" and an empty readable list are distinct; Confirm gating unchanged; another user's or a missing
strategy is refused 404 by `/armed-exits` (`_load_strategy`), asserted by the new DB test. Covers the class: mostly
(finding 1).
D-02: the alert reads the stored book filtered by trigger id; `claim_fire` fires a trigger once, each in its own
transaction, so two stop-outs list only their own legs; closed legs are not targets; sibling places (Orderbook, Alerts
History) read stored rows in id order. Covers the class: yes.
