# Lane N: changes still needed in files Lane N does not own (ADR-330 (56))

Spec basis: ADR-330 (56) (owner 27 Nov 16:50, relayed): the not-live notice shows ONCE at the top of the screen, with the time;
each trade keeps its last figures, greyed, with no repeated sentence; with exactly one trade affected, only it carries the line.
Branch `lanen/adr56`. The shared pieces already exist there and need no edit: `priceScope` / `tileNotLive` / `PRICE_GREYED_CLASS`
(`frontend/src/lib/priceState.js`), the `price-greyed` CSS class (`frontend/src/style.css`), `PriceNotice.vue`.

## For lane V

### frontend/src/components/strategy/PaperStrategies.vue (Lane U then V)

Why (ADR-330 (56)): each Positions Paper tile (full card and compact row) is greyed when its prices are not live and prints no
not-live sentence of its own when two or more strategies are affected; exactly one affected: only that tile keeps its line; the list
tells the page how many are affected (`summary.affected`), so `PositionsPage.vue` (already on the branch) shows the one page notice.
Until this diff lands, `PositionsPage.vue` reads `paperSummary?.affected || null`, so it shows the notice from the index answer alone:
nothing breaks, the tiles just keep their own sentence. Display lines only; no Exit function is touched.

```diff
diff --git a/frontend/src/components/strategy/PaperStrategies.vue b/frontend/src/components/strategy/PaperStrategies.vue
--- a/frontend/src/components/strategy/PaperStrategies.vue
+++ b/frontend/src/components/strategy/PaperStrategies.vue
@@ -44,7 +44,7 @@
       <ul v-if="compact" class="mt-2" data-testid="paper-compact">
-        <li v-for="g in shown" :key="g.id" class="border-b border-line py-2" data-testid="paper-compact-row" :data-strategy="g.id">
+        <li v-for="g in shown" :key="g.id" class="border-b border-line py-2" :class="tile(g).greyed ? PRICE_GREYED_CLASS : ''" data-testid="paper-compact-row" :data-strategy="g.id">
@@ -55,13 +55,13 @@
-              <span v-if="stale || g.totalAfter.text === null" class="block text-xs text-ink-muted" data-testid="paper-compact-reason">{{ stale ? PAPER_PAUSED : g.stateText || NO_TOTAL }}</span>
+              <span v-if="stale || g.totalAfter.text === null" class="block text-xs text-ink-muted" data-testid="paper-compact-reason">{{ stale ? PAPER_PAUSED : (tile(g).line ? g.stateText : '') || (g.stateText ? '' : NO_TOTAL) }}</span>
@@ -64,1 +64,1 @@
-        <div v-for="g in shown" :key="g.id" :ref="(el) => (cards[g.id] = el)" class="mt-3 rounded-lg border border-line p-3" data-testid="paper-group" :data-strategy="g.id">
+        <div v-for="g in shown" :key="g.id" :ref="(el) => (cards[g.id] = el)" class="mt-3 rounded-lg border border-line p-3" :class="tile(g).greyed ? PRICE_GREYED_CLASS : ''" data-testid="paper-group" :data-strategy="g.id">
@@ -111,7 +111,7 @@
-            <p v-if="g.stateText" class="mt-1" data-testid="paper-state">{{ g.stateText }}</p>
+            <p v-if="g.stateText && (tile(g).line || g.state === 'EXITED')" class="mt-1" data-testid="paper-state">{{ g.stateText }}</p>
@@ -181,7 +181,7 @@
-import { usePriceFreshness } from '@/lib/priceState'
+import { PRICE_GREYED_CLASS, priceScope, tileNotLive, usePriceFreshness } from '@/lib/priceState'
@@ -263,7 +263,11 @@
 const loading = ref(true)
+// ADR-330 (56): ONE rule (priceScope) says how many strategies have no price; many -> the page notice + greyed tiles, one -> only that tile's line
+const scope = computed(() => priceScope((shown.value ?? []).filter((g) => g.readable), (g) => g.state === 'PAUSED' || g.state === 'NOT_CONNECTED' || (g.positions ?? []).some((p) => p.open && p.noPrice)))
+const tile = (g) => tileNotLive(scope.value, g.id)
 const summary = computed(() => ({
+  affected: scope.value.count,
   totalAfter: totals.value ? totals.value.totalAfter : null,
```

(The hunk line numbers are the ones at bf02669a; apply by content. The same diff from git: `git diff bf02669a b4c5ec83 -- frontend/src/components/strategy/PaperStrategies.vue`.)

Tests that go with it (removed from Lane N's suite because they assert this file's new behaviour). Put them in a Lane V test file;
they use the fixtures of `tests/paper-header-6d.test.js` (`withPriceTexts`, `legacy` from `./_paperList`, the api mock):

```js
const paused = { state: 'PAUSED', total: null, unbooked: null, as_of: '2026-10-28T11:00:00+05:30', pause_reason: 'price_stale' }
it('two paused strategies: greyed, no sentence of their own, and the list says 2 are affected', async () => {
  const w = await show([item(1, paused), item(2, paused)])   // item(id, over) like paper-header-6d.test.js, strategy_id: id
  const groups = w.findAll('[data-testid="paper-group"]')
  expect(groups).toHaveLength(2)
  for (const g of groups) {
    expect(g.find('[data-testid="paper-state"]').exists()).toBe(false)
    expect(g.classes()).toContain('price-greyed')
  }
  expect(w.emitted('summary').at(-1)[0].affected).toBe(2)
})
it('one paused among two: only it carries the line, and the list says 1 is affected', async () => {
  const w = await show([item(1, paused), item(2)])
  const [a, b] = w.findAll('[data-testid="paper-group"]')
  expect(a.get('[data-testid="paper-state"]').text()).toContain('Paper P&L paused - prices not live')
  expect(a.classes()).toContain('price-greyed')
  expect(b.find('[data-testid="paper-state"]').exists()).toBe(false)
  expect(b.classes()).not.toContain('price-greyed')
  expect(w.emitted('summary').at(-1)[0].affected).toBe(1)
})
```

With the diff applied, the full vitest suite passed on `lanen/adr56` at b4c5ec83 (3275 tests), so no existing PaperStrategies test needs to change.

### frontend/src/pages/StrategyBuilderPage.vue (Lane V)

No change needed from Lane N. Lane N did not edit it. The builder's own paper panel (`PaperBookPanel.vue`) and the tracking lines
(`frontend/src/lib/tracking.js`) already say "As of" only for the price's time (`last_price_at`) and "Checked at" for a read time.
Its `checked-at` lines (`Checked at {{ checkedAt }}`, ~lines 1361-1387) are already labelled as a read time and stay as they are.
Optional, only if Lane V wants the builder to carry the notice too: its own `MarketClosedBanner` (~line 1239) could become
`<PriceNotice :answer="..." />` using the page's index answer (`useIndexAnswer` is already on the page); not done here.

## For lane L

### frontend/src/pages/MyStrategiesPage.vue and frontend/src/pages/HomeOverviewPage.vue

No change needed. Why (ADR-330 (56)): the layout now mounts the one price notice above My Strategies (route flag `priceNotice`,
`frontend/src/router/routes.js`, `AppLayout.vue` > `LayoutPriceNotice.vue`), so the page needs no edit. Home shows the notice through
`IndexStrip.vue` (Lane N file), which Home already mounts.
"Select all N shown" counts only the rows that can be deleted; that is by design (REQ-070, e2e BULK-2), not a bug: no change.

If Lane L later adds a price notice of its own to My Strategies, remove `'strategies/my-strategies'` from `PRICE_NOTICE_ROUTES`
in `frontend/src/router/routes.js` so the notice does not show twice.
