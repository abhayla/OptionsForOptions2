---
work_item: W-080
ac: AC-2
requirement: REQ-073
ac_fp: "12b126ca3e41"
result: pass
verified_by: "verifier (opus, fresh context)"
builder: "builder (opus/sonnet, worktree agents, rounds 1-10 + integration)"
date: '2026-10-16'
commands: "the AC-1 pytest run at 26eff25; python -c make_tag/parse_tag boundary probes"
---

AC: AC-2
result: pass
commands: the AC-1 pytest run at 26eff25; python -c make_tag/parse_tag boundary probes
observed: (1,1,0) -> "OFS1V1L0" (8 alphanumeric characters, decodes back); (12345678,1234567,99) would be 22 characters and is refused, never cut; ids 0, True, -1, 1.0 and '1' refused; parse_tag refuses "OFS01V1L0", a trailing space, lower case, "L00" and an Arabic-Indic digit. Live: tags OFS1V1L0 and OFS1V2L0 came back on Kite's orders 261016170576173 and 261016170858845.
attack: over-length tags, bool/float ids, padded and Unicode-digit tags - all refused.

Recorded by the orchestrator from the verifier's returned block.
