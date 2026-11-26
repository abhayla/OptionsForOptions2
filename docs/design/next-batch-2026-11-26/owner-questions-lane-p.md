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

## LP-2 Does the "2x the credit received" stop stay beside a stop typed in rupees?

Spec basis: ADR-330 (5) "a plan's profit target and loss stop can be typed either in rupees or in percent ... One rule
for every plan trigger"; ADR-247 "a loss of 50 % of max loss or 2x the credit received, whichever comes first". The
spec does not say whether a rupee stop replaces only the "% of max loss" part or the whole stop line.

Real case (Opus review of P4, 26 Nov, on the ADJ-01 iron condor, max loss Rs 2,600): rupee stop typed as Rs 400 while
the 2x-credit line stands at Rs 300; at a loss of Rs 450 two stop alerts fire, the credit one first (at Rs 300, before
the stop the user typed).

Options:
- (a) The rupee stop replaces only the "% of max loss" part; the "2x the credit received" line stays and the plan says
  so: "Stop: loss of Rs 400 (15.38 % of max loss) or 2x the credit received, whichever comes first". **Recommended**:
  it keeps ADR-247's rule unchanged and the user sees both lines that watch him.
- (b) A rupee stop is the whole stop: the 2x-credit line is not checked while a rupee stop is set.

Built meanwhile: (a), the words say both, in one place (`settings_in_force.stops_of` and the stop words), reversible.

## LP-3 (decided, B2) The per-lot figure when the legs have different lot counts

Spec basis: owner answer Q3 (ADR-330): "per-lot figure shown beside it"; silent on legs of different sizes (searched:
"per lot", "per-lot"). Decided: the per-lot figure is shown only when every leg has the same number of lots; otherwise
only the whole-trade figure. Reversible in `routes/adjustment_plan.py`.
