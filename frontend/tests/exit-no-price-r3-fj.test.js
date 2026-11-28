// Lane FJ (R3) item 5 (TD O-3). Real case ADJ-02a: one contract (NIFTY 9 Nov 23500 CE) had no price; Exit (1) stayed blue and the dialog said
// "Prices are not live; try again when they update" without saying which contract. Now: "No price for <contract>", and the Exit button is grey
// beforehand with that line. A failed read or an unreadable state keeps the old general sentence (nothing leg-specific is known). Spec basis: REQ-109 AC-5, ADR-322 (3), ADR-016..019.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import REAL0 from './fixtures/paper-strategies.json'
import { closedFrom } from './_closedRows'
import { exitEndText, legsNoPrice } from '@/lib/usePaperExit'
import { NOT_LIVE_EXIT } from '@/lib/priceState'
import { TRACKING_REFRESH_MS } from '@/lib/tracking'

const REAL = { ...REAL0, strategies: REAL0.strategies.map((s) => ({ ...s, closed: closedFrom(s.positions) })) }
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url) => {
    const a = answers[`${method} ${url}`] ?? (method === 'GET' && url === '/market/exit-state' ? async () => ({ data: { closed: false, sentence: null, next_open_at: null } }) : undefined)
    return a ? a() : Promise.reject({ message: 'no answer', parts: null, status: null })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST'), delete: reply('DELETE') } }
})
import PaperStrategies from '@/components/strategy/PaperStrategies.vue'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'

describe('legsNoPrice: which ticked legs have no price (null when the block is not about a leg)', () => {
  const pos = [{ id: 1, live: true }, { id: 2, live: false }, { id: 3, live: true }]
  it('names the unpriced ticked legs only', () => { expect(legsNoPrice('PAUSED', pos, [1, 2])).toEqual([2]) })
  it('all priced: null', () => { expect(legsNoPrice('LIVE', pos, [1, 3])).toBeNull() })
  it('not connected: every ticked leg has no price', () => { expect(legsNoPrice('NOT_CONNECTED', pos, [1, 3])).toEqual([1, 3]) })
  it('unknown or missing state, positions not an array, a leg not listed, nothing ticked: null (the general sentence)', () => {
    expect(legsNoPrice(undefined, pos, [2])).toBeNull()
    expect(legsNoPrice('WEIRD', pos, [2])).toBeNull()
    expect(legsNoPrice('LIVE', undefined, [2])).toBeNull()
    expect(legsNoPrice('LIVE', pos, [9])).toBeNull()
    expect(legsNoPrice('LIVE', pos, [])).toBeNull()
  })
  it('a live flag that is not exactly true is no price (fail closed)', () => { expect(legsNoPrice('LIVE', [{ id: 1, live: 'live' }], [1])).toEqual([1]) })
})
describe('exitEndText no_price', () => {
  it('one or several names, no "<names>:" prefix', () => {
    expect(exitEndText('no_price', ['NIFTY 9 Nov 23500 CE'])).toBe('No price for NIFTY 9 Nov 23500 CE')
    expect(exitEndText('no_price', ['A 1 CE', 'B 2 PE'])).toBe('No price for A 1 CE, B 2 PE')
  })
  it('the general sentence is unchanged', () => { expect(exitEndText('not_live', ['A'])).toBe(`A: ${NOT_LIVE_EXIT}`) })
})

const mounted = []
beforeEach(() => { vi.useFakeTimers() })
afterEach(() => { vi.useRealTimers(); while (mounted.length) mounted.pop().unmount(); document.body.innerHTML = '' })
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const withLegDown = (contractId) => {
  const book = JSON.parse(JSON.stringify(REAL))
  const p = book.strategies[1].positions.find((x) => x.contract_id === contractId)
  p.price_state = 'stale'; p.ltp = null; p.ltp_text = null
  return book
}
const ID = REAL.strategies[1].strategy_id
async function list(book) {
  answers = { 'GET /paper/strategies': async () => ({ data: book }) }
  const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: PaperStrategies }, { path: '/strategy/builder', component: { template: '<div/>' } }] })
  r.push('/')
  await r.isReady()
  const w = mount(PaperStrategies, { global: { plugins: [r] }, attachTo: document.body })
  mounted.push(w)
  await flushPromises()
  return w
}
const reason = (w) => { const g = w.find(`[data-testid="paper-group"][data-strategy="${ID}"]`); const r = g.find('[data-testid="paper-exit-reason"]'); return r.exists() ? r.text() : null }
const tick = async (w, cid) => { await t(w, `select-leg-${ID}-${cid}`).setValue(true); await flushPromises() }
const NAME_784 = /^No price for NIFTY.*23000 CE/

describe('Positions: Exit opens the dialog that says which contract has no price', () => {
  it('a ticked leg with no price: Exit (1) is enabled, opens the dialog, the sentence names the contract, Confirm is off (ADR-330)', async () => {
    const w = await list(withLegDown(784))
    await tick(w, 784)
    expect(t(w, `exit-selected-${ID}`).attributes('disabled')).toBeUndefined()
    await t(w, `exit-selected-${ID}`).trigger('click')
    await flushPromises()
    const dlg = w.findComponent(PaperConfirmDialog)
    expect(dlg.props('open')).toBe(true)
    expect(dlg.props('blocked')).toBe(true)
    expect(dlg.props('error')).toMatch(NAME_784)
    expect(document.body.querySelector('[data-testid="paper-confirm-button"]').disabled).toBe(true)
  })
  it('only the priced leg ticked: Exit enabled, no such line', async () => {
    const w = await list(withLegDown(784))
    await tick(w, 776)
    expect(t(w, `exit-selected-${ID}`).attributes('disabled')).toBeUndefined()
    expect(reason(w)).toBeNull()
  })
  it('both ticked: the line names only the unpriced one', async () => {
    const w = await list(withLegDown(784))
    await tick(w, 776)
    await tick(w, 784)
    expect(t(w, `exit-selected-${ID}`).attributes('disabled')).toBeUndefined()
    await t(w, `exit-selected-${ID}`).trigger('click')
    await flushPromises()
    const dlg = w.findComponent(PaperConfirmDialog)
    expect(dlg.props('open')).toBe(true)
    expect(dlg.props('blocked')).toBe(true)
    expect(dlg.props('error')).toMatch(/^No price for [^,]*23000 CE$/)
    expect(document.body.querySelector('[data-testid="paper-confirm-button"]').disabled).toBe(true)
  })
  it('nothing ticked: the tick line, as before', async () => {
    const w = await list(withLegDown(784))
    expect(reason(w)).toBe('Tick a leg to exit.')
  })
  it('the dialog open on a priced leg, then a good read takes that leg\'s price: Confirm off and the sentence names it', async () => {
    const w = await list(JSON.parse(JSON.stringify(REAL)))
    await tick(w, 784)
    await t(w, `exit-selected-${ID}`).trigger('click')
    await flushPromises()
    const dlg = w.findComponent(PaperConfirmDialog)
    expect(dlg.props('open')).toBe(true)
    const down = withLegDown(784)
    answers['GET /paper/strategies'] = async () => ({ data: down })
    await vi.advanceTimersByTimeAsync(TRACKING_REFRESH_MS)
    await flushPromises()
    expect(dlg.props('blocked')).toBe(true)
    expect(dlg.props('error')).toMatch(/^No price for NIFTY.*23000 CE$/)
  })
})
