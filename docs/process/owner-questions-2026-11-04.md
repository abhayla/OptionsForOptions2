# Owner questions parked overnight, 2026-11-04 (GC-IC1)

Asked at the 09:15 Kite login, one at a time, recommended option first.

## Q1. How does a roll place the new short strike: entry distance from spot (Q255) or the playbook's target delta?

- Business call: what strikes a user is shown for a roll is product behaviour, and two of the owner's own decisions
  disagree; only the owner can choose.
- Found: GC-IC1 step 10 round 2, evidence/W-200/AC-4.md (FAIL), independent verifier.
- Side A, REQ-046 "Owner decision (2026-09-29, Q255)": "The platform keeps the structure's widths and re-places the
  short strike(s) at their entry distance from spot, snapped to the nearest listed strike." Example: entered with the
  short call 353 points above spot; spot now 23,300 -> rolled call spread 23,650 / 23,850.
- Side B, the approved playbooks (catalogue 2026-10-30, system playbooks decided 2026-11-02; ADR-239 for A-02/A-04/
  A-06): "A-02 roll the tested side out to 0.20 delta"; the code builds rolls at the playbook's target delta, with a
  200 / 500 point fallback when the chain has no delta (backend/ofo/adjustment/approaches.py:376-404). No entry spot
  or entry distance is stored anywhere today.
- Real case: strategy 82 (paper mirror of the NIFTY 29 Dec iron condor 21000/21500 PE, 24000/24500 CE, entered
  3 Nov 10:52). Its compare rolls today use the delta basis.
- Recommendation: Side B (target delta), and mark Q255 superseded in REQ-046. Reason: the playbooks were decided
  later and per strategy type and stage, delta tracks risk as volatility changes, and it is what is built and priced
  today; the entry-distance rule needs an entry spot that is not stored. Option: offer entry distance as a second
  basis later.
- Spec basis: REQ-046 Q255 section; spec/open-questions.md Q255 (DECIDED 2026-09-29); ADR-239; catalogue
  2026-10-30 line 329; REQ-155 AC-1 (does not name a basis).
