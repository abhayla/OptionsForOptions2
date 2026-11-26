# Lane P owner questions (26 Nov 2026)

Answered by the owner on 26 Nov morning (relayed by the coordinator; now in ADR-330): Q2, Q2b, Q3, Q4, Q5, Q7, Q9, Q10,
Q11. Each was the plan's recommended option; nothing built changed.

## LP-1 An open alert of a strategy that no longer has a plan

Spec basis: ADR-330 (3) "Such an alert does not close, lapse or leave the Active list until the user himself
acknowledges it and takes his call"; ADR-330 (11) "A strategy with no plan gets no adjustment suggestions and no target
or stop alerts". The two meet when a strategy that has an OPEN alert ends up with no plan (an alert raised under the old
playbook fallback before ADR-330 (11) was built, or a plan removed later).

Real case: on the first deploy of ADR-330 (11), every plan-less practice strategy that still holds an open record raised
under the system-default fallback (the owner's test strategies of 23-25 Nov) is in this state.

Options:
- (a) Close those alerts by the system and keep them in History with "The strategy is no longer monitored" (no plan,
  nothing watched; the bell and Active stop showing a rule the strategy no longer has). **Recommended**: the alert asks
  about a rule that no longer applies to the trade, so there is no call left for the user to take on it; History keeps it.
- (b) Keep them in Active until the user answers (ADR-330 (3) literally), although nothing watches the strategy.

Built meanwhile: (a), in one place (`background.py` owner lister, `close_by_system(..., not_monitored)`), reversible by
removing that one call.

**Answered** by the owner on 26 Nov 2026 (question tool, through the coordinator): "Close it by system (Recommended)" = option (a); recorded in ADR-330 (3).
