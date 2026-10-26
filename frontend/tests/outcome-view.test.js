// REQ-034 AC-7 / AC-1 on the mounted Builder page (row 22b, W-150): the outcome view as the user sees it. The plain
// sentences, the figures, the payoff, the scenario table and the margin line are on the page with no click; only the
// per-leg Bid / Ask block is collapsed, and one click on its summary opens it. The answer is a REAL outcome response
// (tests/fixtures/outcome-condor.json, NIFTY 13-Oct iron condor on the recorded 2026-10-08 frames); its margin slot is
// replaced by the backend's own CHECKED block (tests/fixtures/outcome-margin-states.json). Every expected string is
// read from those files, not typed here, except the summary wording and the hidden reason, which are the contract.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import real from './fixtures/outcome-condor.json'
import MARGIN from './fixtures/outcome-margin-states.json'
import { groupMoney } from '@/lib/displayFormat'

let apiAnswer = null
let capabilities = {}
const drawn = vi.hoisted(() => [])
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return {
    ...actual,
    default: {
      get: (url) => (url === '/broker/capabilities' ? Promise.resolve({ data: capabilities }) : Promise.reject(new Error('unmocked get ' + url))),
      post: () => Promise.resolve({ data: apiAnswer }),
    },
  }
})
vi.mock('chart.js/auto', () => ({ default: class { constructor(_ctx, config) { drawn.push(config) } destroy() {} } }))
import StrategyBuilderPage from '@/pages/StrategyBuilderPage.vue'
import { resetCapabilities } from '@/lib/brokerCapabilities'

const SUMMARY_TEXT = 'Details: bid and ask per leg'
const HIDDEN_REASON = 'Margin from the broker is not available for this account.'
const DRAFT = { underlying: 'NIFTY', legs: real.legs.map((l) => ({ instrument_id: l.instrument_id, action: l.action, lots: l.lots,
  planned_entry: l.planned_entry, captured_at: l.captured_at })) }
const t = (w, id) => w.find(`[data-testid="${id}"]`)

async function openBuilder(answer, caps) {
  apiAnswer = answer
  capabilities = caps
  resetCapabilities()
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/strategy/builder', component: StrategyBuilderPage }] })
  await router.push({ path: '/strategy/builder', query: { draft: JSON.stringify(DRAFT) } })
  await router.isReady()
  const w = mount(StrategyBuilderPage, { attachTo: document.body, global: { plugins: [router] } })
  await flushPromises()
  return w
}

const WITH_MARGIN = { ...real, margin: MARGIN.enough }
const MARGIN_ON = { basket_margin_quote: true }

beforeEach(() => { drawn.length = 0 })

describe('REQ-034 AC-7: the technical detail is expandable (core)', () => {
  it('AC-7 core: the Bid/Ask block is closed by default and opens on one click of its summary', async () => {
    const w = await openBuilder(WITH_MARGIN, MARGIN_ON)
    const details = t(w, 'advanced-details')
    expect(details.element.tagName).toBe('DETAILS')
    expect(details.element.open).toBe(false)
    expect(details.find('summary').text()).toBe(SUMMARY_TEXT)
    await details.find('summary').trigger('click')
    expect(details.element.open).toBe(true)
    const rows = details.findAll('tbody tr')
    expect(rows).toHaveLength(real.leg_quotes.length)
    for (const q of real.leg_quotes) {
      const row = details.find(`tr[data-leg="${q.instrument_id}"]`)
      expect(row.find('[data-testid="adv-bid"]').text()).toBe(q.bid)
      expect(row.find('[data-testid="adv-ask"]').text()).toBe(q.ask)
    }
    w.unmount()
  })

  it('AC-7: a second click closes it again', async () => {
    const w = await openBuilder(WITH_MARGIN, MARGIN_ON)
    const details = t(w, 'advanced-details')
    await details.find('summary').trigger('click')
    await details.find('summary').trigger('click')
    expect(details.element.open).toBe(false)
    w.unmount()
  })
})

describe('REQ-034 AC-1: the outcome is on the page with no click', () => {
  it('AC-1: the plain sentences and the figures show from the answer, outside the closed block', async () => {
    const w = await openBuilder(WITH_MARGIN, MARGIN_ON)
    expect(t(w, 'advanced-details').element.open).toBe(false)
    expect(t(w, 'sum-make').text()).toBe(real.summary.what_can_i_make)
    expect(t(w, 'sum-lose').text()).toBe(real.summary.what_can_i_lose)
    expect(t(w, 'sum-start').text()).toBe(real.summary.where_do_i_start_losing)
    expect(t(w, 'max-profit').attributes('data-raw')).toContain(real.summary.max_profit)
    expect(t(w, 'max-loss').attributes('data-raw')).toContain(real.summary.max_loss)
    expect(t(w, 'breakevens').text()).toBe(groupMoney(real.summary.breakevens.join(', ')))
    for (const id of ['summary-cards', 'sum-make', 'sum-lose', 'sum-start', 'strategy-table', 'payoff-chart', 'margin']) {
      expect(t(w, 'advanced-details').find(`[data-testid="${id}"]`).exists()).toBe(false) // none of it hides in the block
    }
    w.unmount()
  })

  it('AC-1: the payoff is drawn from the answer points, and the scenario table has the API columns, with no click', async () => {
    const w = await openBuilder(WITH_MARGIN, MARGIN_ON)
    expect(drawn).toHaveLength(1)
    expect(drawn[0].data.labels).toEqual(real.payoff.points.map((p) => p.level))
    expect(t(w, 'payoff-first').text()).toBe(real.payoff.points[0].level)
    expect(t(w, 'strategy-table').exists()).toBe(true)
    expect(w.findAll('[data-testid="col-head"]')).toHaveLength(real.table.columns.length)
    w.unmount()
  })

  it('AC-1: the margin line shows the answer figures when the capability allows it', async () => {
    const w = await openBuilder(WITH_MARGIN, MARGIN_ON)
    expect(t(w, 'margin').attributes('data-margin-state')).toBe('CHECKED')
    expect(t(w, 'margin-figures').text()).toBe(MARGIN.enough.reason) // the server's own text, never relabelled
    expect(t(w, 'margin-checked-at').exists()).toBe(true)
    w.unmount()
  })

  it('AC-1: the capability off shows the documented hidden state and no figure is invented', async () => {
    const w = await openBuilder(WITH_MARGIN, {})
    expect(t(w, 'margin').attributes('data-margin-state')).toBe('HIDDEN')
    expect(t(w, 'margin-hidden-reason').text()).toBe(HIDDEN_REASON)
    expect(t(w, 'margin-figures').exists()).toBe(false)
    expect(w.text()).not.toContain(MARGIN.enough.needed)
    w.unmount()
  })
})

describe('answer states of the details block (standing item d)', () => {
  it('COMPUTED without leg_quotes: no details block, the rest of the outcome still shows', async () => {
    const { leg_quotes: _drop, ...bare } = WITH_MARGIN
    const w = await openBuilder(bare, MARGIN_ON)
    expect(t(w, 'advanced-details').exists()).toBe(false)
    expect(t(w, 'sum-make').text()).toBe(real.summary.what_can_i_make)
    expect(t(w, 'margin-figures').exists()).toBe(true)
    w.unmount()
  })
})
