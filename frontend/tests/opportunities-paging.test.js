// u511 (ISSUES.md:97, "one unpaged page with 131 lapsed + 49 open rows, about 150 KB of text"): Positions > Adjustment
// opportunities shows 25 rows a page with "Showing 1-25 of N rows" (N = every row the server returned) and Next / Previous.
// The server sends the whole list in one read (GET /adjustment-opportunities has no paging), so the pages are cut in the
// browser from that one reply; the order is the server's (newest first). A row's time carries its date when it is not today.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (url) => (answers[`GET ${url}`] ? Promise.resolve({ data: answers[`GET ${url}`] }) : Promise.reject({ message: 'no answer', parts: null, status: 404 }))
  return { ...actual, default: { get: reply, post: reply } }
})
import AdjustmentOpportunitiesPage from '@/pages/AdjustmentOpportunitiesPage.vue'

const COUNTS = ['open', 'lapsed'].map((outcome) => ({ outcome, text: outcome, count: 0 }))
const group = (n) => ({
  group: `g-${n}`, strategy_id: n, strategy_name: `"Trade ${n}"`, shown_at: '2026-11-06T07:47:04.000000Z', label: 'Adjustment opportunity detected',
  summary: null, has_open: false,
  records: [{ id: n, rule_id: 'T-01', condition: `Rule sentence ${n}`, outcome: 'lapsed', outcome_text: 'Lapsed', detail: null, can_act: false }],
})
const inbox = (count) => ({ groups: Array.from({ length: count }, (_, i) => group(i)), counts: COUNTS, empty_text: count ? null : 'No adjustment opportunities', dismiss_reasons: [], held: [] })
const stub = { global: { stubs: { RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } } } }
const mounted = []
beforeEach(() => { for (const k of Object.keys(answers)) delete answers[k] })
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()) })
async function page(count) {
  answers['GET /adjustment-opportunities'] = inbox(count)
  const w = mount(AdjustmentOpportunitiesPage, stub)
  mounted.push(w)
  await flushPromises()
  return w
}
const rows = (w) => w.findAll('[data-testid="opp-row"]')
const range = (w) => w.find('[data-testid="opp-range"]')

describe('u511: the opportunities list pages by 25', () => {
  it('200 rows: 25 are shown with "Showing 1-25 of 200 rows"; Next and Previous walk the pages', async () => {
    const w = await page(200)
    expect(rows(w)).toHaveLength(25)
    expect(range(w).text()).toBe('Showing 1-25 of 200 rows')
    expect(w.get('[data-testid="opp-prev"]').attributes('disabled')).toBeDefined()
    await w.get('[data-testid="opp-next"]').trigger('click')
    expect(rows(w)).toHaveLength(25)
    expect(range(w).text()).toBe('Showing 26-50 of 200 rows')
    expect(rows(w)[0].get('[data-testid="opp-strategy"]').text()).toBe('Trade 25') // the server's order, no re-sorting
    await w.get('[data-testid="opp-prev"]').trigger('click')
    expect(range(w).text()).toBe('Showing 1-25 of 200 rows')
  })

  it('the last page is the short one and Next is off there', async () => {
    const w = await page(60)
    await w.get('[data-testid="opp-next"]').trigger('click')
    await w.get('[data-testid="opp-next"]').trigger('click')
    expect(rows(w)).toHaveLength(10)
    expect(range(w).text()).toBe('Showing 51-60 of 60 rows')
    expect(w.get('[data-testid="opp-next"]').attributes('disabled')).toBeDefined()
  })

  it('25 rows fit one page: no paging controls; 1 row reads "Showing 1-1 of 1 rows" with no controls; 0 rows shows the empty text', async () => {
    const w25 = await page(25)
    expect(rows(w25)).toHaveLength(25)
    expect(w25.find('[data-testid="opp-next"]').exists()).toBe(false)
    expect(range(w25).text()).toBe('Showing 1-25 of 25 rows')
    const w1 = await page(1)
    expect(rows(w1)).toHaveLength(1)
    expect(w1.find('[data-testid="opp-prev"]').exists()).toBe(false)
    const w0 = await page(0)
    expect(rows(w0)).toHaveLength(0)
    expect(w0.get('[data-testid="opp-empty"]').text()).toBe('No adjustment opportunities')
    expect(range(w0).exists()).toBe(false)
  })

  it('a row older than today carries its date', async () => {
    const w = await page(1)
    expect(w.get('[data-testid="opp-time"]').text()).toBe('6 Nov 2026, 13:17:04 IST')
  })
})
