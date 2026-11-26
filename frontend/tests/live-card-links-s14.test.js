// S-14 (owner live test 25 Nov): the Live card's name opens the strategy, a running paper card has a Stops link, and the
// entry column says "Entry price" for a placed (Running) strategy, "Planned entry" for an unplaced plan. Expected strings are
// written here. Exit is a link to the Paper tab (`exit=<id>`) that opens that list's own confirm: the card has no exit code of its own.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

let onPush = null
let failLegs = false
vi.mock('@/composables/useStrategyLive', async () => {
  const { ref } = await import('vue')
  return { useStrategyLive: (h) => { onPush = h.onPush; return { status: ref('live'), reconnecting: ref(false), reconnectingText: ref(''), follow() {}, stop() {} } } }
})
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: () => Promise.reject({ status: 404 }), post: () => Promise.resolve({ data: {} }) } }
})
vi.mock('@/lib/saveDraft', async (importActual) => {
  const actual = await importActual()
  return { ...actual, fetchSavedLegs: () => (failLegs ? Promise.reject(new Error('x')) : Promise.resolve([
    { underlying: 'NIFTY', instrument_id: 'NSE_FO:1001', action: 'SELL', lots: 1, planned_entry: '100.00', captured_at: '2026-11-25T09:20:00+05:30' }])) }
})
import LiveStrategyCard from '@/components/live/LiveStrategyCard.vue'

const outcome = () => ({ state: 'COMPUTED', underlying: 'NIFTY', status_label: null, reason: null, output_label: null, spot_level: '25575.00',
  spot_at: '2026-11-25T11:18:00+05:30', answered_at: '2026-11-25T11:18:01+05:30',
  summary: { max_profit_display: '+1,985', max_loss_display: '−4,515', breakevens_display: [] },
  legs: [{ instrument_id: 'NSE_FO:1001', symbol: 'N1', action: 'SELL', lots: 1, planned_entry_display: '88.50', ltp: '80.00', health: 'available' }] })
const strat = (id, word) => ({ id, name: `S${id}`, underlying: 'NIFTY', status: 'draft', status_word: word, has_order: word === 'Running', created_at: '2026-11-25T09:00:00+05:30', updated_at: '2026-11-25T09:00:00+05:30' })

async function mountCard(strategy, push = true) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/:p(.*)*', component: { template: '<div/>' } }] })
  router.push('/')
  await router.isReady()
  const w = mount(LiveStrategyCard, { props: { strategy }, global: { plugins: [router] } })
  await flushPromises()
  if (push) { onPush(outcome()); await flushPromises() }
  return w
}
beforeEach(() => { failLegs = false; onPush = null })

describe('S-14 Live card links', () => {
  it('the name opens /strategy/builder?strategy=<id>, the title text stays', async () => {
    const w = await mountCard(strat(168, 'Running'))
    expect(w.get('[data-testid="live-strategy-open"]').attributes('href')).toBe('/strategy/builder?strategy=168')
    expect(w.get('[data-testid="live-strategy-title"]').text()).toContain('S168')
  })
  it('a running card has a Stops link to the paper tab of its strategy', async () => {
    const w = await mountCard(strat(168, 'Running'))
    expect(w.get('[data-testid="live-strategy-stops"]').attributes('href')).toBe('/positions/current-positions?tab=paper&strategy=168')
    expect(w.get('[data-testid="live-strategy-exit"]').attributes('href')).toBe('/positions/current-positions?tab=paper&strategy=168&exit=168')
    expect(w.get('[data-testid="live-strategy-exit"]').text()).toBe('Exit')
  })
  it('a Completed card has the name link and no Stops link', async () => {
    const w = await mountCard(strat(170, 'Completed'))
    expect(w.find('[data-testid="live-strategy-open"]').exists()).toBe(true)
    expect(w.find('[data-testid="live-strategy-stops"]').exists()).toBe(false)
    expect(w.find('[data-testid="live-strategy-exit"]').exists()).toBe(false)
  })
  it('a Draft card has no Stops link', async () => {
    const w = await mountCard(strat(171, 'Draft'))
    expect(w.find('[data-testid="live-strategy-stops"]').exists()).toBe(false)
  })
  it('a card in error state has no links at all, title stays text', async () => {
    failLegs = true
    const w = await mountCard(strat(168, 'Running'), false)
    expect(w.get('[data-testid="live-strategy-card"]').attributes('data-state')).toBe('error')
    expect(w.find('[data-testid="live-strategy-open"]').exists()).toBe(false)
    expect(w.find('[data-testid="live-strategy-stops"]').exists()).toBe(false)
    expect(w.find('[data-testid="live-strategy-exit"]').exists()).toBe(false)
    expect(w.get('[data-testid="live-strategy-title"]').text()).toContain('S168')
  })
  it('entry column head: "Entry price" for a placed (Running) strategy, "Planned entry" for an unplaced plan', async () => {
    const placed = await mountCard(strat(168, 'Running'))
    expect(placed.get('[data-testid="live-legs"] thead').text()).toContain('Entry price')
    expect(placed.get('[data-testid="live-legs"] thead').text()).not.toContain('Planned entry')
    const plan = await mountCard(strat(171, 'Draft'))
    expect(plan.get('[data-testid="live-legs"] thead').text()).toContain('Planned entry')
    expect(plan.get('[data-testid="live-legs"] thead').text()).not.toContain('Entry price')
  })
})
