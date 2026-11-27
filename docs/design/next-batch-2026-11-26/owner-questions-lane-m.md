# Owner questions, Lane M (27 Nov 2026)

## Q1. Does a trade with no plan get the side-closed question?

Business call: when one side of an iron condor that has NO plan closes, is the user told and asked (add the legs
again, or confirm the new shape)? And does a waiting side-closed question stay when the plan is removed?

Spec basis: ADR-330 (2)(b) "When a side closes, the user is told so and asked ..." and (33) "every time a side of the
trade closes the user is told and asked again" (no plan condition); against ADR-330 (3) a waiting alert "when he
removes the plan from its strategy ... leaves the Active list ... closed by system because the plan was removed. Not
chosen: keep it until answered" and (11) "A strategy with no plan gets no adjustment suggestions and no target or
stop alerts".

Real case: PC 27 Nov, trade B-P2: call side closed, no side-closed row in Alerts > Active at 11:42 or 13:03 (it had
no plan at 11:14). Fresh trade B-P3 #208 with a plan: the row came 1 minute after its call side exited (T2-04 PASS).

Options:
1. (Recommended) Yes: the question is about the trade's shape name, not a plan rule; it comes with or without a
   plan and stays until answered when a plan is removed. Built and tested on branch hotfix/side-closed-1127 (df611c2,
   not pushed, Tier A reviewed), ready to push on your yes.
2. No: only a trade with a plan is asked (today's behaviour); ADR-330 (2)(b) gets "for a trade with a plan".
