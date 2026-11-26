# Lane B: what the page commit (5.5.4) needs in `frontend/src/pages/StrategyBuilderPage.vue`

Written by Lane B because the page was not Lane B's to edit in this run. Nothing below was applied or run against the page: the
page-dependent tests (listed in RESULTS-lane-b.md) were never green against a real wiring, so expect to adjust a test id or a
flush in them. Line numbers are of `a99730b8`.

Everything the page needs already exists as a module: `composables/useLegDoor.js`, `components/strategy/DuplicateLegDialog.vue`,
`stores/builderHold.js`, `composables/useLeaveBuilder.js`, `components/strategy/LeaveBuilderDialog.vue`, `lib/legDoor.js`
(`sameLegs`, `OPPOSITE_*`). The tests turn themselves on when the page source contains `useLegDoor`, `draft-replace-dialog`,
`useBuilderHold`, `useLeaveBuilder` (`tests/helpers/phase5Wired.js`), so the page commit needs no test edit except deleting the two
`skipIf` stand-ins (below).

1. Door (replaces `:748-791`, `:1004-1012`). `const door = useLegDoor({ maxLots: () => served.integer(MAX_LOTS_KEY) })`,
   `provide('legDoor', door)`, `const cancelDuplicate = () => door.cancel()` (call sites `:648, :742, :758, :800, :939` stay).
   Delete `dupAsk`, `askDuplicate`, `answerDuplicate`, `askMovedDuplicates`; keep the local `sameLegs` or import it from
   `@/lib/legDoor`. In `sendEdit` (`:817`) use `const moved = await door.admitMoved(baseLegs, landed)` (same null / `{error}` /
   `{legs, increased}` handling). Template: one `<DuplicateLegDialog :door="door" />` instead of the `<Modal :open="dupAsk !== null"...>`
   block (the page must no longer contain `title="Already in this strategy"`).
2. ADR-328 (2) (`:626-640` watch). Before `leaveDrafts()` / `setLegs`: parse the incoming draft into locals; if `legs.value.length`,
   the link is readable and its legs differ (by `instrument_id`, `action`, `lots`) from the shown ones, ask `replacePrompt(count)`
   (`@/lib/readyMade`) in a Modal holding `data-testid="draft-replace-dialog"`, buttons `draft-replace-yes` / `draft-replace-cancel`
   (Escape, x, overlay = Cancel). Cancel: legs, Drafts Mode and `openStrategy` untouched, `draftQuery` / `canonicalQueryLegs` put
   back, `router.replace` the previous `draft` and ignore the one watch call that write causes. Same content as shown: return
   without reseeding. Unreadable link: today's path (no question). A second question settles the first as Cancel.
3. ADR-329 hold (`:121` and the refs at `:350, :356, :362, :190`). Before `const legs = ref(...)`: `const hold = useBuilderHold()`;
   `?strategy=` or `?adjust=` in the query -> `hold.clear()` else `heldBack = hold.take()`; `legs = ref(heldBack ? heldBack.legs : legsFromQuery())`
   and seed `savedId`, `savedRevision`, `openStrategy`, `shapeName` from `heldBack`.
4. Chain add (`onMounted`, `:702`). `if (heldBack && draftQuery && canonicalQueryLegs)`: incoming = `legsFromQuery()` re-id'd `chain-<n>`;
   `const r = await door.admit(legs.value, incoming, { opposite: 'allow' })`; `null` = leave the held legs; `r.error` -> `editError`
   (`{ ...NEUTRAL_PARTS, what_happened: r.error }`); else `setLegs([...r.legs, ...r.kept])`. Do this before `load()` so the first
   outcome request has the final legs, and never through the draft-watch question.
5. Leave guard (near the end of `<script setup>`). `const leaveGuard = useLeaveBuilder({ role: 'builder', unsaved: () => unsavedCount({ legCount: legs.value.length, savedId: savedId.value, inDrafts: paper.value !== null, pendingCount: pendingOrders.value?.length ?? 0 }), snapshot: () => (legs.value.length ? { legs: legs.value, openStrategy: openStrategy.value, savedId: savedId.value, savedRevision: savedRevision.value, shapeName: shapeName.value, paperId: paper.value?.book?.strategy_id ?? null, netKey: paper.value ? netKeyOf(paper.value.net) : null } : null) })`
   and `<LeaveBuilderDialog :leave="leaveGuard" />` in the template. The guard only registers when the page is rendered by a
   `<router-view>` (the real app); tests that mount the page directly stay unaffected.
6. Drafts Mode restore (the part PLAN 5.5 allows to park). On mount with `heldBack.paperId`: `router.replace` the query to
   `?strategy=<paperId>` and, when `enterDrafts` has read the book, compare `netKeyOf(net)` with `heldBack.netKey`: equal ->
   `setLegs(heldBack.legs)` (the pending edits reappear); different -> keep the book's net and show "The strategy changed while you
   were away. Your unsaved edits were not restored." (new wording). Test C11 pins this; if it costs more than 2 rounds, park it
   (deferred issue) and make the snapshot skip Drafts Mode (`paperId` null) so the leave question alone covers it.
7. Delete the two stand-ins once 1 and 2 are in: the `it.skipIf(WIRED.door)` test in `leg-step-duplicate-d60.test.js` and the
   `it.skipIf(WIRED.draftReplace)` test in `draft-link.test.js`.
8. Grep the 40 test files that mount `StrategyBuilderPage` for a second `?draft=` push with legs on screen (item 2 now asks): add
   the `draft-replace-yes` click with the reason in the commit message. Not done here (the page was out of reach).

Merge first: `origin/refactor/modular-doors` at Lane A's Phase 4 head (PLAN 3.2), then regenerate nothing (Phase 5 has no generated file).
