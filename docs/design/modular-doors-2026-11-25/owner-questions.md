# Owner questions: modular-doors plan

25 Nov 2026. Raised by the Step 0 review of `PLAN.md`. The cloud session does not wait for answers: it builds the
choice named under "Built meanwhile".

## OQ-1 D-60: ask a question when a strike step lands on an opposite-action held contract?

What: D-60 was reported as "B 26000 CE and S 26000 CE as two rows". Today's rule (ADR-319 (4), REQ-030 AC-11) asks the
Increase / Keep separate / Cancel question only for the same action on the same contract; a deliberate add of the
opposite action is allowed as two rows (`legDoor.js:15 sameContract` needs the same action). Moving a leg with the
strike step so that it lands on a held contract of the opposite action therefore raises no question and leaves two
opposite rows that net to nothing. Should that step ask?

Spec basis: REQ-030 AC-11; ADR-319 (1) (same-action moves ask the question) and (4) (opposite action is a deliberate
add, no question); ADR-322 (3) is unrelated (price refusal). The spec is silent on a step, as distinct from a deliberate
add, that lands on an opposite-action contract.

Options:
1. Ask on a strike step or move onto an opposite-action held contract; keep ADR-319 (4) (no question) for deliberate
   adds (picker, ready-made). (recommended)
2. Never ask for opposite action, as ADR-319 (4) is written.
3. Ask for every entry point, including deliberate adds.

Recommendation: option 1. A step is a move of an existing leg, and two opposite rows on one contract net to nothing,
which is rarely what the user meant; a deliberate add is a different intent and stays as ADR-319 (4) says.

Built meanwhile: ADR-319 (4) as written (option 2): no question for opposite action; every entry point still goes
through the one leg door, and same-action moves ask the question.

## OQ-2 Delete `POST /strategies/{id}/tracking/exit` as a dead door?

What: the route has no frontend caller, but four test files use it (`tests_app/test_strategy_tracking_list.py`,
`test_paper_adjustment_limit.py`, `test_paper_save_paths_fx2.py`, `test_scenario_isolation.py`), plus a mention in
`scenario_mode.py` and the `paper_limit.py` docstring. It closes from the entry legs, not the net book
(`tracking.py:550`). Keeping it means one more exit path to maintain; deleting it means rewriting those tests onto the
Positions exit route.

Spec basis: ADR-002 (every order belongs to a strategy; the route keeps that); ADR-117 (buys first); ADR-322 (3). The
spec does not name this route (searched: tracking/exit, exit route, tracking exit).

Options:
1. Keep it for now on the shared exit door, behaviour unchanged; delete in a later round with its tests moved.
   (recommended)
2. Delete it in this round and move the tests onto the Positions exit route.
3. Keep it permanently.

Recommendation: option 1 (delete in a later round). It is a dead door for users, but removing it now widens a refactor
that is meant to leave behaviour unchanged.

Built meanwhile: the route stays and is moved onto the B1 exit door, behaviour unchanged (closes from the entry legs);
its tests stay as they are.
