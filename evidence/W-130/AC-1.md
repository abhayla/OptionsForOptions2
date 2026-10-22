---
work_item: W-130
ac: AC-1
requirement: REQ-015
ac_fp: "489a55faca6a"
result: pass
verified_by: "independent verifier (Opus, fresh context, round 2 on 8a23776f)"
builder: "builder (Sonnet, builder sequence row 2)"
date: '2026-10-22'
commands: "start verifier on main 235e1793 (grep broker/status, login links, SessionEndedCard; templates.py:315-330); round 2 on 8a23776f: git diff af331fe4..8a23776f; grep get_kite_session"
---

AC: AC-1
result: pass
commands: start verifier on main 235e1793 (grep broker/status, login links, SessionEndedCard; templates.py:315-330); round 2 on 8a23776f: git diff af331fe4..8a23776f; grep get_kite_session
observed: connection is asked for only by broker gates: execute.py:298, execution_return.py:140, positions.py:169, tracking_not_connected; builder, outcome, catalogue and saved-strategy pages trigger no prompt
attack: looked for any non-broker route or page that asks for the connection: none (rounds 0, 1, 2)

Recorded by the orchestrator from the verifier's returned block.
