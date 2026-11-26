## D-60 rounds 3 and 4 (2026-11-24): commits 48bd943 + aa23745, 02fa66d + d886506

Owner direction 24 Nov ("take your call"): the two-round park rule clashed with the Part A Definition of Done ("nothing
else open" on the seven), so two further narrow rounds were run, each reviewed by a fresh-context helper.

Round 3 review (aa23745): (a) a net-zero step closes the question through one shared `cancelDuplicate`: yes. (b)
Increase raises `base_lots` with `lots` (`legDoor.js:27-30`; held base 1 at x2 + incoming base 1 at x2 = lots 4, base 2;
apply_multiplier 2 x 2 = 4): yes; MINOR: one side without `base_lots` at a multiplier other than 1 mixes units (no path
found that makes such a leg). Two MAJOR: an identity check dropped a real answer on an equal-content reassignment;
route watches, Undo and discardPending replaced legs without closing the question.

Round 4 review (d886506): `cancelDuplicate()` is the first line of `setLegs`, which every replacement except
`nameLegsFrom` (278) and the reply itself passes; `onBeforeUnmount` cancels; the answer check compares content
(`sameLegs`: id, instrument_id, action, lots). The apply path never calls `setLegs`, so an answer cannot cancel itself.
Tests 36/36.
1. Deferred (outside D-60, older than Part A): a `setLegs` while a leg-edit request is still in flight (no question yet)
   does not cancel that request, so its reply lands on the new legs. The code before Part A (01055d4, `sendEdit`
   `legs.value = applyEditReply(legs.value, reply)`) had the same behaviour. One-line fix: `guard.cancel('leg-edit')` in
   `setLegs`. Class: stale reply applied after a legs replacement.
2. MINOR: after `nameLegsFrom` fills names while the question is open, the move writes back legs built before the
   names (the names are re-filled on the next reply).
3. MINOR: an equal-content `setLegs` emit still closes the question (a replacement is treated as a replacement).

Covers the D-60 class (one live duplicate question per move; legs never merged silently): yes.
