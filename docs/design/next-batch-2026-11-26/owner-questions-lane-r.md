# Owner questions, Lane R (screen findings of 26 Nov 2026)

Raised by Lane R (branch fix/screen-findings-1126, cut from feat/nb-screens-w2-1126 at a9bd41a). Each question goes to the
owner only through the coordinator. Where an option is reversible, Lane R builds the recommended one and says so.

## LR-Q1 Row 11: the "Replace the N legs?" question on a draft link (asked 26 Nov 2026)

Spec basis: ADR-328 (2) (Option Chain "Add Selected" asks "Replace the N legs?"); ADR-329 (1) (the chain trip now ADDS,
it does not replace) and ADR-329 (3) ("ADR-328 (2) stays for the case where the builder, already showing legs,
receives a draft link that replaces them (a pasted or shared link, not the chain's Add Selected)"); ADR-329 (2) and
check row 10 ("Closing or reloading the tab: no question (decided: the browser's own box cannot show the sentence)");
REQ-079 AC-5 (the wording). ADR-328.md itself was never edited, so read alone it still says "Option Chain Add Selected";
ADR-329 (3) narrowed it. The check text (RESULTS.md row 11) follows ADR-329 (3).

**The two texts.**
- Check row 11: "With legs shown, paste a different `?draft=` link into the address bar of the same tab: 'Replace the
  N legs in the builder?' Replace / Cancel; Cancel keeps the legs and puts the old link back."
- ADR-328 (2) as written: "Option Chain 'Add Selected': when the builder already holds legs, it asks 'Replace the N
  legs?' ... before replacing them". ADR-329 (3) later moved this question to a pasted or shared draft link.

**What the screen did (A11-retry, 10:57).** Empty NIFTY 1 Dec builder, 3 legs added (S 25900 CE, S 25700 PE,
B 26000 CE), then the address became `/strategy/builder?draft=test-replace-1126` by a full page load: "No draft
strategy is open. Add a leg to start one." The 3 legs vanished and no question was asked.

**What the code does (read this turn).** The question lives in a watch on the URL's `draft` value in
`frontend/src/pages/StrategyBuilderPage.vue` (line 673 on); it fires only when the `draft` value changes while the
builder page is ALREADY mounted. A link typed or pasted into the address bar and Enter loads the whole app fresh: the
unsaved legs are in page memory only, so they are gone before any code can ask (the same as row 10's decided reload
case). The only two places in the app that make a draft link (Option Chain "Add Selected", `OptionChainPage.vue:129`,
and Create Strategy > Guided, `CreateStrategyPage.vue:170`) both start on another page, so the builder is not mounted
when the link arrives; the chain trip then adds (ADR-329 (1)) and the Create Strategy trip has already asked "Leave
the builder?" on the way out. Real case: there is no path in today's app on which a user can see "Replace the N legs?"
from a draft link; only the unit test `draft-link.test.js` reaches it, by changing the route in place.

**Options.**
1. (Recommended) Keep the behaviour; correct the check and the spec text. The replace question stays as a guard for an
   in-app link that arrives while the builder is open (none exists today; any future one gets it for free). Row 11 is
   rewritten as: "Paste a different `?draft=` link into the address bar: the page loads fresh, the unsaved legs are lost
   with no question, the same as a reload (row 10)". ADR-328 (2) gets a pointer to ADR-329 (3) so it no longer reads as
   the chain's rule. Reversible, wording only; no user loses anything new. Cost: a pasted link still drops unsaved legs
   silently (true today and for a reload, already decided).
2. Keep unsaved builder legs across a page load (kept in the tab's own browser storage, cleared on Save, Discard or
   Leave), so a pasted link, and a reload, find the legs and ask "Replace the N legs in the builder?". This is new
   behaviour: it also changes row 10's decided reload case (a reload would bring the legs back), and it must not bring
   back legs for a different user on a shared PC. Larger build; Lane R would not start it without the answer.
3. Ask with the browser's own "Leave site?" box before any page load while the builder holds unsaved legs. Already not
   chosen once (row 10: the browser box cannot show the sentence or the count).

**Lane R action now:** nothing built for row 11. If option 1 is chosen, Lane R (or the coordinator) edits the check text
and adds the ADR-328 pointer; that pointer is a spec text change, so the row number stays the coordinator's.
