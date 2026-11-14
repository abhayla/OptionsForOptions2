# Owner answers given 14 Nov 2026 after the last branch commit (80a2f473)

Not yet on the branch, on purpose: the full local check's pass marker is for head 80a2f473, and a commit would make
it stale. The NEXT session's first step: copy each answer below into
`docs/process/owner-questions-2026-11-13.md` on `fix/gc-icfix` (an "ANSWERED" line under the question) and commit.

## Q4 (the "needed to recover the current loss" line on every fresh trade): ANSWERED 14 Nov 2026 (question tool)
Answer: "Keep as built (Recommended)". The line stays, shown whenever Profit left is larger than Max profit, also when
the loss is only charges. No decision row needed: it confirms the two branch decision rows (302 and 306) as built.

## DECIDED BY THE RUN under the owner's rule of 14 Nov ("whenever you have question, go with your recommendation")
- Q7 (builder work folders): leave them until the single push; then remove 16 with the removal tool; keep `-paisa`
  until issue 707 is done. Both of the owner's rules stay intact; cost is a little disk space.
- Q8 (a real broker trade cannot show the after-charges figure in the target alert): leave as built (the alert gives
  the true reason). Decide ADR-276 (4) again only when real order placing returns (ADR-281 hold).
- Issue 707 (Max profit after the charges really paid): one more round, in the NEXT fresh session, not in the long
  one. Cause is now exact: money text must be formatted once at the reply boundary (two decimals), so neither `962`
  nor a 28-digit tail leaves the server; add a database-path test with a stored futures row. First merge
  `fix/gc-icfix` into `build/gc-icfix-paisa`, run the guard tests, record the merge commit in the issue. Reason for
  another round despite the two-round cap: the Opus check passed the design, the one red test has a one-line cause,
  and the defect is visible to users (Max profit ignores charges already paid).
- Live app copy: restart from the branch at the start of the next session (needed before the Monday screen proofs).

## Q9 (Max profit assumes a closing order): ANSWERED 14 Nov 2026 (question tool)
Answer: "Keep as is (Recommended)". Closing charges stay assumed in Max profit and Max loss.
No decision row needed: the answer keeps ADR-263 and ADR-082 (2) exactly as written; nothing in the product changes.
