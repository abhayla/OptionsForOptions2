// GC-ADJ1 step 3 (REQ-156 AC-1..AC-5, REQ-157 AC-1..AC-5): the adjust compare mounted on the REAL route replies, captured
// from the dev server (POST /api/strategies/{id}/adjustment-approaches, OFO_SCENARIO=ADJ-02 strategy 72 and ADJ-13 strategy 73;
// tests/fixtures/adjust-approaches-adj02.json / -adj13.json). Every expected string is read from the fixture; the browser
// computes nothing. The ids are the server's own (No change = A-36).
import { describe, it, expect, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import adj02 from './fixtures/adjust-approaches-adj02.json'
import adj13 from './fixtures/adjust-approaches-adj13.json'

const drawn = vi.hoisted(() => [])
vi.mock('chart.js/auto', () => ({ default: class { constructor(_ctx, config) { drawn.push(config) } destroy() {} } }))
import AdjustCompare from '@/components/strategy/AdjustCompare.vue'
import { cmpDecimal, NO_CHANGE_ID, spanOf } from '@/lib/adjustCompare'
import { istTime } from '@/lib/displayFormat'

const ORDER = adj02.approaches.map((a) => a.id) // the server's order, No change first
const OTHERS = ORDER.filter((id) => id !== NO_CHANGE_ID)
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const all = (w, id) => w.findAll(`[data-testid="${id}"]`)
const clone = (x) => JSON.parse(JSON.stringify(x))
const contractsFor = (approach) => approach.after_legs.map((l, i) => ({
  contract_id: 100 + i, symbol: l.tradingsymbol, expiry: l.expiry, instrument_type: l.type, strike: l.strike, lot_size: 65, exchange_segment: 'NFO', exchange_token: 900 + i,
}))
const client = (reply, { tracking } = {}) => ({
  post: vi.fn(async () => ({ data: reply })),
  get: vi.fn(async (url) => {
    if (url.startsWith('/catalogue')) return { data: { contracts: reply.approaches.flatMap(contractsFor) } }
    if (url.endsWith('/tracking')) {
      if (tracking) return { data: tracking }
      throw Object.assign(new Error('x'), { status: 404 })
    }
    return { data: { name: '"NIFTY Oct condor"', definition: { underlying: 'NIFTY' } } }
  }),
})
async function show(reply, props = {}, opts = {}) {
  const c = client(reply, opts)
  const w = mount(AdjustCompare, { attachTo: document.body, props: { strategyId: 72, client: c, ...props } })
  await flushPromises()
  return { w, c }
}
const lastLines = () => drawn[drawn.length - 1].data.datasets.map((d) => d.id)
const colIds = (w) => w.findAll('thead th[data-testid^="adjust-col-"]').map((x) => x.attributes('data-testid').replace('adjust-col-', ''))

describe('REQ-156 compare display on the real reply', () => {
  it('AC-1: asks the route once; every column id is the server\'s approach id, No change (A-36) first, even when the reply lists it later', async () => {
    const r = clone(adj02)
    r.approaches = [...r.approaches.slice(1, 3), r.approaches[0], ...r.approaches.slice(3)]
    const { w, c } = await show(r)
    expect(c.post).toHaveBeenCalledTimes(1)
    expect(c.post.mock.calls[0][0]).toBe('/strategies/72/adjustment-approaches')
    expect(all(w, 'adjust-table').length).toBe(1)
    expect(NO_CHANGE_ID).toBe('A-36')
    expect(colIds(w)).toEqual(['A-36', ...r.approaches.map((a) => a.id).filter((id) => id !== 'A-36')])
    expect(t(w, 'adjust-title').text()).toBe('Compare possible approaches: NIFTY Oct condor')
  })

  it('AC-1: a refused approach (the server\'s error parts) is listed with its reason, and is in no column, chart line or picker', async () => {
    const { w } = await show(adj13)
    for (const a of adj13.approaches.filter((x) => x.refusal)) {
      expect(t(w, `adjust-refused-${a.id}`).text()).toContain(a.refusal.what_happened)
      expect(t(w, `adjust-col-${a.id}`).exists()).toBe(false)
      expect(lastLines()).not.toContain(a.id)
    }
    expect(colIds(w)).toEqual(['A-36'])
    expect(t(w, 'adjust-showing').text()).toBe('Showing 1 of 1 approaches')
    expect(t(w, 'adjust-pick-empty').exists()).toBe(true)
  })

  it('AC-2 / AC-3: every criterion row shows the server values and leader cells with the leader label; unavailable shows "-" and the reason', async () => {
    const r = clone(adj02)
    r.criteria[11].values['A-05'] = { text: null, value: null, unavailable_reason: 'Probability of profit is switched off.' } // pop row
    const { w } = await show(r)
    for (const c of r.criteria) {
      expect(t(w, `adjust-row-${c.id}`).exists()).toBe(true)
      for (const id of ORDER) {
        const cell = t(w, `adjust-cell-${c.id}-${id}`)
        const v = c.values[id]
        if (v.unavailable_reason || v.text == null) {
          expect(cell.text()).toContain('-')
          if (v.unavailable_reason) expect(cell.text()).toContain(v.unavailable_reason)
          expect(cell.attributes('data-leader')).toBe('false')
        } else {
          expect(cell.text()).toContain(v.text)
          expect(cell.attributes('data-leader')).toBe(c.leaders.includes(id) ? 'true' : 'false')
          if (c.leaders.includes(id)) expect(cell.text()).toContain(c.leader_label)
        }
      }
    }
    expect(t(w, 'adjust-group-money_now').text()).toBe('Money now')
    expect(t(w, 'adjust-group-summary').text()).toBe('Summary')
  })

  it('AC-3: a tie names every leader (both cells marked)', async () => {
    const r = clone(adj02)
    r.criteria[0].leaders = ['A-01', 'A-11']
    const { w } = await show(r)
    expect(ORDER.filter((id) => t(w, `adjust-cell-credit-${id}`).attributes('data-leader') === 'true')).toEqual(['A-01', 'A-11'])
  })

  it('AC-4: "Leads on N of M" equals the server leads for each column; the first column stays No change (no sort by N)', async () => {
    const { w } = await show(adj02)
    for (const id of ORDER) expect(t(w, `adjust-leads-${id}`).text()).toBe(`${adj02.leads[id].n} of ${adj02.leads[id].m}`)
    expect(colIds(w)[0]).toBe('A-36')
  })

  it('AC-4: no "best", "better", "winner", "rank", "score" or "recommend" anywhere in the rendered compare (ADR-003)', async () => {
    for (const r of [adj02, adj13]) {
      const { w } = await show(r, { picked: ['A-36', 'A-01'] })
      expect(w.text().toLowerCase()).not.toMatch(/\b(best|better|winner|rank|ranking|score|recommend\w*)\b/)
      w.unmount()
    }
  })

  it('AC-5: the Before is a dashed line, each approach its own line with the reply\'s own texts; hiding one removes only its line', async () => {
    const { w } = await show(adj02)
    const sets = drawn[drawn.length - 1].data.datasets
    expect(sets.map((d) => d.id)).toEqual(['before', ...ORDER])
    expect(sets[0].borderDash.length).toBeGreaterThan(0)
    expect(sets[1].borderDash.length).toBe(0)
    const [x, y] = adj02.curves['A-36'][0]
    expect(sets[1].data[0]).toEqual({ x, y })
    await t(w, 'adjust-legend-A-01').trigger('click')
    expect(lastLines()).toEqual(['before', ...ORDER.filter((id) => id !== 'A-01')])
    expect(all(w, 'adjust-col-A-01').length).toBe(1) // the table keeps its column
    await t(w, 'adjust-legend-A-01').trigger('click')
    expect(lastLines()).toContain('A-01')
  })

  it('ADJ-13: the booked P&L rides in the whole-trade figures the reply sent (nothing recomputed)', async () => {
    const built = adj13.approaches.find((a) => a.id === 'A-36')
    expect(built.after.booked_pnl).toBe(adj13.approaches[0].after.booked_pnl)
    const { w } = await show(adj13)
    expect(t(w, 'adjust-intro').text()).toContain('including P&L already booked')
    expect(t(w, 'adjust-cell-max_loss-A-36').text()).toContain(adj13.criteria.find((c) => c.id === 'max_loss').values['A-36'].text)
  })

  it('a spot from the feed shows its source and time as the reply sent them', async () => {
    const { w } = await show(adj02)
    expect(t(w, 'adjust-spot').text()).toBe(`Spot ${adj02.spot.value} · ${adj02.spot.source_text} · ${istTime(adj02.spot.at)}`)
  })

  it('390 px: the table scrolls in its own container; the page never needs a horizontal scroll', async () => {
    const { w } = await show(adj02)
    expect(t(w, 'adjust-table-scroll').classes()).toContain('overflow-x-auto')
    expect(w.find('section').classes()).toContain('min-w-0')
  })
})

describe('REQ-157 filters on the real reply', () => {
  const lossOf = (a) => (a.after.after_charges ?? a.after.gross).max_loss
  it('AC-1 / AC-2: the chips list only kinds and sides present; each range spans the values\' own min and max', async () => {
    const { w } = await show(adj02)
    const kinds = [...new Set(OTHERS.map((id) => adj02.approaches.find((a) => a.id === id).kind))]
    expect(w.findAll('[data-testid^="adjust-kind-"]').map((x) => x.attributes('data-testid')).sort()).toEqual(kinds.map((k) => `adjust-kind-${k}`).sort())
    expect(t(w, 'adjust-kind-roll').text()).toBe('Roll (2)')
    expect(t(w, 'adjust-kind-close_part').text()).toBe('Close part (1)')
    expect(w.findAll('[data-testid^="adjust-side-"]').length).toBe(3)
    const span = spanOf(OTHERS.map((id) => lossOf(adj02.approaches.find((a) => a.id === id))).filter((v) => v !== 'UNLIMITED'))
    expect(t(w, 'adjust-range-max_loss-min').text()).toBe(span.min)
    expect(t(w, 'adjust-range-max_loss-max').text()).toBe(span.max)
    const pops = spanOf(OTHERS.map((id) => adj02.approaches.find((a) => a.id === id).pop.value))
    expect(t(w, 'adjust-range-pop-min').text()).toBe(pops.min)
    expect(t(w, 'adjust-range-pop-max').text()).toBe(pops.max)
  })

  it('AC-3 / AC-5: filters hiding every other approach read "Showing 1 of 7"; No change stays in chart and table; the picker is empty and says why', async () => {
    const { w } = await show(adj02)
    expect(t(w, 'adjust-showing').text()).toBe('Showing 7 of 7 approaches')
    await t(w, 'adjust-kind-exit').trigger('click')
    await t(w, 'adjust-side-call').trigger('click') // exit is "both": no approach is both
    expect(t(w, 'adjust-showing').text()).toBe('Showing 1 of 7 approaches')
    expect(colIds(w)).toEqual(['A-36'])
    expect(lastLines()).toEqual(['before', 'A-36'])
    expect(w.findAll('[data-testid="adjust-pick"] option').length).toBe(0)
    expect(t(w, 'adjust-open').attributes('disabled')).toBeDefined()
    expect(t(w, 'adjust-pick-empty').text()).toContain('only "No change"')
    await t(w, 'adjust-clear').trigger('click')
    expect(t(w, 'adjust-showing').text()).toBe('Showing 7 of 7 approaches')
  })

  it('AC-5: chart, table and picker all follow the filters', async () => {
    const { w } = await show(adj02)
    await t(w, 'adjust-kind-roll').trigger('click')
    expect(t(w, 'adjust-showing').text()).toBe('Showing 3 of 7 approaches')
    expect(lastLines()).toEqual(['before', 'A-36', 'A-01', 'A-05'])
    expect(w.findAll('[data-testid="adjust-pick"] option').map((o) => o.element.value)).toEqual(['A-01', 'A-05'])
  })

  it('AC-4: an approach with no value for an active filter stays, marked "not available for this filter"', async () => {
    const r = clone(adj02)
    r.approaches.find((a) => a.id === 'A-29').pop = { value: null, not_available: true, reason: 'x' }
    const { w } = await show(r)
    const input = t(w, 'adjust-range-pop-input')
    input.element.value = '0.45'
    await input.trigger('input')
    expect(t(w, 'adjust-col-A-29').exists()).toBe(true)
    expect(t(w, 'adjust-unavailable-A-29').text()).toBe('not available for this filter')
    expect(t(w, 'adjust-unavailable-A-01').exists()).toBe(false)
  })
})

describe('GC-ADJ1 step 3: picks from the drawer and the hand-off', () => {
  const PICKS = ['A-36', 'A-01', 'A-05', 'A-11', 'A-31'] // two of the seven unticked in the drawer: A-29, A-28

  it('the scope select defaults to the picked ones: No change + the picks only; "All 7 that apply" brings the rest back', async () => {
    const { w } = await show(adj02, { picked: PICKS })
    expect(colIds(w)).toEqual(PICKS)
    expect(t(w, 'adjust-showing').text()).toBe('Showing 5 of 5 approaches')
    expect(w.findAll('[data-testid="adjust-scope-select"] option').map((o) => o.text())).toEqual(['All 7 that apply', 'Only the ones picked in the drawer'])
    await t(w, 'adjust-scope-select').setValue('all')
    expect(colIds(w)).toEqual(ORDER)
  })

  it('attack 2: only No change picked still opens the compare, "Showing 1 of 1"', async () => {
    const { w } = await show(adj02, { picked: ['A-36'] })
    expect(colIds(w)).toEqual(['A-36'])
    expect(t(w, 'adjust-showing').text()).toBe('Showing 1 of 1 approaches')
  })

  it('attack 4: a refused approach the user picked is listed with its reason; a refused one nobody picked is not mentioned', async () => {
    const { w } = await show(adj13, { picked: ['A-36', 'A-01'] })
    expect(t(w, 'adjust-refused-A-01').text()).toContain(adj13.approaches.find((a) => a.id === 'A-01').refusal.what_happened)
    expect(t(w, 'adjust-refused-A-05').exists()).toBe(false)
  })

  it('the "Why detected · current state" card shows the same layers as the drawer, "-" where the card has no figure', async () => {
    const tracking = {
      strategy_id: 72, state: 'LIVE', paper_pnl_text: '+195.00', booked_text: '+0.00', unbooked_text: '+195.00', as_of: null, legs: [],
      index: { level: '23420.00' }, breakevens: ['22655.95', '23544.05'],
      detections: [{ kind: 'platform_detection', condition: 'near_short_strike', level: '23500.00', index_level: '23420.00', distance_points: '80.00', distance_percent: '0.34', threshold_percent: '0.6', at: '2026-11-06T11:39:59+05:30', price_health: 'live' }],
    }
    const { w } = await show(adj02, { picked: PICKS }, { tracking })
    expect(t(w, 'adjust-why-line').text()).toBe('Adjustment opportunity detected: Index is near a short strike: 23500, 80.00 points (0.34%) away')
    expect(t(w, 'adjust-why-pnl').text()).toBe('+195.00')
    expect(t(w, 'adjust-why-breakevens').text()).toBe('22655.95, 23544.05')
    expect(t(w, 'adjust-why-delta').text()).toBe('-')
  })

  it('the button hands the chosen approach\'s After legs on as builder legs; no order is placed (one POST only: the compare read)', async () => {
    const { w, c } = await show(adj02)
    await t(w, 'adjust-pick').setValue('A-01')
    await t(w, 'adjust-open').trigger('click')
    await flushPromises()
    const [ev] = w.emitted('prepare')
    const a = adj02.approaches.find((x) => x.id === 'A-01')
    expect(ev[0].underlying).toBe('NIFTY')
    expect(ev[0].legs.length).toBe(a.after_legs.length)
    expect(ev[0].legs[0]).toMatchObject({ action: a.after_legs[0].side, lots: a.after_legs[0].lots, planned_entry: a.after_legs[0].entry, symbol: a.after_legs[0].tradingsymbol })
    expect(c.post).toHaveBeenCalledTimes(1)
  })
})

describe('cmpDecimal (string comparison, no arithmetic)', () => {
  it('orders signs, lengths and fractions exactly', () => {
    expect(cmpDecimal('9', '10')).toBe(-1)
    expect(cmpDecimal('-9', '-10')).toBe(1)
    expect(cmpDecimal('0.50', '0.5')).toBe(0)
    expect(cmpDecimal('1,000.10', '1000.1')).toBe(0)
    expect(cmpDecimal('-0.0', '0')).toBe(0)
    expect(cmpDecimal('UNLIMITED', '1')).toBeNull()
  })
})
