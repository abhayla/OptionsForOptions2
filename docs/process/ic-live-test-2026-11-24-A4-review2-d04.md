## A4 review 2 (2026-11-24): D-04 server change 2915daf6 and fallback 6972d3d7

Reviewer: fresh-context helper, read-only, static read of HEAD ac04a0a. Class: every paper basket at or over the plan
maximum (ADR-318 points 1 to 5); rules from the entry shape with the fallback (ADR-318 point 4). Verdict: REVISE.

Findings:
1. MAJOR, screen and server disagree when the entry shape cannot be classified. The server (`paper_limit.py:42`) calls
   `check.entry_type`, which falls back to the current shape (`adjustment_check.py:176-177`). The screen's offer path
   (`routes/adjustment.py:590`) passes `tracked.entry_position or position` to `guards_of`, and
   `adjustment_readers.py:287` classifies that position alone, with no fallback. Case: a condor entered on an expiry no
   longer listed, rolled, now at 2 of 2: the screen finds no playbook, shows no limit notice and offers rolls and adds;
   the server refuses the same basket with STRATEGY_VALIDATION_505. Also the server classifies with spot None while the
   screen uses the live spot. Fix: route the offer path through `check.entry_type`. Class: yes (offered against refused).
2. MINOR, permissive paths with no "not checked" note: (a) entry and current shape both unclassifiable, or no listed
   contracts (`paper_limit.py:133`): no limit, opens accepted; (b) `adjustment_readers.py:190-192` returns no entry shape
   when any order lacks `placed_at`, so the current shape decides. These are the existing "no playbook means no limit"
   state. Class: partly.
3. MINOR, accepted set wider than offered: any basket made only of exit, stop or settle is accepted
   (`paper_limit.py:99`), including closing only a protective wing. Matches ADR-318 (5) literally ("close or reduce open
   legs"); not a defect. `paper_store._check_reducing` refuses an exit that does not strictly reduce.

Basket matrix at or over the maximum (`paper_limit.py:78-102`): close only, reduce only, buy back a short, exit all,
draft quantity reduction: accepted. Open a new leg, add to a leg, mixed close and open, roll, strike change, draft that
crosses zero: refused. Already over the maximum: reduce accepted, open refused. The entry basket is never checked.

Bypass check: `place_checked` has two callers (`routes/paper.py:1065`, `routes/tracking.py:539`); the other writers
(`paper_monitor.py:231` stop, `paper_settlement.py:178` settle) only reduce; `INSERT INTO public.paper_orders` appears
only in `paper_store.py:44`. No bypass found. Open: A-23 "Delta-neutral helper" is in EXIT_REDUCE (`offered.py:22`);
whether it places add orders was not confirmed.

`tests_app/test_adjustment_history_why.py:141`: the code is right and the expectation is wrong (ADR-318 point 5). The
basket at line 140 is the third non-entry basket and sends one order of kind "add" at the plan maximum.

Covers the class: no (finding 1 on the offer path; finding 2 silent no-limit paths).
