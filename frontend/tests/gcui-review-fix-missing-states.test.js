// GC-UI review fixes 2 and 4: a missing field is a dash (never "null"/empty); an exit is decided from the server's own
// marker, never from a price text; money text is the server's, printed as sent (a true zero is "0.00", no sign).
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

let reply = null
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: () => Promise.resolve({ data: reply }), post: () => Promise.reject(new Error('no')) } }
})
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import AdvancedDetails from '@/components/strategy/AdvancedDetails.vue'
import { readTracking } from '@/lib/tracking'
import { MISSING_REASONS } from '@/lib/dataHealthText'

const leg = (i, over = {}) => ({
  leg_index: i, instrument_id: `NSE_FO:${i + 1}`, action: 'BUY', instrument: 'CE', strike: '22300.00', expiry: '2026-11-03',
  quantity: 65, entry_price: '114.25', entry_price_display: '114.25', current_price: '113.60', current_price_display: '113.60',
  price_state: 'live', exit_price: null, exited_at: null, ...over,
})
const item = (over = {}) => ({
  strategy_id: 48, name: '"P"', underlying: 'NIFTY', started_at: '2026-10-28T05:03:10Z', state: 'LIVE', pause_reason: null,
  as_of: null, total: '0.00', booked: '0.00', unbooked: '0.00', total_text: '0.00', booked_text: '0.00', unbooked_text: '0.00',
  legs: [leg(0)], ...over,
})
async function show(it) {
  reply = { strategies: [it], answered_at: '2026-10-28T06:00:00Z' }
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }] })
  router.push('/')
  await router.isReady()
  const w = mount(PaperStrategies, { global: { plugins: [router] } })
  await flushPromises()
  return w
}
const text = (w, id) => w.get(`[data-testid="${id}"]`).text()
beforeEach(() => { reply = null })

describe('review fix 4: money text is the server text, printed as sent', () => {
  it('a true zero from the server prints "0.00" (no sign) and the browser rewrites nothing', async () => {
    const w = await show(item())
    expect(['paper-total', 'paper-unbooked', 'paper-booked'].map((id) => text(w, id))).toEqual(['0.00', '0.00', '0.00'])
  })
  it('the browser does not repair a signed zero: "+0.00" from the server is shown as sent (the server is the one to fix)', async () => {
    const w = await show(item({ total_text: '+0.00' }))
    expect(text(w, 'paper-total')).toBe('+0.00')
  })
  it('a missing text is a dash, never a figure formed from the raw number', async () => {
    const w = await show(item({ total: '195.00', total_text: undefined }))
    expect(text(w, 'paper-total')).toBe('—')
  })
  it('the colour follows the sign of the server text, including the true minus sign', async () => {
    const w = await show(item({ total: '-5.00', total_text: '−5.00' }))
    expect(w.get('[data-testid="paper-total"]').classes()).toContain('text-loss')
  })
})

describe('review fix 2: missing exit price text, exit decided from the server marker', () => {
  it('an exited leg with no exit price text reads "Exited at —", never "Exited at null"', async () => {
    const w = await show(item({ legs: [leg(0, { exited_at: '2026-10-28T09:00:00Z', pnl_kind: 'booked', price_state: 'exited', exit_price: '50.25' })] }))
    const cell = w.get('[data-testid="paper-leg"]').text()
    expect(cell).toContain('Exited at —')
    expect(cell).not.toContain('null')
  })
  it('a leg with an exit price text but no exited marker is still open (a text does not decide it)', async () => {
    const w = await show(item({ legs: [leg(0, { exit_price: '50.25', exit_price_display: '50.25' })] }))
    expect(w.get('[data-testid="paper-leg"]').text()).not.toContain('Exited')
  })
  it('readTracking: exited from exited_at / booked, with exitPrice null when no text came', () => {
    const body = { state: 'LIVE', paper_pnl: '1.00', booked: '1.00', unbooked: '0.00', detections: [], legs: [
      leg(0, { exited_at: '2026-10-28T09:00:00Z' }), leg(1, { exit_price_display: '9.00' }), leg(2, { pnl_kind: 'booked' })] }
    const r = readTracking(body)
    expect(r.legs.map((l) => [l.exited, l.exitPrice])).toEqual([[true, null], [false, '9.00'], [true, null]])
  })
  it('Advanced details: a bid with no text and no reason shows a dash, not an empty cell', () => {
    const w = mount(AdvancedDetails, { props: { rows: [{ instrument_id: 'a', bid: '1', ask: '2', health: 'available' }], nameOf: (r) => r.instrument_id } })
    expect(w.get('[data-testid="adv-bid"]').text()).toBe('—')
    expect(w.get('[data-testid="adv-ask"]').text()).toBe('—')
    expect(MISSING_REASONS).toBeTruthy()
  })
})
