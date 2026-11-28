// Lane FA r2, I-17 (ADR-330 (60), (58), REQ-109 AC-5): the Exit dialog says in ONE plain line how old its price is.
// Real case 27 Nov 2026 16:02 Positions: 9 paper trades "no price", the dialog still opened and said nothing about the price.
// States, each its own line: no price | time absent | time unreadable | not live | age in seconds / minutes / hours / days.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'
import { priceAgeLine } from '@/lib/priceState'

vi.mock('@/services/api', () => ({ default: { get: () => Promise.resolve({ data: { closed: false } }), post: () => Promise.resolve({ data: {} }) } }))

const NOW = Date.parse('2026-11-27T10:42:00+05:30')
const AT = '2026-11-27T10:41:20+05:30' // 40 s before NOW
const row = (o = {}) => ({ key: 'a', kind: 'exit', side: 'BUY', text: 'NIFTY 25500 PE', lots: 1, lot_size: 65, price: '42.55', price_at: AT, contract_id: 1, ...o })
const mounted = []
const open = async (orders, extra = {}) => {
  const w = mount(PaperConfirmDialog, { props: { open: true, orders, nowMs: NOW, ...extra }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  return w
}
const line = (w) => w.find('[data-testid="paper-price-age"]')
afterEach(() => { while (mounted.length) mounted.pop().unmount() })

describe('priceAgeLine: the one as-of formatter', () => {
  const at = (iso, extra = {}) => priceAgeLine([row({ price_at: iso })], { nowMs: NOW, ...extra })
  it('seconds', () => expect(at(AT)).toEqual({ state: 'fresh', text: 'Price as of 10:41:20 IST, 40 seconds ago.' }))
  it('stale by minutes', () => expect(at('2026-11-27T10:35:00+05:30')).toEqual({ state: 'stale', text: 'Price as of 10:35:00 IST, 7 minutes ago.' }))
  it('hours', () => expect(at('2026-11-27T07:42:00+05:30').text).toBe('Price as of 07:42:00 IST, 3 hours ago.'))
  it('days carries the date', () => expect(at('2026-11-24T10:00:00+05:30').text).toBe('Price as of 24 Nov 2026, 10:00:00 IST, 3 days ago.'))
  it('not live names the time and the age', () => expect(at('2026-11-27T10:35:00+05:30', { notLive: true })).toEqual({ state: 'not_live', text: 'Prices are not live. Last price as of 10:35:00 IST, 7 minutes ago.' }))
  it('the oldest quote of several rows is the one told', () => expect(priceAgeLine([row(), row({ key: 'b', price_at: '2026-11-27T10:35:00+05:30' })], { nowMs: NOW }).text).toContain('10:35:00'))
  it('absent price', () => expect(priceAgeLine([row({ price: '', price_at: null })], { nowMs: NOW })).toEqual({ state: 'no_price', text: 'No price for 1 of 1 legs; the server prices the exit when you confirm.' }))
  it('price without a time', () => expect(priceAgeLine([row({ price_at: null })], { nowMs: NOW })).toEqual({ state: 'no_time', text: 'The time of the price is not available.' }))
  it('unparseable time is a different state from absent', () => expect(priceAgeLine([row({ price_at: '27/11 10:41' })], { nowMs: NOW })).toEqual({ state: 'unreadable', text: 'The time of the price could not be read.' }))
  it('a quote from the future is never "ago" and is not called fresh', () => expect(at('2026-11-27T10:50:00+05:30')).toEqual({ state: 'ahead', text: 'Price as of 10:50:00 IST.' }))
  it('no exit rows: nothing', () => expect(priceAgeLine([row({ kind: 'open' })], { nowMs: NOW })).toEqual({ state: '', text: '' }))
})

describe('the dialog shows the line', () => {
  it('fresh', async () => expect(line(await open([row()])).text()).toBe('Price as of 10:41:20 IST, 40 seconds ago.'))
  it('minutes old', async () => expect(line(await open([row({ price_at: '2026-11-27T10:35:00+05:30' })])).text()).toContain('7 minutes ago'))
  it('no price (27 Nov 16:02 case): the dialog opens and says so', async () => {
    const w = await open([row({ price: '', price_at: null }), row({ key: 'b', price: '', price_at: null })])
    expect(line(w).text()).toBe('No price for 2 of 2 legs; the server prices the exit when you confirm.')
    expect(w.find('[data-testid="paper-orders"]').exists()).toBe(true)
  })
  it('absent time', async () => expect(line(await open([row({ price_at: null })])).text()).toBe('The time of the price is not available.'))
  it('unreadable time', async () => expect(line(await open([row({ price_at: 'garbage' })])).text()).toBe('The time of the price could not be read.'))
  it('not live line set: age line says not live', async () => expect(line(await open([row({ price_at: '2026-11-27T10:35:00+05:30' })], { notLiveLine: 'x' })).text()).toBe('Prices are not live. Last price as of 10:35:00 IST, 7 minutes ago.'))
  it('an entry-only dialog has no age line', async () => expect(line(await open([row({ kind: 'open' })])).exists()).toBe(false))
})

describe('review F3: the line is told against the time of the Confirm press, not only the opening', () => {
  it('after minutes with the dialog open, pressing Confirm refreshes the line (no 5 seconds ago)', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(Date.parse('2026-11-27T10:41:25+05:30'))
    const w = mount(PaperConfirmDialog, { props: { open: true, orders: [row()] }, attachTo: document.body })
    mounted.push(w)
    await flushPromises()
    expect(line(w).text()).toBe('Price as of 10:41:20 IST, 5 seconds ago.')
    vi.setSystemTime(Date.parse('2026-11-27T10:58:00+05:30'))
    await w.get('[data-testid="paper-confirm-button"]').trigger('click')
    await flushPromises()
    vi.useRealTimers()
    expect(line(w).text()).toBe('Price as of 10:41:20 IST, 16 minutes ago.')
  })
})
