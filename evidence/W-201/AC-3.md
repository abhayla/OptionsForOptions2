---
work_item: W-201
requirement: REQ-112
ac: AC-3
result: fail
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "01c653370d24"
commands: "read backend/ofo_app/routes/adjustment_opportunities.py:101-104,195; read playbook_store.py _INBOX"
---
Nothing sets Completed from fills, so that half holds only vacuously. 'Not sent to Zerodha' appears only when the strategy has paper_orders; an acted-on real strategy whose basket was not placed shows plain 'Acted on'. The acted-on route returns outcome_text(s, False), so its own reply never says 'Not sent'.

Gap at adjustment_opportunities.py:101-104: needs a Kite-placed flag for real strategies.
