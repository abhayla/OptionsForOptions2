// GC-6 shared states: each approved text, state, prop and emit is pinned. A text change turns a test red.
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { readFileSync, readdirSync } from 'node:fs'
import { KITE_ORDER_BOOK_URL } from '@/lib/execute'
import MarketClosedBanner from '@/components/states/MarketClosedBanner.vue'
import SessionEndedCard from '@/components/states/SessionEndedCard.vue'
import TwoBasketStepper from '@/components/states/TwoBasketStepper.vue'
import ReturnStatus from '@/components/states/ReturnStatus.vue'
import EmptyState from '@/components/states/EmptyState.vue'
import * as T from '@/lib/sharedStateText'
import { routes } from '@/router/routes'

const t = (w, id) => w.get(`[data-testid="${id}"]`).text()

describe('MarketClosedBanner', () => {
  it('shows the exact text with the IST time', () => {
    const w = mount(MarketClosedBanner, { props: { pricesAt: '2026-10-19T15:30:00+05:30' } })
    expect(t(w, 'market-closed-text')).toBe('Market closed. Prices are from 19 Oct 2026, 15:30:00 IST.')
  })
  it('exposes disablesExecute, default false', () => {
    expect(mount(MarketClosedBanner, { props: { pricesAt: '2026-10-19T15:30:00+05:30' } }).get('[data-testid="market-closed-banner"]').attributes('data-disables-execute')).toBe('false')
    expect(mount(MarketClosedBanner, { props: { pricesAt: '2026-10-19T15:30:00+05:30', disablesExecute: true } }).get('[data-testid="market-closed-banner"]').attributes('data-disables-execute')).toBe('true')
  })
  it('never shows a raw string for an unusable time', () => {
    expect(t(mount(MarketClosedBanner, { props: { pricesAt: 'garbage' } }), 'market-closed-text')).toBe('Market closed. Prices are from Time not available.')
  })
})

describe('SessionEndedCard', () => {
  let router
  beforeEach(async () => {
    sessionStorage.clear()
    router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:p(.*)*', component: { template: '<i/>' } }] })
    router.push('/strategy/execute?x=1')
    await router.isReady()
  })
  it('shows the exact text and the Reconnect button', () => {
    const w = mount(SessionEndedCard, { global: { plugins: [router] } })
    expect(t(w, 'session-ended-text')).toBe('Zerodha session ended. Reconnect to continue')
    expect(t(w, 'session-reconnect')).toBe('Reconnect')
    expect(w.find('[data-testid="session-last-sync"]').exists()).toBe(false)
  })
  it('shows the last sync time', () => {
    const w = mount(SessionEndedCard, { props: { lastSyncAt: '2026-10-19T15:29:00+05:30' }, global: { plugins: [router] } })
    expect(t(w, 'session-last-sync')).toBe('Last synced 19 Oct 2026, 15:29:00 IST')
  })
  it('Reconnect emits and remembers the same route', async () => {
    const w = mount(SessionEndedCard, { global: { plugins: [router] } })
    await w.get('[data-testid="session-reconnect"]').trigger('click')
    expect(w.emitted('reconnect')[0][0]).toEqual({ returnTo: '/strategy/execute?x=1' })
    expect(sessionStorage.getItem(T.RETURN_ROUTE_KEY)).toBe('/strategy/execute?x=1')
  })
})

describe('TwoBasketStepper', () => {
  it('shows both steps exactly, no middle message at step 1', () => {
    const w = mount(TwoBasketStepper)
    expect(t(w, 'step-buys')).toBe('Step 1 of 2 Buys')
    expect(t(w, 'step-sells')).toBe('Step 2 of 2 Sells (locked until Zerodha confirms the fills)')
    expect(w.find('[data-testid="two-basket-message"]').exists()).toBe(false)
  })
  it('buys_filled state text', () => {
    expect(t(mount(TwoBasketStepper, { props: { state: 'buys_filled' } }), 'two-basket-message')).toBe('Buys filled. Sells not placed yet. Your position is not complete.')
  })
  it('buy_failed state text', () => {
    expect(t(mount(TwoBasketStepper, { props: { state: 'buy_failed' } }), 'two-basket-message')).toBe('Buy not executed - see Kite')
  })
  it('buy_failed links to Kite order book and the old text is gone from src (ADR-138 (6))', () => {
    const a = mount(TwoBasketStepper, { props: { state: 'buy_failed' } }).get('[data-testid="two-basket-kite-link"]')
    expect(a.attributes('href')).toBe(KITE_ORDER_BOOK_URL)
    expect(a.attributes('target')).toBe('_blank')
    expect(a.attributes('rel')).toBe('noopener')
    const walk = (d) => readdirSync(d, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(`${d}/${e.name}`) : [`${d}/${e.name}`]))
    const old = ['A buy', 'failed. Sells stay locked.'].join(' ')
    expect(walk('src').filter((f) => readFileSync(f, 'utf8').includes(old))).toEqual([])
  })
})

describe('ReturnStatus', () => {
  it('idle: button keeps the spec wording and emits check', async () => {
    const w = mount(ReturnStatus)
    expect(t(w, 'return-status-check')).toBe('Check with Zerodha')
    await w.get('[data-testid="return-status-check"]').trigger('click')
    expect(w.emitted('check')).toHaveLength(1)
  })
  it('checking text', () => {
    expect(t(mount(ReturnStatus, { props: { status: 'checking' } }), 'return-status-checking')).toBe('Checking with Zerodha…')
  })
  it('no change text', () => {
    expect(t(mount(ReturnStatus, { props: { status: 'no_change' } }), 'return-status-no-change')).toBe('no change detected yet')
  })
  it('done reads the approved text exactly (ADR-129); slot is only an extra below it', () => {
    const bare = mount(ReturnStatus, { props: { status: 'done' } })
    expect(t(bare, 'return-status-done-text')).toBe('Zerodha confirmed your orders.')
    expect(t(bare, 'return-status-done')).toBe('Zerodha confirmed your orders.')
    const w = mount(ReturnStatus, { props: { status: 'done' }, slots: { default: '<span data-testid="x">SLOT</span>' } })
    expect(t(w, 'return-status-done-text')).toBe('Zerodha confirmed your orders.')
    expect(t(w, 'x')).toBe('SLOT')
  })
  it('failed: Retry button emits retry', async () => {
    const w = mount(ReturnStatus, { props: { status: 'failed' } })
    expect(t(w, 'return-status-retry')).toBe('Retry')
    await w.get('[data-testid="return-status-retry"]').trigger('click')
    expect(w.emitted('retry')).toHaveLength(1)
  })
})

describe('EmptyState', () => {
  it('S4: message plus Create Strategy button that emits', async () => {
    const w = mount(EmptyState, { props: { message: T.EMPTY_S4_MESSAGE, actionLabel: T.EMPTY_S4_BUTTON } })
    expect(t(w, 'empty-state-message')).toBe('No saved strategies yet.')
    expect(t(w, 'empty-state-action')).toBe('Create Strategy')
    await w.get('[data-testid="empty-state-action"]').trigger('click')
    expect(w.emitted('action')).toHaveLength(1)
  })
  it('S6 and S7: exact messages plus Create Strategy button to the Create Strategy route (ADR-130)', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes })
    router.push('/orders')
    await router.isReady()
    for (const [msg, label, text] of [[T.EMPTY_S6_MESSAGE, T.EMPTY_S6_BUTTON, 'No orders yet.'], [T.EMPTY_S7_MESSAGE, T.EMPTY_S7_BUTTON, 'No open positions.']]) {
      const w = mount(EmptyState, { props: { message: msg, actionLabel: label, actionTo: T.CREATE_STRATEGY_ROUTE }, global: { plugins: [router] } })
      expect(t(w, 'empty-state-message')).toBe(text)
      expect(t(w, 'empty-state-action')).toBe('Create Strategy')
      await w.get('[data-testid="empty-state-action"]').trigger('click')
      await flushPromises()
      // The page is a lazy chunk (W-119): EmptyState does not await router.push, so wait for the navigation to settle.
      await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('strategies-create-strategy'))
      expect(router.currentRoute.value.name).toBe('strategies-create-strategy')
      expect(router.currentRoute.value.fullPath).toBe('/strategies/create-strategy')
      expect(router.currentRoute.value.fullPath).not.toBe('/strategy/builder')
      expect(w.emitted('action')).toHaveLength(1)
      await router.push('/orders')
    }
  })
  it('Create Strategy target is the create-strategy nav item route, by name, not the Strategy Builder', () => {
    expect(T.CREATE_STRATEGY_ROUTE).toEqual({ name: 'strategies-create-strategy' })
    const target = routes.find((r) => r.name === T.CREATE_STRATEGY_ROUTE.name)
    expect(target.path).toBe('/strategies/create-strategy')
    expect(target.path).not.toBe('/strategy/builder')
  })
})

describe('390 px class check', () => {
  it('no fixed pixel widths in the components; buttons have a 44 px tap target', () => {
    for (const f of ['MarketClosedBanner', 'SessionEndedCard', 'TwoBasketStepper', 'ReturnStatus', 'EmptyState']) {
      const src = readFileSync(`src/components/states/${f}.vue`, 'utf8')
      expect(src, f).not.toMatch(/\b(?:min-|max-)?w-\[\d+px\]|\bw-\d{2,}\b|width:\s*\d+px/)
      for (const m of src.matchAll(/<button[^>]*>/g)) expect(m[0], f).toContain('min-h-[44px]')
    }
  })
})
