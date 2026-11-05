# Owner questions parked 2026-11-05 (owner away overnight; rule: never call the question tool while the owner is away)

## (a) Mockup approval - "Your adjustment settings"
Business call: only the owner approves what users will see.
Spec basis: goal-contract-your-adjustment-settings-2026-11-04.md Step 0b / 0c (no screen code before the owner approves
the mockup); owner chat 2026-11-05 ~00:25 IST: "once you reach the desired rating, then you start work on the screen ...
You have all my approvals".
State: round 17 reached every tab above 9.0 from all three reviewers (UI 9.2-9.3, mockup 9.2-9.3, options 9.3-9.4);
published once to https://claude.ai/artifact/Gw56H742xyZegg5bQXhW6p (version 2). Screen work started under the
pre-approval above (step 4 Adjustment settings screen merged and pushed on feature/adjustments 0603f418 after prepush --full TOTAL PASS; nothing to main).
Recommendation: confirm "Approved" after a look at the link. Any change you ask for goes into the mockup and the
screens as a change list (it does not undo the merged server steps 1-2).

## Already answered in session (written into the spec, fe0177cb): (b) ADR-247 stop; (c) #627 after the contract
(in ADR-247); (d) ADR-248 ranking cost / credit; (e) ADR-249 Reading A now, B later.

ANSWERED 2026-11-05 ~08:0x IST via the question tool: (a) "Approved". No spec change: mockup approval is the contract step 0c gate, not a product rule.

## (f) T-14 gamma alerts on LIVE strategies (parked 2026-11-05 23:33 IST by the ic-e2e-paper goal run)
Business call: only the owner decides whether a new rule starts raising alerts on real positions (what the owner sees
live on strategy 82 from the next market open).
Spec basis: goal contract ic-e2e-paper design decision 8 (T-14 = worst P&L change from a 1% move as a % of margin,
fires at >= 3 / 3 / 2) AND design decision 17 ("Live behaviour must not change. The only live-mode change allowed is
the lister filter"). The two conflict once T-14 is evaluated: every system playbook has T-14 ON (Stage B2 review,
probe of all 12 playbooks), live already reads margin for the carry rule, so T-14 would fire on real positions.
Measured: on the test iron condor (ADJ-02 legs) T-14 = 7.6063 % of margin vs the stage value 3 -> it fires.
Strategy 82's own value: not measured (the run never reads ofo_dev outside the Stage D move).
What the run did (technical call, reversible): T-14 is evaluated in TEST-DATA (scenario) mode only; in live mode it
stays "pending / not checked yet" exactly as before. Proven by tests both ways.
Recommendation: turn T-14 on for live after you look at its value on strategy 82 (one line change + its live test).
Expect T-14 alerts on most short iron condors near expiry, since a 1% move costs more than 3% of margin there.
