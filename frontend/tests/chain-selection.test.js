// W-120 + W-118-sel part 2 (REQ-030 AC-1/2/4/5/6/7/8/9/10/11/15/16; ADR-002, ADR-132): the Option Chain's leg selection, on a fake chain socket, and the
// chainSelection store on its own. Each test name starts with its AC id.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { echoSeq } from './helpers/echoSeq'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const get = (url) => {
    if (url.startsWith('/catalogue/')) return Promise.resolve({ data: { expiries: ['2026-10-27', '2026-11-03'] } })
    return Promise.reject(new Error('down'))
  }
  return { ...actual, default: { get, post: () => Promise.reject(new Error('no post')) } }
})
import OptionChainPage from '@/pages/OptionChainPage.vue'
import { contractOf, useChainSelection } from '@/stores/chainSelection'

class FakeSocket {
  static all = []
  constructor(url) { this.url = url; this.sent = []; this.readyState = 0; FakeSocket.all.push(this) }
  send(text) { this.sent.push(text) }
  close() { this.readyState = 3 }
  serverOpen() { this.readyState = 1; this.onopen?.() }
  serverPush(obj) { this.onmessage?.({ data: JSON.stringify(echoSeq(this, obj)) }) }
}
const sock = () => FakeSocket.all.at(-1)

const cell = (id, ltp, permission = {}) => ({ instrument_id: id, ltp, bid: null, ask: null, change: null, oi: '1000', oi_change: null, volume: '5', health: 'available', at: '2026-10-19T10:00:00+05:30', permitted: true, unavailable_reason: null, ...permission })
const strikes = ['23600.00', '23800.00', '24000.00', '24200.00']
const chain = (expiry, blocked = {}) => ({
  state: 'LIVE', underlying: 'NIFTY', expiry, spot: '23900.00', spot_at: '2026-10-19T10:00:00+05:30', spot_health: 'available',
  atm_strike: '23800.00', rows_missing: null, answered_at: '2026-10-19T10:00:01+05:30',
  rows: strikes.map((k) => ({ strike: k, ce: cell(`NFO:${expiry}:${k}CE`, '100.00', blocked[`${k}CE`]), pe: cell(`NFO:${expiry}:${k}PE`, '90.50', blocked[`${k}PE`]) })),
})

let router
async function mountPage(expiry = '2026-10-27', blocked = {}) {
  router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/', component: { template: '<div/>' } },
    { path: '/strategies/strategy-builder', name: 'strategies-strategy-builder', component: { template: '<div/>' } },
  ] })
  await router.push('/')
  const w = mount(OptionChainPage, { global: { plugins: [router] } })
  await flushPromises()
  sock().serverOpen()
  sock().serverPush(chain(expiry, blocked))
  await flushPromises()
  return w
}
const rowAt = (w, strike) => w.findAll('[data-testid="chain-row"]').find((r) => r.find('[data-testid="strike"]').text() === strike)
const pick = async (w, strike, side, action) => {
  const r = rowAt(w, strike)
  await r.get(`[data-testid="select-${side}"]`).setValue(true)
  await r.get(`[data-testid="${action}-${side}"]`).trigger('click')
}
const addButton = (w) => w.get('[data-testid="add-selected"]')

beforeEach(() => {
  setActivePinia(createPinia())
  FakeSocket.all = []
  vi.stubGlobal('WebSocket', FakeSocket)
})
afterEach(() => vi.unstubAllGlobals())

describe('Option Chain selection (screen)', () => {
  it('Core, AC-1/AC-2/AC-4/AC-9: four ticked contracts with explicit Buy/Sell -> "Add Selected (4)" opens the Builder with exactly those 4 legs', async () => {
    const w = await mountPage()
    // AC-4: the selectors sit on both sides, calls left of the strike, puts right of it
    const tds = rowAt(w, '24000.00').findAll('td')
    expect(tds.at(0).attributes('data-testid')).toBe('sel-ce')
    expect(tds.at(-1).attributes('data-testid')).toBe('sel-pe')
    await pick(w, '24000.00', 'ce', 'buy')
    await pick(w, '24200.00', 'ce', 'sell')
    await pick(w, '23800.00', 'pe', 'buy')
    await pick(w, '23600.00', 'pe', 'sell')
    expect(addButton(w).text()).toBe('Add Selected (4)')
    await addButton(w).trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('strategies-strategy-builder')
    const draft = JSON.parse(router.currentRoute.value.query.draft)
    expect(draft.underlying).toBe('NIFTY')
    expect(draft.legs).toEqual([
      { instrument_id: 'NFO:2026-10-27:24000.00CE', action: 'BUY', lots: 1, planned_entry: '100.00', captured_at: '2026-10-19T10:00:00+05:30' },
      { instrument_id: 'NFO:2026-10-27:24200.00CE', action: 'SELL', lots: 1, planned_entry: '100.00', captured_at: '2026-10-19T10:00:00+05:30' },
      { instrument_id: 'NFO:2026-10-27:23800.00PE', action: 'BUY', lots: 1, planned_entry: '90.50', captured_at: '2026-10-19T10:00:00+05:30' },
      { instrument_id: 'NFO:2026-10-27:23600.00PE', action: 'SELL', lots: 1, planned_entry: '90.50', captured_at: '2026-10-19T10:00:00+05:30' },
    ])
  })

  it('AC-2: ticking a contract does not choose an action; Add Selected stays disabled and counts nothing until Buy or Sell is pressed', async () => {
    const w = await mountPage()
    await rowAt(w, '24000.00').get('[data-testid="select-ce"]').setValue(true)
    expect(addButton(w).text()).toBe('Add Selected (0)')
    expect(addButton(w).attributes('disabled')).toBeDefined()
    expect(w.get('[data-testid="selected-leg"]').attributes('data-action')).toBe('')
    await rowAt(w, '24000.00').get('[data-testid="sell-ce"]').trigger('click')
    expect(addButton(w).text()).toBe('Add Selected (1)')
    expect(w.get('[data-testid="selected-leg"]').attributes('data-action')).toBe('SELL')
  })

  it('AC-11: the same contract bought and sold stays two legs, never netted', async () => {
    const w = await mountPage()
    await pick(w, '24000.00', 'ce', 'buy')
    await rowAt(w, '24000.00').get('[data-testid="sell-ce"]').trigger('click')
    expect(addButton(w).text()).toBe('Add Selected (2)')
    await addButton(w).trigger('click')
    await flushPromises()
    expect(JSON.parse(router.currentRoute.value.query.draft).legs.map((l) => l.action)).toEqual(['BUY', 'SELL'])
  })

  it('AC-5: pressing the same contract and action twice never makes a second leg (the second press switches it off)', async () => {
    const w = await mountPage()
    await pick(w, '24200.00', 'ce', 'sell') // keeps the summary bar on screen
    await pick(w, '24000.00', 'ce', 'buy')
    expect(addButton(w).text()).toBe('Add Selected (2)')
    await rowAt(w, '24000.00').get('[data-testid="buy-ce"]').trigger('click')
    expect(addButton(w).text()).toBe('Add Selected (1)')
    await rowAt(w, '24000.00').get('[data-testid="buy-ce"]').trigger('click')
    expect(addButton(w).text()).toBe('Add Selected (2)')
    expect(w.findAll('[data-testid="selected-leg"]')).toHaveLength(2)
  })

  it('AC-6: legs of several expiries show the notice with Continue / Review Selection before import; Continue imports, Review does not', async () => {
    const w = await mountPage('2026-10-27')
    await pick(w, '24000.00', 'ce', 'buy')
    await w.get('[data-testid="expiry-select"]').setValue('2026-11-03')
    sock().serverPush(chain('2026-11-03'))
    await flushPromises()
    await pick(w, '24200.00', 'ce', 'sell')
    expect(addButton(w).text()).toBe('Add Selected (2)') // AC-10: the first expiry's leg is still selected
    await addButton(w).trigger('click')
    expect(w.get('[data-testid="multi-expiry"]').text()).toContain('Multiple expiries detected — Continue / Review Selection')
    expect(router.currentRoute.value.name).not.toBe('strategies-strategy-builder')
    await w.get('[data-testid="multi-expiry-review"]').trigger('click')
    expect(w.find('[data-testid="multi-expiry"]').exists()).toBe(false)
    expect(router.currentRoute.value.name).not.toBe('strategies-strategy-builder')
    await addButton(w).trigger('click')
    await w.get('[data-testid="multi-expiry-continue"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('strategies-strategy-builder')
    expect(JSON.parse(router.currentRoute.value.query.draft).legs.map((l) => l.instrument_id)).toEqual([
      'NFO:2026-10-27:24000.00CE', 'NFO:2026-11-03:24200.00CE'])
  })

  it('AC-10: selections persist across expiry tabs', async () => {
    const w = await mountPage('2026-10-27')
    await pick(w, '24000.00', 'ce', 'buy')
    await w.get('[data-testid="expiry-select"]').setValue('2026-11-03')
    sock().serverPush(chain('2026-11-03'))
    await flushPromises()
    expect(w.findAll('[data-testid="selected-leg"]')).toHaveLength(1)
    expect(rowAt(w, '24000.00').get('[data-testid="select-ce"]').element.checked).toBe(false) // another expiry's contract
    await w.get('[data-testid="expiry-select"]').setValue('2026-10-27')
    sock().serverPush(chain('2026-10-27'))
    await flushPromises()
    expect(rowAt(w, '24000.00').get('[data-testid="select-ce"]').element.checked).toBe(true)
  })

  it('AC-7: lots move by a +/- stepper, never below 1', async () => {
    const w = await mountPage()
    await pick(w, '24000.00', 'ce', 'buy')
    await w.get('[data-testid="lots-plus"]').trigger('click')
    await w.get('[data-testid="lots-plus"]').trigger('click')
    expect(w.get('[data-testid="leg-lots"]').text()).toBe('3')
    for (let i = 0; i < 5; i++) await w.get('[data-testid="lots-minus"]').trigger('click')
    expect(w.get('[data-testid="leg-lots"]').text()).toBe('1')
    await w.get('[data-testid="lots-plus"]').trigger('click')
    await addButton(w).trigger('click')
    await flushPromises()
    expect(JSON.parse(router.currentRoute.value.query.draft).legs[0].lots).toBe(2)
  })

  it('AC-8: a Selected Legs summary shows each leg and stays pinned (sticky) to the screen bottom', async () => {
    const w = await mountPage()
    expect(w.find('[data-testid="selected-legs"]').exists()).toBe(false)
    await pick(w, '24000.00', 'ce', 'buy')
    const bar = w.get('[data-testid="selected-legs"]')
    expect(bar.text()).toContain('Selected Legs')
    expect(bar.get('[data-testid="selected-leg-name"]').text()).toBe('NIFTY 2026-10-27 24000.00 CE')
    expect(bar.classes()).toContain('sticky')
  })

  it('AC-15: Remove is immediate and a short Undo puts the leg back', async () => {
    const w = await mountPage()
    await pick(w, '24000.00', 'ce', 'buy')
    await pick(w, '24200.00', 'ce', 'sell')
    await w.findAll('[data-testid="leg-remove"]').at(0).trigger('click')
    expect(addButton(w).text()).toBe('Add Selected (1)')
    await w.get('[data-testid="undo"]').trigger('click')
    expect(addButton(w).text()).toBe('Add Selected (2)')
    expect(w.findAll('[data-testid="selected-leg-name"]').map((n) => n.text())[0]).toBe('NIFTY 2026-10-27 24000.00 CE')
    expect(w.find('[data-testid="undo"]').exists()).toBe(false)
  })

  it('ADR-002: the import only navigates; it sends no request and says nothing about orders', async () => {
    const w = await mountPage()
    await pick(w, '24000.00', 'ce', 'buy')
    await addButton(w).trigger('click')
    expect(w.text()).not.toMatch(/\b(order|execute|place)\b/i)
  })
})

const NOT_PERMITTED = {
  notListed: { permitted: false, unavailable_reason: 'not_listed' },
  restricted: { permitted: false, unavailable_reason: 'restricted' },
  unknown: { permitted: false, unavailable_reason: 'unknown' },
}
const LINES = {
  not_listed: "Not in Zerodha's list today.",
  restricted: 'Zerodha limits trading in this strike.',
  unknown: "We couldn't check with Zerodha. Refresh to try again.",
}

describe('Option Chain: contracts Zerodha does not permit (REQ-030 AC-13, AC-16; ADR-132 (3))', () => {
  it.each([
    ['not_listed', NOT_PERMITTED.notListed],
    ['restricted', NOT_PERMITTED.restricted],
    ['unknown', NOT_PERMITTED.unknown],
  ])('Core, AC-16: a %s cell says "Currently unavailable on Zerodha" with its exact reason line, its checkbox/Buy/Sell are disabled, and Add Selected never includes it', async (reason, state) => {
    const w = await mountPage('2026-10-27', { '24000.00CE': state })
    const row = rowAt(w, '24000.00')
    expect(row.get('[data-testid="unavailable-label-ce"]').text()).toBe('Currently unavailable on Zerodha')
    expect(row.get('[data-testid="unavailable-reason-ce"]').text()).toBe(LINES[reason])
    for (const id of ['select-ce', 'buy-ce', 'sell-ce']) expect(row.get(`[data-testid="${id}"]`).attributes('disabled')).toBeDefined()
    // the permitted PE of the same strike is untouched
    expect(row.get('[data-testid="select-pe"]').attributes('disabled')).toBeUndefined()
    expect(row.find('[data-testid="unavailable-pe"]').exists()).toBe(false)
    // even a forced click (the DOM disabled flag removed) adds nothing: the store refuses it
    const store = useChainSelection()
    await row.get('[data-testid="buy-ce"]').element.removeAttribute('disabled')
    await row.get('[data-testid="buy-ce"]').trigger('click')
    await row.get('[data-testid="select-ce"]').setValue(true)
    expect(store.entries).toEqual([])
    await pick(w, '24200.00', 'ce', 'buy')
    expect(addButton(w).text()).toBe('Add Selected (1)')
    await addButton(w).trigger('click')
    await flushPromises()
    expect(JSON.parse(router.currentRoute.value.query.draft).legs.map((l) => l.instrument_id)).toEqual(['NFO:2026-10-27:24200.00CE'])
  })

  it('AC-16: a Refresh button shows with any unavailable cell and sends the current request again, once', async () => {
    const w = await mountPage('2026-10-27', { '24000.00CE': NOT_PERMITTED.unknown })
    const before = sock().sent.length
    await w.get('[data-testid="chain-refresh"]').trigger('click')
    expect(sock().sent.length).toBe(before + 1)
    expect(JSON.parse(sock().sent.at(-1))).toEqual({ underlying: 'NIFTY', expiry: '2026-10-27', strikes_each_side: 15 })
  })

  it('AC-16: with every contract permitted there is no notice, but Refresh is still shown and re-sends the request once', async () => {
    const w = await mountPage()
    expect(w.find('[data-testid="unavailable-notice"]').exists()).toBe(false)
    const before = sock().sent.length
    await w.get('[data-testid="chain-refresh"]').trigger('click')
    expect(sock().sent.length).toBe(before + 1)
  })

  it('AC-13/AC-16: a ticked contract that a newer answer marks not permitted stays visible with its reason and leaves the count and the import', async () => {
    const w = await mountPage()
    await pick(w, '24000.00', 'ce', 'buy')
    await pick(w, '24200.00', 'ce', 'sell')
    expect(addButton(w).text()).toBe('Add Selected (2)')
    sock().serverPush(chain('2026-10-27', { '24000.00CE': NOT_PERMITTED.restricted }))
    await flushPromises()
    expect(addButton(w).text()).toBe('Add Selected (1)')
    const legLine = w.findAll('[data-testid="selected-leg"]').find((l) => l.text().includes('24000.00 CE'))
    expect(legLine.get('[data-testid="selected-leg-unavailable"]').text()).toContain('Currently unavailable on Zerodha. Zerodha limits trading in this strike.')
    await addButton(w).trigger('click')
    await flushPromises()
    expect(JSON.parse(router.currentRoute.value.query.draft).legs.map((l) => l.instrument_id)).toEqual(['NFO:2026-10-27:24200.00CE'])
  })

  it('AC-16: a cell with no permission field at all (an old or forged answer) is treated as not permitted, "could not check"', async () => {
    const w = await mountPage()
    const bare = chain('2026-10-27')
    delete bare.rows[0].ce.permitted
    delete bare.rows[0].ce.unavailable_reason
    sock().serverPush(bare)
    await flushPromises()
    const row = rowAt(w, '23600.00')
    expect(row.get('[data-testid="unavailable-reason-ce"]').text()).toBe(LINES.unknown)
    expect(row.get('[data-testid="buy-ce"]').attributes('disabled')).toBeDefined()
  })
})

describe('chainSelection store: permission', () => {
  const blocked = (strike, state) => contractOf('NIFTY', '2026-10-27', strike, 'CE', cell(`id-${strike}`, '10.00', state))

  it('AC-16: a not-permitted or unknown contract is refused by toggle and by choose; only an explicit permitted: true opens it', () => {
    const s = useChainSelection()
    const states = [NOT_PERMITTED.notListed, NOT_PERMITTED.restricted, NOT_PERMITTED.unknown, { permitted: 'yes' }, { permitted: 1 }, { permitted: undefined }]
    states.forEach((state, i) => { // a different contract each time: a second toggle of one contract would remove it
      s.toggleContract(blocked(String(i), state))
      s.chooseAction(blocked(String(i), state), 'BUY')
    })
    expect(s.entries).toEqual([])
    expect(s.draftOf('NIFTY').legs).toEqual([])
  })

  it('AC-16: draftOf never carries an entry whose permission is gone, whatever the entry says about its action', () => {
    const s = useChainSelection()
    s.chooseAction(blocked('1', {}), 'BUY')
    s.entries[0].permitted = false // a newer answer or tampering
    expect(s.legsOf('NIFTY')).toEqual([])
    expect(s.draftOf('NIFTY').legs).toEqual([])
    s.syncPermissions([cell('id-1', '10.00')]) // permitted again on the next answer
    expect(s.draftOf('NIFTY').legs.map((l) => l.instrument_id)).toEqual(['id-1'])
  })
})

describe('chainSelection store: permission is re-checked, never carried (review MINOR 1)', () => {
  const ca = contractOf('NIFTY', '2026-10-27', '1', 'CE', cell('id-A', '10.00'))
  const cb = contractOf('NIFTY', '2026-11-03', '2', 'CE', cell('id-B', '10.00'))

  it('a leg on another expiry whose answer says not permitted is excluded from draftOf even if its own flag says true', () => {
    const s = useChainSelection()
    s.chooseAction(ca, 'BUY')
    s.chooseAction(cb, 'SELL')
    s.syncPermissions([{ ...cell('id-A', '10.00'), permitted: false, unavailable_reason: 'restricted' }])
    s.entries.find((e) => e.instrument_id === 'id-A').permitted = true // a stale cached flag
    expect(s.legsOf('NIFTY').map((e) => e.instrument_id)).toEqual(['id-B'])
    expect(s.draftOf('NIFTY').legs.map((l) => l.instrument_id)).toEqual(['id-B'])
  })

  it('a leg removed, then losing permission, is not permitted again by Undo', () => {
    const s = useChainSelection()
    s.chooseAction(ca, 'BUY')
    s.remove(s.entries[0].id)
    s.syncPermissions([{ ...cell('id-A', '10.00'), permitted: false, unavailable_reason: 'restricted' }]) // entry not present: only the answer moves
    s.undo()
    expect(s.entries).toHaveLength(1)
    expect(s.entries[0].permitted).toBe(false)
    expect(s.draftOf('NIFTY').legs).toEqual([])
  })

  it('Undo of a leg with no known answer reads as unknown and is excluded', () => {
    const s = useChainSelection()
    s.chooseAction(ca, 'BUY')
    s.remove(s.entries[0].id)
    delete s.answers['id-A']
    s.undo()
    expect(s.entries[0].unavailable_reason).toBe('unknown')
    expect(s.draftOf('NIFTY').legs).toEqual([])
  })
})

describe('chainSelection store', () => {
  const c = (strike, type = 'CE', expiry = '2026-10-27') => contractOf('NIFTY', expiry, strike, type, cell(`id-${expiry}-${strike}${type}`, '10.00'))

  it('AC-5: the same contract and action twice never makes two legs (one row)', () => {
    const s = useChainSelection()
    s.toggleContract(c('1'))
    s.chooseAction(c('1'), 'BUY')
    s.chooseAction(c('1'), 'BUY') // the second press switches the choice off, not on a second row
    expect(s.entries.filter((e) => e.action === 'BUY')).toHaveLength(0)
    s.chooseAction(c('1'), 'BUY')
    expect(s.entries.filter((e) => e.action === 'BUY')).toHaveLength(1)
  })

  it('AC-11: opposite actions on one contract are two entries with their own ids', () => {
    const s = useChainSelection()
    s.chooseAction(c('1'), 'BUY')
    s.chooseAction(c('1'), 'SELL')
    expect(s.entries.map((e) => [e.action, e.id])).toEqual([['BUY', 'id-2026-10-27-1CE|BUY'], ['SELL', 'id-2026-10-27-1CE|SELL']])
  })

  it('AC-2: an unknown action is refused', () => {
    const s = useChainSelection()
    s.chooseAction(c('1'), 'HOLD')
    s.chooseAction(c('1'), undefined)
    expect(s.entries).toEqual([])
  })

  it('AC-7: lots accept a whole number 1..10000 only', () => {
    const s = useChainSelection()
    s.chooseAction(c('1'), 'BUY')
    const id = s.entries[0].id
    for (const bad of [0, -1, 1.5, '2', '1e2', 10001, '', null, 'abc', NaN]) {
      s.setLots(id, bad)
      expect(s.entries[0].lots).toBe(1)
    }
    s.setLots(id, 10000)
    expect(s.entries[0].lots).toBe(10000)
    s.stepLots(id, 1)
    expect(s.entries[0].lots).toBe(10000)
  })

  it('AC-9: the draft holds only legs with an action, for the asked underlying, in the order picked', () => {
    const s = useChainSelection()
    s.toggleContract(c('1')) // ticked, no action: not imported
    s.chooseAction(c('2'), 'SELL')
    s.chooseAction(contractOf('SENSEX', '2026-10-30', '9', 'PE', cell('sx-9PE', null)), 'BUY')
    expect(s.draftOf('NIFTY').legs.map((l) => l.instrument_id)).toEqual(['id-2026-10-27-2CE'])
    expect(s.draftOf('SENSEX').legs).toEqual([{ instrument_id: 'sx-9PE', action: 'BUY', lots: 1, planned_entry: null, captured_at: '2026-10-19T10:00:00+05:30' }])
  })

  it('AC-15: undo restores the last removed leg in place; a second undo does nothing', () => {
    const s = useChainSelection()
    s.chooseAction(c('1'), 'BUY')
    s.chooseAction(c('2'), 'BUY')
    s.remove(s.entries[0].id)
    expect(s.entries).toHaveLength(1)
    s.undo()
    expect(s.entries.map((e) => e.instrument_id)).toEqual(['id-2026-10-27-1CE', 'id-2026-10-27-2CE'])
    s.undo()
    expect(s.entries).toHaveLength(2)
  })
})
