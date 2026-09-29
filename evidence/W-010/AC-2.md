---
work_item: W-010
ac: AC-2
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "python - sweep: 8,571 values x add/edit/preview/apply/edits/search/is_qualifying; BOM and CR tests; 3 inline mutants via pytest.main"
---

AC: AC-2
result: pass
commands: python - sweep: 8,571 values x add/edit/preview/apply/edits/search/is_qualifying; BOM and CR tests; 3 inline mutants via pytest.main
observed: failures: 0. File-level BOM fine; BOM inside a cell MALFORMED; quoted cells holding \n, \r, \r\n, \x00, \x0b, \x7f MALFORMED; NBSP-only row MALFORMED; one bad row in a 10k file refuses the whole file (0 entries)
attack: Zs/Zl/Zp/Cf/Cc characters, look-alikes (Cyrillic, Greek, fullwidth, math alphanumerics, Kelvin sign, dotless i, long s, sharp s), all 1,985 combining marks and emoji, before/inside/after and substituted: none accepted. Mutants (Unicode strip, upper before check, isascii after full trim) caught: 2/18/18 failed. Outside AC (deferred #10): a \r-only CSV crashes preview with csv.Error instead of ValueError; nothing applied.

Recorded by the orchestrator from the verifier's returned block.
