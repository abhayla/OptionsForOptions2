// Rewritten by Lane R2 (owner 28 Nov: "paper and real trades are same now"; withdraws ADR-330 (64)). A REAL position's row shows the same
// Exit and Stops as paper and ONE line (the server's, else the proposal); its stored actions are never sent. A row whose tag cannot be
// read (unknown, missing) shows neither control and says why (fail closed, the unknown lock stays); a paper row is unchanged.
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

let onPush = null
vi.mock('@/composables/useStrategyLive', async () => {
  const { ref } = await import('vue')
  return { useStrategyLive: (h) => (onPush = h.onPush, { status: ref('live'), reconnecting: ref(false), reconnectingText: ref(''), follow() {}, stop() {} }) }
})
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: () => Promise.reject({ status: 404 }), post: () => Promise.resolve({ data: {} }) } }
})
vi.mock('@/lib/saveDraft', async (importActual) => {
  const actual = await importActual()
  return { ...actual, fetchSavedLegs: () => Promise.resolve([
    { underlying: 'NIFTY', instrument_id: 'NSE_FO:1001', action: 'SELL', lots: 1, planned_entry: '100.00', captured_at: '2026-11-25T09:20:00+05:30' }]) }
})
import LiveStrategyCard from '@/components/live/LiveStrategyCard.vue'
import { isActionableKind } from '@/lib/positionKind'

const REAL_LINE = 'Real position. Zerodha shows its quantity and P&L. Exits and stops you store here are not sent. Place them in Kite.'
const UNKNOWN_LINE = 'Cannot tell whether this is a real or a paper position, so Exit and Stops are not shown. Check it in Kite.'
const strat = (over = {}) => ({ id: 5, name: 'S5', underlying: 'NIFTY', status: 'draft', status_word: 'Running', has_order: true, created_at: '2026-11-25T09:00:00+05:30', updated_at: '2026-11-25T09:00:00+05:30', revision: 1, leg_count: 1, first_leg: { instrument: 'N1', strike: '25500', expiry: '2026-12-01' }, ...over })
const outcome = () => ({ state: 'COMPUTED', underlying: 'NIFTY', status_label: null, reason: null, output_label: null, spot_level: '25575.00',
  spot_at: '2026-11-25T11:18:00+05:30', answered_at: '2026-11-25T11:18:01+05:30',
  summary: { max_profit_display: '+1,985', max_loss_display: '−4,515', breakevens_display: [] },
  legs: [{ instrument_id: 'NSE_FO:1001', symbol: 'N1', action: 'SELL', lots: 1, planned_entry_display: '88.50', ltp: '80.00', health: 'available' }] })
const mountCard = async (s) => {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/:p(.*)*', component: { template: '<div/>' } }] })
  router.push('/')
  await router.isReady()
  const w = mount(LiveStrategyCard, { props: { strategy: s }, global: { plugins: [router] } })
  await flushPromises()
  onPush(outcome())
  await flushPromises()
  return w
}
const t = (w, id) => w.find(`[data-testid="${id}"]`)

describe('Live card by position kind', () => {
  it('real: the server line, Exit and Stops like paper', async () => {
    const w = await mountCard(strat({ position_kind: 'real', position_kind_text: REAL_LINE }))
    expect(t(w, 'live-position-kind-line').text()).toBe(REAL_LINE)
    expect(t(w, 'live-strategy-exit').exists()).toBe(true)
    expect(t(w, 'live-strategy-stops').exists()).toBe(true)
  })
  it('paper: Exit and Stops, no line', async () => {
    const w = await mountCard(strat({ position_kind: 'paper', position_kind_text: null }))
    expect(t(w, 'live-strategy-exit').exists()).toBe(true)
    expect(t(w, 'live-strategy-stops').exists()).toBe(true)
    expect(t(w, 'live-position-kind-line').exists()).toBe(false)
  })
  it('unknown or missing tag: neither control, and a line saying why', async () => {
    for (const over of [{ position_kind: 'unknown', position_kind_text: UNKNOWN_LINE }, {}]) {
      const w = await mountCard(strat(over))
      expect(t(w, 'live-strategy-exit').exists()).toBe(false)
      expect(t(w, 'live-strategy-stops').exists()).toBe(false)
      expect(t(w, 'live-position-kind-line').text()).toContain('Exit and Stops are not shown')
    }
  })
})

describe('only exactly "paper" or "real" offers Exit', () => {
  it('none, unknown, missing and odd words do not', () => {
    expect(isActionableKind({ position_kind: 'paper' })).toBe(true)
    expect(isActionableKind({ position_kind: 'real' })).toBe(true)
    for (const k of ['none', 'unknown', 'Paper', 'Real', '', undefined, null]) expect(isActionableKind({ position_kind: k })).toBe(false)
    expect(isActionableKind(null)).toBe(false)
  })
})
