// Lane R2 CORE (owner 28 Nov 2026: "paper and real trades are same now"): a REAL row on Live Strategies shows the same Exit and Stops links
// as paper, and under it the one line "Not sent to Zerodha. Place it in Kite."; the dialog says the exit is only stored; the P&L and the
// shown quantity never change because of a stored action. Mocked contract: position_kind real, stored_not_sent true, record {action, stored_at, price}.
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
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'
import { NOT_SENT_LINE, REAL_EXIT_DIALOG_TEXT, recordLineOf } from '@/lib/positionKind'

const REAL_ROW = 'Real position. Zerodha shows its quantity and P&L. Exits and stops you store here are not sent. Place them in Kite.'
const strat = (over = {}) => ({ id: 5, name: 'S5', underlying: 'NIFTY', status: 'draft', status_word: 'Running', has_order: true, created_at: '2026-11-25T09:00:00+05:30', updated_at: '2026-11-25T09:00:00+05:30', revision: 1, leg_count: 1, first_leg: { instrument: 'N1', strike: '25500', expiry: '2026-12-01' }, ...over })
const outcome = () => ({ state: 'COMPUTED', underlying: 'NIFTY', status_label: null, reason: null, output_label: null, spot_level: '25575.00',
  spot_at: '2026-11-25T11:18:00+05:30', answered_at: '2026-11-25T11:18:01+05:30',
  summary: { max_profit_display: '+1,985', max_loss_display: '−4,515', breakevens_display: [] },
  legs: [{ instrument_id: 'NSE_FO:1001', symbol: 'N1', action: 'SELL', lots: 1, planned_entry_display: '88.50', ltp: '80.00', health: 'available' }] })
const PNL = { kind: 'value', text: '+1,234.50', label: 'Zerodha figure' }
const mountCard = async (s) => {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/:p(.*)*', component: { template: '<div/>' } }] })
  router.push('/')
  await router.isReady()
  const w = mount(LiveStrategyCard, { props: { strategy: s, pnl: PNL }, global: { plugins: [router] } })
  await flushPromises()
  onPush(outcome())
  await flushPromises()
  return w
}
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const RECORD = { action: 'exit', stored_at: '2026-11-28T10:32:00+05:30', price: '120.50' }

describe('R2 core: a real row gets the paper screens and says nothing was sent', () => {
  it('Live card: Exit and Stops links, the row line, the record line; P&L and quantity text unchanged', async () => {
    const before = await mountCard(strat({ position_kind: 'real', position_kind_text: REAL_ROW }))
    const w = await mountCard(strat({ position_kind: 'real', position_kind_text: REAL_ROW, stored_not_sent: true, record: RECORD }))
    expect(t(w, 'live-strategy-exit').exists()).toBe(true)
    expect(t(w, 'live-strategy-stops').exists()).toBe(true)
    expect(t(w, 'live-position-kind-line').text()).toBe(REAL_ROW)
    expect(t(w, 'live-record-line').text()).toBe('Exit stored 10:32:00 at 120.50. Not sent to Zerodha. Place it in Kite.')
    expect(t(w, 'live-record-line').text()).toContain(NOT_SENT_LINE)
    // a stored action changes neither the P&L nor the legs text
    expect(t(w, 'live-pnl').text()).toBe(t(before, 'live-pnl').text())
    expect(t(w, 'live-pnl-figure').text()).toBe('+1,234.50')
    expect(w.text().replace(t(w, 'live-record-line').text(), '')).toBe(before.text())
  })
  it('the Exit dialog for a real position says the exit is only stored, before the press', () => {
    const orders = [{ key: 'k1', side: 'BUY', text: 'NIFTY 25500 CE', lots: 1, lot_size: 75, price: '0', kind: 'exit', contract_id: 'NSE_FO:1001' }]
    const w = mount(PaperConfirmDialog, { props: { open: true, orders, kind: 'real' }, global: { stubs: { teleport: true } } })
    expect(w.text()).toContain('Exit Real (stored, not sent) positions')
    expect(w.get('[data-testid="real-not-sent"]').text()).toContain(REAL_EXIT_DIALOG_TEXT)
    expect(w.find('[data-testid="paper-not-real"]').exists()).toBe(false) // "This is not a real trade" would be false here
  })
  it('recordLineOf: absent, not stored, unreadable record', () => {
    expect(recordLineOf({})).toBeNull()
    expect(recordLineOf({ stored_not_sent: false, record: RECORD })).toBeNull()
    expect(recordLineOf({ stored_not_sent: true })).toBe(NOT_SENT_LINE)
    expect(recordLineOf({ stored_not_sent: true, record: { action: 'exit', stored_at: 'garbage', price: null } })).toBe(`Exit stored. ${NOT_SENT_LINE}`)
  })
})
