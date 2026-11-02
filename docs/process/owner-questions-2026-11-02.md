# Owner items, 2026-11-02 (GC-ALERT1 run; none blocks the run)

## 1. For information: when an adjustment suggestion lapses (ADR-237 (4), decided 21:04 IST)

- What changed: a playbook suggestion now lapses when its value clears the line by the re-arm margin (T-07 at 80 %
  intraday: at or below 72 %), not at the first moment it dips back under the line.
- Why: with one suggestion per crossing, the old rule would lapse strategy 66's single 10:40 suggestion at the 10:41
  close (78.74 %), and the rule would then stay quiet all morning while the value sat at 80 %. The trader would see one
  flash and nothing.
- What you will see: one open suggestion that stays "Open" while the value hovers near the line, instead of 30
  suggestions that each said "Lapsed" (2026-11-02: 75 of 103 records lapsed).
- Spec basis: REQ-112 AC-2 ("Lapsed (the condition stopped holding ...)"), REQ-170 AC-1/AC-2, ADR-237 (4).
- To change it: say "lapse at the line" and the old rule comes back (one-line change in the gate).
