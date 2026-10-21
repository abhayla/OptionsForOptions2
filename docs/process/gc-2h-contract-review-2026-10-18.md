# GC-2h contract review (chain rule 3), 2026-10-18 ~23:30 IST

Precondition check (fresh Sonnet): READY - every fixture, script, held PR (9, all open drafts) and the 43 open issues
match the tracker one to one; ADR-112 and chain rules 8-9 exist only in this PR (it lands first).

Full design review (fresh Opus, order + reconciliation behaviour): GO WITH FIXES. All findings ACCEPTED and applied in
`goal-contract-GC-2h-2026-10-18.md`:
1. CRITICAL - next-day net 65 -> `filled` broke ADR-109 (2) (outside lots never attached automatically) and is
   permanent (a closed plan cannot be reopened). -> auto-close only when nothing changed; else a recorded mismatch;
   "adopt from net" parked as OQ-GC2h-1.
2. CRITICAL - the earlier-day open EXIT (ADR-111's own case) was missing; EXIT net 0 -> `exited` would absorb a hand
   close on Kite. -> EXIT net = held -> `nothing_placed`; net 0 -> mismatch, lifted by ADR-109 (4) "Kite flat -> mark
   exited".
3. MAJOR - #63 asked to slice; ADR-092 says never split anywhere; tracker showed #255 blocked on OQ-2 though ADR-092
   answered it. -> block above the freeze limit; #255 joins item 3; row corrected.
4. MAJOR - a recorded mismatch needs #380-1 and a close reason. -> #380-1 first, #352-1 stacked on #398 + #380-1, close
   reason `unresolved_from_positions`.
5. MAJOR - the GC-3L delta's fallback named only gc-2f/gc-2g; merging TRACKER would end the docs-only head. -> fallback
   covers `lock/gc-2*` (this PR); TRACKER held.
6. MINOR - overnight expiry -> mismatch / ADR-083 settlement. 7. MINOR - base = the net of the other stored plans; never
   close from the book. 8. MINOR - real next-day positions reply as pre-merge proof at GC-3F (tracker #352-proof).
9. MINOR - tracker_check gaps (deleted rows, closed-issue states, owner/stage-5 contracts) and #352's two halves. ->
   spec widened; rows split.
