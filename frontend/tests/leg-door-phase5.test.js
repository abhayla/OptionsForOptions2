// Phase 5 (PLAN 5.5, D-60, ADR-319 (1), ADR-328 (1)): one leg door per builder page. A step, Shift, Width or Hedge that lands a leg on a
// contract held on the OPPOSITE side asks first ("Keep both" / "Cancel"); a deliberate add (picker, form, edit) stays silent.
// Real page, real recorded condor (outcome-condor.json: SELL 22800 CE 44624, BUY 23000 CE 44632, SELL 22400 PE 44604, BUY 22200 PE 44595);
// Drafts Mode on the real strategy 63 book (tests/fixtures/paper/strategy-63-roll.json). Rows 1-4, 7 (page half), 9 (moves), 10 and
// 12 (page half) need the page wiring (5.5.4, Lane A's file until the hand-over): they run when the page names `useLegDoor`
// (tests/helpers/phase5Wired.js); the rest run on the door itself.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { WIRED } from './helpers/phase5Wired'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const { withPriceTexts } = await import('./_priceTexts.js')
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`]
    if (a === undefined && url.startsWith('/paper/strategies/')) return Promise.reject({ status: 404 })
    if (a === undefined && url === '/settings') return Promise.resolve({ data: settingsData() })
    if (a === undefined) return Promise.reject(new Error(`unmocked ${method} ${url}`))
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: withPriceTexts(a) })
  }
  return { ...actual, default: { get: (url) => respond('GET', url), post: (url, body) => respond('POST', url, body) } }
})
import { settingsData } from './helpers/servedLots'
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import LegPicker from '@/components/strategy/LegPicker.vue'
import { useLegDoor } from '@/composables/useLegDoor'
import { OPPOSITE_NOTE, OPPOSITE_QUESTION, admitLegs, lotsRangeText, oppositeContract, sameContract } from '@/lib/legDoor'
import { paperOrdersFor } from '@/lib/paperDrafts'
import real from './fixtures/outcome-condor.json'
import BOOK from '../../tests/fixtures/paper/strategy-63-roll.json'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const all = (w, id) => w.findAll(`[data-testid="${id}"]`)
const DRAFT = { underlying: 'NIFTY', legs: real.legs.map((l) => ({ instrument_id: l.instrument_id, action: l.action, lots: l.lots,
  planned_entry: l.planned_entry, captured_at: l.captured_at })) }
const replyLeg = (l, extra = {}) => ({ instrument_id: l.instrument_id, action: l.action, instrument: l.instrument, strike: l.strike,
  expiry: l.expiry, lots: l.lots, base_lots: l.lots, quantity: l.quantity, planned_entry: l.planned_entry, captured_at: l.captured_at,
  price_source: 'captured', included: true, hedge: false, block: null, ...extra })
const READ = { legs: real.legs.map((l) => replyLeg(l)), shape: 'iron_condor', shape_name: 'Short Iron Condor', outcome: real,
  controls: { shift: true, width: true, hedge: true }, shift_total: 0 }
const BUY_CE = real.legs[1] // 23000 CE, BUY, held; leg 0 (SELL 22800 CE) is the one that moves
const SELL_PE = real.legs[2] // 22400 PE, SELL, held
const landing = (onto, over = {}) => (body) => Promise.resolve({ data: {
  seq: body.seq, shape: null, shape_name: null, outcome: null, controls: { shift: true, width: true, hedge: true }, shift_total: 50,
  legs: body.legs.map((sent, i) => (i === 0
    ? replyLeg(real.legs[0], { instrument_id: onto.instrument_id, instrument: onto.instrument, strike: onto.strike, ...over })
    : replyLeg(real.legs[i], { instrument_id: sent.instrument_id }))),
} })
beforeEach(() => {
  calls.length = 0
  answers = {}
})
async function openPage(query = { draft: JSON.stringify(DRAFT) }) {
  answers['POST /strategies/outcome'] = real
  answers['POST /strategies/leg-edit'] = READ
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await router.push({ path: '/strategy/builder', query })
  await router.isReady()
  const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
  await flushPromises()
  return w
}
const ids = (w) => w.vm.$.setupState.legs.map((l) => l.instrument_id)
const sides = (w) => w.vm.$.setupState.legs.map((l) => `${l.action} ${l.instrument_id}`)
const BEFORE = real.legs.map((l) => l.instrument_id)
const NAME_CE = 'NIFTY 13 Oct 23000 CE'
const stepFirst = async (w, onto) => {
  answers['POST /strategies/leg-edit'] = landing(onto)
  await all(w, 'strike-plus')[0].trigger('click')
  await flushPromises()
}
const leEdits = () => calls.filter((c) => c.url === '/strategies/leg-edit').length

describe.runIf(WIRED.door)('Phase 5 row 1-4, 10: a move onto an opposite-held contract asks (ADR-328 (1))', () => {
  it('1 Core: a SELL stepped onto the held BUY of the contract asks, with exactly Keep both and Cancel; the legs are unchanged until answered', async () => {
    const w = await openPage()
    await stepFirst(w, BUY_CE)
    expect(t(w, 'dup-dialog').exists()).toBe(true)
    expect(t(w, 'dup-question').text()).toBe(OPPOSITE_QUESTION(NAME_CE, 'BUY'))
    expect(t(w, 'dup-question').text()).toBe('NIFTY 13 Oct 23000 CE is already in this strategy as a Buy.')
    expect(t(w, 'dup-note').text()).toBe(OPPOSITE_NOTE)
    expect(t(w, 'dup-separate').text()).toBe('Keep both')
    expect(t(w, 'dup-cancel').text()).toBe('Cancel')
    expect(t(w, 'dup-increase').exists()).toBe(false)
    expect(ids(w)).toEqual(BEFORE)
  })

  it('2 Keep both: two rows of the contract, a SELL and a BUY', async () => {
    const w = await openPage()
    await stepFirst(w, BUY_CE)
    await t(w, 'dup-separate').trigger('click')
    await flushPromises()
    expect(sides(w)).toEqual([`SELL ${BUY_CE.instrument_id}`, `BUY ${BUY_CE.instrument_id}`, `SELL ${SELL_PE.instrument_id}`, `BUY ${BEFORE[3]}`])
    expect(t(w, 'dup-dialog').exists()).toBe(false)
  })

  it('3 Cancel, Escape, x and the overlay each leave the legs as before and send no further leg-edit', async () => {
    for (const close of [
      (w) => t(w, 'dup-cancel').trigger('click'),
      (w) => t(w, 'modal-root').trigger('keydown', { key: 'Escape' }),
      (w) => t(w, 'modal-close').trigger('click'),
      (w) => t(w, 'modal-overlay').trigger('click'),
    ]) {
      const w = await openPage()
      await stepFirst(w, BUY_CE)
      const sent = leEdits()
      await close(w)
      await flushPromises()
      expect(ids(w)).toEqual(BEFORE)
      expect(sides(w)[0]).toBe(`SELL ${BEFORE[0]}`)
      expect(t(w, 'dup-dialog').exists()).toBe(false)
      expect(leEdits()).toBe(sent)
      w.unmount()
    }
  })

  it('4 Shift, Width and Hedge onto an opposite-held contract ask the same question', async () => {
    for (const control of ['shift', 'width', 'hedge']) {
      const w = await openPage()
      answers['POST /strategies/leg-edit'] = landing(BUY_CE)
      void w.vm.$.setupState.editLeg({ control, direction: 1 }) // not awaited: the edit waits for the answer
      await flushPromises()
      expect(t(w, 'dup-question').text(), control).toBe(OPPOSITE_QUESTION(NAME_CE, 'BUY'))
      expect(t(w, 'dup-increase').exists(), control).toBe(false)
      await t(w, 'dup-cancel').trigger('click')
      await flushPromises()
      expect(ids(w), control).toEqual(BEFORE)
      w.unmount()
    }
  })

  it('10 Escape on the page dialog for a same-action step is Cancel (no page dialog test before)', async () => {
    const w = await openPage()
    await stepFirst(w, SELL_PE)
    expect(t(w, 'dup-question').text()).toBe('NIFTY 13 Oct 22400 PE is already in this strategy.')
    await t(w, 'modal-root').trigger('keydown', { key: 'Escape' })
    await flushPromises()
    expect(ids(w)).toEqual(BEFORE)
    expect(t(w, 'dup-dialog').exists()).toBe(false)
  })
})

describe.runIf(WIRED.door)('Phase 5 Drafts Mode (rows 2, 3): the opposite step on the paper net position', () => {
  const never = () => new Promise(() => {})
  async function openDrafts() {
    answers = {
      'GET /paper/strategies/63': BOOK, 'GET /strategies': { strategies: [] }, 'POST /strategies/outcome': never,
      'GET /catalogue/NIFTY/contracts?expiry=2026-11-03': { underlying: 'NIFTY', contracts: BOOK.positions.map((p) => ({ contract_id: p.contract_id,
        exchange_segment: 'NSE_FO', exchange_token: p.contract_id, instrument_type: p.instrument, expiry: p.expiry, strike: p.strike, lot_size: 65, symbol: `N${p.strike}${p.instrument}` })) },
    }
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
    await router.push({ path: '/strategy/builder', query: { strategy: '63' } })
    await router.isReady()
    const w = mount(StrategyBuilderPage, { global: { plugins: [router], stubs: { PayoffChart: true } } })
    await flushPromises()
    return w
  }
  // leg 0 (BUY 5572) lands on the held SELL 5576: the reply names that contract for row 0 and keeps the others as sent
  const landOnLeg1 = (w) => {
    const legs = w.vm.$.setupState.legs
    answers['POST /strategies/leg-edit'] = (body) => Promise.resolve({ data: { seq: body.seq, shape: null, shape_name: null, outcome: null,
      controls: { shift: true, width: true, hedge: true }, shift_total: 0,
      legs: legs.map((l, i) => ({ ...replyLeg({ ...l, instrument: l.instrument_type, quantity: null }), base_lots: l.lots, contract_id: l.contract_id, lot_size: l.lot_size,
        ...(i === 0 ? { instrument_id: legs[1].instrument_id, strike: legs[1].strike, contract_id: legs[1].contract_id, lot_size: legs[1].lot_size } : {}) })) } })
  }
  it('2 Keep both: the diff still has the two exits (REQ-109 AC-9); 3 Cancel: pending changes unchanged', async () => {
    const w = await openDrafts()
    const pending = () => w.vm.$.setupState.pendingOrders.length
    expect(pending()).toBe(0)
    landOnLeg1(w)
    void w.vm.$.setupState.editLeg({ control: 'step', index: 0, direction: 1 }) // not awaited: the edit waits for the answer
    await flushPromises()
    expect(t(w, 'dup-question').text()).toContain('is already in this strategy as a Sell.')
    await t(w, 'dup-cancel').trigger('click')
    await flushPromises()
    expect(pending()).toBe(0)
    void w.vm.$.setupState.editLeg({ control: 'step', index: 0, direction: 1 }) // not awaited: the edit waits for the answer
    await flushPromises()
    await t(w, 'dup-separate').trigger('click')
    await flushPromises()
    const { legs, paper, pendingOrders } = w.vm.$.setupState
    expect(pendingOrders.map((o) => o.kind).sort()).toEqual(paperOrdersFor(paper.net, legs).map((o) => o.kind).sort())
    expect(pendingOrders.filter((o) => o.kind === 'exit')).toHaveLength(2)
  })
})

describe('Phase 5 rows 5, 6, 7, 8, 9, 13: the door itself', () => {
  const held = [{ id: 'a', instrument_id: 'NSE_FO:1', action: 'BUY', lots: 1 }, { id: 'b', instrument_id: 'NSE_FO:2', action: 'SELL', lots: 1 }]
  const q = (action, id = 'NSE_FO:1', lots = 1) => ({ id: 'x', instrument_id: id, action, lots })

  it('oppositeContract and sameContract are exclusive, and a leg with no instrument id matches nothing', () => {
    expect(oppositeContract(held[0], q('SELL'))).toBe(true)
    expect(oppositeContract(held[0], q('BUY'))).toBe(false)
    expect(sameContract(held[0], q('BUY'))).toBe(true)
    expect(oppositeContract({ action: 'BUY' }, { action: 'SELL' })).toBe(false)
    expect(oppositeContract({ instrument_id: null, action: 'BUY' }, { instrument_id: null, action: 'SELL' })).toBe(false)
  })

  it('5/6 a deliberate add or edit (opposite: allow, the default) of the other side asks nothing and adds a second row', async () => {
    const ask = vi.fn()
    const r = await admitLegs(held, [q('SELL')], { ask, maxLots: 10 })
    expect(ask).not.toHaveBeenCalled()
    expect(r).toEqual({ legs: held, kept: [q('SELL')] })
    const door = useLegDoor({ maxLots: () => 10 })
    expect(await door.admit(held, [q('SELL')], { skipId: 'a', opposite: 'allow' })).toEqual({ legs: held, kept: [q('SELL')] })
    expect(door.pending.value).toBeNull()
  })

  it('opposite: ask asks once (kind opposite) with the held leg; Keep both adds, Cancel and anything else is Cancel', async () => {
    const ask = vi.fn().mockResolvedValue('separate')
    expect(await admitLegs(held, [q('SELL')], { ask, maxLots: 10, opposite: 'ask' })).toEqual({ legs: held, kept: [q('SELL')] })
    expect(ask).toHaveBeenCalledWith(held[0], 'opposite')
    expect(await admitLegs(held, [q('SELL')], { ask: async () => 'cancel', maxLots: 10, opposite: 'ask' })).toBeNull()
    expect(await admitLegs(held, [q('SELL')], { ask: async () => 'increase', maxLots: 10, opposite: 'ask' })).toBeNull() // no Increase on this side
    expect(await admitLegs(held, [q('BUY', 'NSE_FO:9')], { ask, maxLots: 10, opposite: 'ask' })).toEqual({ legs: held, kept: [q('BUY', 'NSE_FO:9')] })
  })

  it('the same-action question comes first and a skipId leg is never its own clash', async () => {
    const ask = vi.fn().mockResolvedValue('separate')
    await admitLegs(held, [q('BUY')], { ask, maxLots: 10, opposite: 'ask' })
    expect(ask).toHaveBeenCalledWith(held[0], 'same')
    const none = vi.fn()
    await admitLegs(held, [q('SELL')], { ask: none, maxLots: 10, opposite: 'ask', skipId: 'a' })
    expect(none).not.toHaveBeenCalled()
  })

  it('7 one live question: a second ask settles the first as cancel; cancel is idempotent', async () => {
    const door = useLegDoor({ maxLots: () => 10 })
    const first = door.ask(held[0], 'same')
    expect(door.pending.value).toMatchObject({ kind: 'same', heldAction: 'BUY' })
    const second = door.ask(held[1], 'opposite')
    expect(await first).toBe('cancel')
    expect(door.pending.value).toMatchObject({ kind: 'opposite', heldAction: 'SELL' })
    door.cancel()
    door.cancel()
    expect(await second).toBe('cancel')
    expect(door.pending.value).toBeNull()
    door.answer('increase') // nothing open: nothing happens
    expect(door.pending.value).toBeNull()
  })

  it('9 same-action: Increase raises lots and base_lots; past the maximum the lots sentence and nothing changed', async () => {
    const door = useLegDoor({ maxLots: () => 5 })
    const p = door.admit([{ ...held[0], lots: 2, base_lots: 2 }], [q('BUY', 'NSE_FO:1', 2)])
    expect(door.pending.value.kind).toBe('same')
    door.answer('increase')
    expect((await p).legs[0]).toMatchObject({ lots: 4, base_lots: 4 })
    const over = door.admit([{ ...held[0], lots: 4 }], [q('BUY', 'NSE_FO:1', 4)])
    door.answer('increase')
    expect(await over).toEqual({ error: lotsRangeText(5) })
  })

  it('13 a moved leg with no instrument_id never asks (absent)', async () => {
    const door = useLegDoor({ maxLots: () => 10 })
    const base = [{ id: 'a', instrument_id: 'NSE_FO:1', action: 'BUY', lots: 1 }, { id: 'b', instrument_id: 'NSE_FO:2', action: 'SELL', lots: 1 }]
    const landed = [{ id: 'a', instrument_id: undefined, action: 'BUY', lots: 1 }, base[1]]
    expect(await door.admitMoved(base, landed)).toEqual({ legs: landed, increased: false })
    expect(door.pending.value).toBeNull()
  })

  it('admitMoved: only a moved leg is asked, against the unmoved legs; Increase folds the row away; Cancel returns null', async () => {
    const door = useLegDoor({ maxLots: () => 10 })
    const base = [{ id: 'a', instrument_id: 'NSE_FO:1', action: 'BUY', lots: 1 }, { id: 'b', instrument_id: 'NSE_FO:2', action: 'SELL', lots: 1 }]
    const landed = [{ ...base[0], instrument_id: 'NSE_FO:2', action: 'SELL' }, base[1]]
    const p = door.admitMoved(base, landed)
    expect(door.pending.value.kind).toBe('same')
    door.answer('increase')
    expect(await p).toMatchObject({ legs: [{ id: 'b', lots: 2 }], increased: true })
    const opp = door.admitMoved(base, [{ ...base[0], instrument_id: 'NSE_FO:2' }, base[1]])
    expect(door.pending.value.kind).toBe('opposite')
    door.cancel()
    expect(await opp).toBeNull()
  })

  it('8 picker stale legs: an answer given after the page legs changed is Cancel and changes nothing', async () => {
    const door = useLegDoor({ maxLots: () => 10 })
    const legs = [{ id: 'a', instrument_id: 'NSE_FO:44624', action: 'SELL', lots: 1, underlying: 'NIFTY' }]
    const w = mount(LegPicker, { props: { legs, maxLots: 10, lotChoiceCount: 10 }, global: { provide: { legDoor: door } } })
    await flushPromises()
    const p = w.vm.$.setupState.admitHere([{ instrument_id: 'NSE_FO:44624', action: 'SELL', lots: 1 }])
    await flushPromises()
    expect(door.pending.value).not.toBeNull()
    await w.setProps({ legs: [{ id: 'z', instrument_id: 'NSE_FO:44632', action: 'BUY', lots: 3, underlying: 'NIFTY' }] })
    door.answer('increase')
    expect(await p).toBeNull()
    expect(w.emitted('update:legs')).toBeUndefined()
    w.unmount()
  })

  it('an equal-content refresh of the legs keeps the answer (Increase still applies)', async () => {
    const door = useLegDoor({ maxLots: () => 10 })
    const legs = [{ id: 'a', instrument_id: 'NSE_FO:44624', action: 'SELL', lots: 1, underlying: 'NIFTY' }]
    const w = mount(LegPicker, { props: { legs, maxLots: 10, lotChoiceCount: 10 }, global: { provide: { legDoor: door } } })
    await flushPromises()
    const p = w.vm.$.setupState.admitHere([{ instrument_id: 'NSE_FO:44624', action: 'SELL', lots: 1 }])
    await flushPromises()
    await w.setProps({ legs: legs.map((l) => ({ ...l, symbol: 'NIFTY26O1322800CE' })) })
    door.answer('increase')
    expect((await p).legs[0].lots).toBe(2)
    w.unmount()
  })

  it('a picker mounted alone makes and renders its own dialog; with a provided door it renders none', async () => {
    const own = mount(LegPicker, { props: { legs: [], maxLots: 10, lotChoiceCount: 10 } })
    expect(own.findComponent({ name: 'DuplicateLegDialog' }).exists()).toBe(true)
    const door = useLegDoor()
    const fed = mount(LegPicker, { props: { legs: [], maxLots: 10, lotChoiceCount: 10 }, global: { provide: { legDoor: door } } })
    expect(fed.findComponent({ name: 'DuplicateLegDialog' }).exists()).toBe(false)
    own.unmount()
    fed.unmount()
  })
})

describe('Phase 5 row 11, 12: what is not a door user, and the old title is gone', () => {
  it('11 a ?draft= with two same-action rows of one contract opens as two rows, no question', async () => {
    const dupDraft = { underlying: 'NIFTY', legs: [DRAFT.legs[0], DRAFT.legs[0]] }
    const w = await openPage({ draft: JSON.stringify(dupDraft) })
    expect(w.findAll('[data-testid="leg-row"]')).toHaveLength(2)
    expect(t(w, 'dup-dialog').exists()).toBe(false)
  })
  const src = (p) => readFileSync(resolve(__dirname, '../src', p), 'utf8')
  it('12 LegPicker.vue has no title="Already in this strategy" of its own (the dialog component has the one)', () => {
    expect(src('components/strategy/LegPicker.vue')).not.toContain('title="Already in this strategy"')
    expect(src('components/strategy/DuplicateLegDialog.vue')).toContain('title="Already in this strategy"')
  })
  it.runIf(WIRED.door)('12 StrategyBuilderPage.vue no longer carries the dialog (the one door and one dialog)', () => {
    expect(src('pages/StrategyBuilderPage.vue')).not.toContain('title="Already in this strategy"')
    expect(src('pages/StrategyBuilderPage.vue')).toContain('DuplicateLegDialog')
  })
  it.runIf(WIRED.door)('7 page half: with the picker drawer mounted there is at most one dup-dialog while a question is open', async () => {
    const w = await openPage()
    await stepFirst(w, SELL_PE)
    expect(all(w, 'dup-dialog')).toHaveLength(1)
  })
})

afterEach(() => vi.useRealTimers())
