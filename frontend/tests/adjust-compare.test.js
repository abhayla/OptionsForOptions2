// GC-ADJ1 step 3 (REQ-156 AC-1..AC-5, REQ-157 AC-1..AC-5): the adjust compare mounted on route replies built from the reply
// model (tests/_adjustFixtures.js; not recorded from the route, which does not send criteria/leads/curves yet).
// Every expected string is read from the fixture; the browser computes nothing.
import { describe, it, expect, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { replyFor } from './_adjustFixtures.js'

const drawn = vi.hoisted(() => [])
vi.mock('chart.js/auto', () => ({ default: class { constructor(_ctx, config) { drawn.push(config) } destroy() {} } }))
import AdjustCompare from '@/components/strategy/AdjustCompare.vue'
import { cmpDecimal, spanOf } from '@/lib/adjustCompare'

const ORDER = ['no_change', 'roll_up', 'roll_down', 'reduce_calls', 'convert_butterfly', 'recentre', 'exit']
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const all = (w, id) => w.findAll(`[data-testid="${id}"]`)
const client = (reply) => ({
  post: vi.fn(async () => ({ data: reply })),
  get: vi.fn(async (url) => (url.startsWith('/catalogue')
    ? { data: { contracts: [{ contract_id: 1, symbol: 'NIFTY26NOV24000CE', expiry: '2026-11-27', instrument_type: 'CE', strike: '24000.00', lot_size: 75, exchange_segment: 'NFO', exchange_token: 9 }] } }
    : { data: { name: '"NIFTY Oct condor"', definition: { underlying: 'NIFTY' } } })),
})
async function show(reply) {
  const c = client(reply)
  const w = mount(AdjustCompare, { attachTo: document.body, props: { strategyId: 7, client: c } })
  await flushPromises()
  return { w, c }
}
const lastLines = () => drawn[drawn.length - 1].data.datasets.map((d) => d.id)

describe('REQ-156 compare display', () => {
  it('AC-1: asks the route once; 7 columns, No change first then reply order, even when the reply lists it later; refused listed apart', async () => {
    const order = ['roll_up', 'no_change', 'roll_down', 'reduce_calls', 'convert_butterfly', 'recentre', 'exit']
    const { w, c } = await show(replyFor({ order }))
    expect(c.post).toHaveBeenCalledTimes(1)
    expect(c.post.mock.calls[0][0]).toBe('/strategies/7/adjustment-approaches')
    expect(all(w, 'adjust-table').length).toBe(1)
    const cols = w.findAll('thead th[data-testid^="adjust-col-"]').map((x) => x.attributes('data-testid').replace('adjust-col-', ''))
    expect(cols).toEqual(['no_change', 'roll_up', 'roll_down', 'reduce_calls', 'convert_butterfly', 'recentre', 'exit'])
    expect(t(w, 'adjust-title').text()).toBe('Compare possible approaches: NIFTY Oct condor')
  })

  it('AC-1: a refused approach is listed with its reason, and is in no column, chart line or picker', async () => {
    const { w } = await show(replyFor({ refused: ['recentre'] }))
    expect(t(w, 'adjust-refused-recentre').text()).toContain('The strikes it needs have no quote right now.')
    expect(t(w, 'adjust-col-recentre').exists()).toBe(false)
    expect(lastLines()).not.toContain('recentre')
    expect(all(w, 'adjust-pick').length).toBe(1)
    expect(w.findAll('[data-testid="adjust-pick"] option').map((o) => o.element.value)).not.toContain('recentre')
    expect(t(w, 'adjust-showing').text()).toBe('Showing 6 of 6 approaches')
  })

  it('AC-2 / AC-3: every criterion row shows the server values and leader cells with the leader label; unavailable shows "-" and the reason', async () => {
    const r = replyFor({ scenario: 'ADJ-20c', unpriced: ['reduce_calls'] })
    const { w } = await show(r)
    for (const c of r.criteria) {
      expect(t(w, `adjust-row-${c.id}`).exists()).toBe(true)
      for (const id of ORDER) {
        const cell = t(w, `adjust-cell-${c.id}-${id}`)
        const v = c.values[id]
        if (v.unavailable_reason) {
          expect(cell.text()).toContain('-')
          expect(cell.text()).toContain(v.unavailable_reason)
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
    const { w } = await show(replyFor())
    const marked = ORDER.filter((id) => t(w, `adjust-cell-credit_debit-${id}`).attributes('data-leader') === 'true')
    expect(marked).toEqual(['roll_up', 'roll_down'])
  })

  it('AC-4: "Leads on N of M" equals the server leads for each column; no sort by N; no overall winner wording', async () => {
    const r = replyFor({ pop: true })
    const { w } = await show(r)
    for (const id of ORDER) expect(t(w, `adjust-leads-${id}`).text()).toBe(`${r.leads[id].n} of ${r.leads[id].m}`)
    expect(w.findAll('thead th[data-testid^="adjust-col-"]').map((x) => x.attributes('data-testid'))[0]).toBe('adjust-col-no_change')
  })

  it('AC-4: no "best", "better", "winner", "rank", "score" or "recommend" anywhere in the rendered compare (ADR-003)', async () => {
    for (const r of [replyFor(), replyFor({ pop: true }), replyFor({ refused: ['exit'] })]) {
      const { w } = await show(r)
      expect(w.text().toLowerCase()).not.toMatch(/\b(best|better|winner|rank|ranking|score|recommend\w*)\b/)
      w.unmount()
    }
  })

  it('AC-5: the Before is a dashed line, each approach its own line; hiding one in the legend removes only its line', async () => {
    const { w } = await show(replyFor())
    const sets = drawn[drawn.length - 1].data.datasets
    expect(sets.map((d) => d.id)).toEqual(['before', ...ORDER])
    expect(sets[0].borderDash.length).toBeGreaterThan(0)
    expect(sets[1].borderDash.length).toBe(0)
    expect(sets[1].data[0]).toEqual({ x: '22000', y: '-3000' }) // the reply's own texts
    await t(w, 'adjust-legend-roll_up').trigger('click')
    expect(lastLines()).toEqual(['before', 'no_change', 'roll_down', 'reduce_calls', 'convert_butterfly', 'recentre', 'exit'])
    expect(all(w, 'adjust-col-roll_up').length).toBe(1) // the table keeps its column
    await t(w, 'adjust-legend-roll_up').trigger('click')
    expect(lastLines()).toContain('roll_up')
  })

  it('ADJ-13: booked P&L rides in the whole-trade figures the reply sent (nothing recomputed)', async () => {
    const r = replyFor({ scenario: 'ADJ-13', booked: '1250.00' })
    expect(r.approaches[1].after.booked_pnl).toBe('1250.00')
    const { w } = await show(r)
    expect(t(w, 'adjust-intro').text()).toContain('including P&L already booked')
    expect(t(w, 'adjust-cell-max_loss-roll_up').text()).toContain(r.criteria[2].values.roll_up.text)
  })

  it('attack 4: a spot from the last close shows its source and date, not "live"', async () => {
    const { w } = await show(replyFor())
    expect(t(w, 'adjust-spot').text()).toBe('Spot 23512.40 · Last close · 29 Oct 2026, 15:30:00 IST')
    expect(t(w, 'adjust-spot').text().toLowerCase()).not.toContain('live')
  })

  it('attack 5 (390 px): the table scrolls in its own container; the page never needs a horizontal scroll', async () => {
    const { w } = await show(replyFor())
    expect(t(w, 'adjust-table-scroll').classes()).toContain('overflow-x-auto')
    expect(t(w, 'adjust-table-scroll').classes()).toContain('min-w-0')
    expect(w.find('section').classes()).toContain('min-w-0')
  })
})

describe('REQ-157 filters', () => {
  it('AC-1 / AC-2: the chips list only kinds and sides present; each range spans the values\' own min and max', async () => {
    const r = replyFor({ pop: true })
    const { w } = await show(r)
    expect(w.findAll('[data-testid^="adjust-kind-"]').map((x) => x.attributes('data-testid'))).toEqual(['adjust-kind-roll', 'adjust-kind-reduce', 'adjust-kind-convert', 'adjust-kind-recentre', 'adjust-kind-exit'])
    expect(t(w, 'adjust-kind-roll').text()).toBe('Roll (2)')
    expect(w.findAll('[data-testid^="adjust-side-"]').map((x) => x.attributes('data-testid'))).toEqual(['adjust-side-call', 'adjust-side-put', 'adjust-side-both'])
    // max loss: finite values among the filtered approaches (No change is never filtered; UNLIMITED has no number)
    const losses = r.criteria[2].values
    const finite = ['no_change', 'roll_up', 'roll_down', 'reduce_calls', 'convert_butterfly', 'exit'].slice(1).map((id) => losses[id].value)
    const span = spanOf(finite)
    expect(t(w, 'adjust-range-max_loss-min').text()).toBe(span.min)
    expect(t(w, 'adjust-range-max_loss-max').text()).toBe(span.max)
    expect(t(w, 'adjust-range-max_loss-input').attributes('min')).toBe(span.min)
    expect(t(w, 'adjust-range-max_loss-input').attributes('max')).toBe(span.max)
    const pops = spanOf(['roll_up', 'roll_down', 'reduce_calls', 'convert_butterfly', 'recentre', 'exit'].map((id) => r.approaches.find((a) => a.id === id).pop.value))
    expect(t(w, 'adjust-range-pop-min').text()).toBe(pops.min)
    expect(t(w, 'adjust-range-pop-max').text()).toBe(pops.max)
    expect(t(w, 'adjust-risk-capped').text()).toBe('Loss capped (5)')
    expect(t(w, 'adjust-risk-uncapped').text()).toBe('Loss not capped (1)')
  })

  it('AC-2: with only a roll and an exit present, the kind filter offers those two alone; a recompute drops a stale choice', async () => {
    const r = replyFor({ order: ['no_change', 'roll_up', 'exit'] })
    const { w } = await show(r)
    expect(w.findAll('[data-testid^="adjust-kind-"]').map((x) => x.attributes('data-testid'))).toEqual(['adjust-kind-roll', 'adjust-kind-exit'])
  })

  it('AC-3 / AC-5 / attack 1: filters hiding every other approach read "Showing 1 of 7"; No change stays in chart and table; the picker is empty and the button says why', async () => {
    const { w } = await show(replyFor({ pop: true }))
    expect(t(w, 'adjust-showing').text()).toBe('Showing 7 of 7 approaches')
    await t(w, 'adjust-kind-exit').trigger('click')
    await t(w, 'adjust-risk-uncapped').trigger('click') // exit is capped: no approach has both
    expect(t(w, 'adjust-showing').text()).toBe('Showing 1 of 7 approaches')
    expect(w.findAll('thead th[data-testid^="adjust-col-"]').map((x) => x.attributes('data-testid'))).toEqual(['adjust-col-no_change'])
    expect(lastLines()).toEqual(['before', 'no_change'])
    expect(w.findAll('[data-testid="adjust-pick"] option').length).toBe(0)
    expect(t(w, 'adjust-pick').attributes('disabled')).toBeDefined()
    expect(t(w, 'adjust-open').attributes('disabled')).toBeDefined()
    expect(t(w, 'adjust-pick-empty').text()).toContain('only "No change"')
    await t(w, 'adjust-clear').trigger('click')
    expect(t(w, 'adjust-showing').text()).toBe('Showing 7 of 7 approaches')
  })

  it('AC-5: chart, table and picker all follow the filters; a range limit keeps only values inside it', async () => {
    const { w } = await show(replyFor({ pop: true }))
    await t(w, 'adjust-kind-roll').trigger('click')
    expect(t(w, 'adjust-showing').text()).toBe('Showing 3 of 7 approaches')
    expect(lastLines()).toEqual(['before', 'no_change', 'roll_up', 'roll_down'])
    expect(w.findAll('[data-testid="adjust-pick"] option').map((o) => o.element.value)).toEqual(['roll_up', 'roll_down'])
    await t(w, 'adjust-clear').trigger('click')
    const input = t(w, 'adjust-range-orders-input')
    input.element.value = '2'
    await input.trigger('input')
    // orders = trades count: roll_up 1, roll_down 2, reduce 3, ... exit 6; No change (0) is never filtered
    expect(w.findAll('[data-testid="adjust-pick"] option').map((o) => o.element.value)).toEqual(['roll_up', 'roll_down'])
    expect(t(w, 'adjust-showing').text()).toBe('Showing 3 of 7 approaches')
  })

  it('AC-4 / attack 3: an approach with no value for an active filter stays, marked "not available for this filter"', async () => {
    const r = replyFor()
    r.approaches.find((a) => a.id === 'reduce_calls').pop = { value: null, not_available: true, reason: 'x' }
    r.approaches.filter((a) => a.id !== 'reduce_calls').forEach((a, i) => { a.pop = { value: `0.${40 + i}`, not_available: false, reason: null } })
    const { w } = await show(r)
    const input = t(w, 'adjust-range-pop-input')
    input.element.value = '0.45'
    await input.trigger('input')
    expect(t(w, 'adjust-col-reduce_calls').exists()).toBe(true)
    expect(t(w, 'adjust-unavailable-reduce_calls').text()).toBe('not available for this filter')
    expect(t(w, 'adjust-unavailable-roll_up').exists()).toBe(false)
  })

  it('REQ-156 step 3: the button hands the chosen approach\'s legs on as builder legs; no order is placed', async () => {
    const { w, c } = await show(replyFor())
    await t(w, 'adjust-pick').setValue('roll_up')
    await t(w, 'adjust-open').trigger('click')
    await flushPromises()
    const [ev] = w.emitted('prepare')
    expect(ev[0].underlying).toBe('NIFTY')
    expect(ev[0].legs[0]).toMatchObject({ instrument_id: 'NFO:9', action: 'SELL', lots: 1, planned_entry: '90.00', symbol: 'NIFTY26NOV24000CE' })
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
