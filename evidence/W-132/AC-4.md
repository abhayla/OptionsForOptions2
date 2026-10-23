---
work_item: W-132
ac: AC-4
requirement: REQ-117
ac_fp: "aed306694ad9"
result: pass
verified_by: "independent verifier (Opus, fresh context, round 2 on 23eee95b)"
builder: "builder (Sonnet, builder sequence row 4: build, finish, fix round 1)"
date: '2026-10-22'
commands: "rounds 1-2: flag_attacks.py; mutation plug always_true / no_try / no_source_check / skip_unknown (killed: 52, 28, 8, 9 tests failed); tests/broker/test_broker_flags.py incl. duplicate keys"
---

AC: AC-4
result: pass
commands: rounds 1-2: flag_attacks.py; mutation plug always_true / no_try / no_source_check / skip_unknown (killed: 52, 28, 8, 9 tests failed); tests/broker/test_broker_flags.py incl. duplicate keys
observed: removing basket_margin_quote turns off that flag only and the margin line shows the reason; a missing file, bad JSON, null, a list, a missing/blank source, a bad/null date, 'true' or 1 for on, an unknown key, an extra field, a BOM, a duplicate flag key or a duplicate entry key -> all 7 off
attack: round 1 found a duplicate JSON key winning silently (all on); fixed with object_pairs_hook in 23eee95b

Recorded by the orchestrator from the verifier's returned block.
