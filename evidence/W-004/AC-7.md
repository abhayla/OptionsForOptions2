---
work_item: W-004
ac: AC-7
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "same; python -c calling scenario_header(UXLevel.GUIDED,'NIFTY',Decimal('22909.5'),('0-P&L',)) and with a float level"
---

AC: AC-7
result: pass
commands: same; python -c calling scenario_header(UXLevel.GUIDED,'NIFTY',Decimal('22909.5'),('0-P&L',)) and with a float level
observed: 24 distinct headings, identical at Guided/Standard/Advanced; caption 'NIFTY at expiry | You make/lose'; Guided has no IV/Greek columns; float level raises ValueError; a level that is both CURRENT and 0-P&L shows both marks
attack: Tried a float level, a fractional level, a blank underlying and a level that is both CURRENT and a breakeven; all handled (rejected or fully marked). Also checked the caption is not inside any column label. New allowlist entry table/conftest.py NIFTY26OCT justified: the catalogue has only NIFTY26OCTFUT at 2026-10-27, same reason as the engine/scenario golden-fixture entries.

Recorded by the orchestrator from the verifier's returned block.
