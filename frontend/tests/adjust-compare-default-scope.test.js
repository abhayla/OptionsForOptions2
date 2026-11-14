// GC-ICFIX issue 14 (ADR-214 2a/2b): the offer screen shows every approach that applies unless the user ticked some in the
// drawer. A link with no ticks (inbox, alerts) must not carry a pick, or the compare opens on No change alone ("1 of 7").
import { describe, it, expect, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import adj02 from './fixtures/adjust-approaches-adj02.json'

vi.mock('chart.js/auto', () => ({ default: class { constructor() {} destroy() {} } }))
import AdjustCompare from '@/components/strategy/AdjustCompare.vue'
import { compareUrl, picksFromQuery } from '@/lib/adjustDrawer'

const N = adj02.approaches.length
const client = { post: vi.fn(async () => ({ data: adj02 })), get: vi.fn(async () => { throw Object.assign(new Error('x'), { status: 404 }) }) }
async function open(query) {
  const w = mount(AdjustCompare, { attachTo: document.body, props: { strategyId: 72, client, picked: picksFromQuery(query) } })
  await flushPromises()
  return w
}
const cols = (w) => w.findAll('thead th[data-testid^="adjust-col-"]').length
const showing = (w) => w.find('[data-testid="adjust-showing"]').text()
const ids = adj02.approaches.map((a) => a.id)

describe('issue 14: default scope of the offer screen', () => {
  it('a link with no ticks carries no pick, and the compare opens on every approach', async () => {
    const url = compareUrl(72, null, ['11'])
    expect(url).toBe('/strategy/builder?adjust=72&opp=11')
    const w = await open(new URL(url, 'http://x').searchParams.get('pick') ?? undefined)
    expect(cols(w)).toBe(N)
    expect(showing(w)).toBe(`Showing ${N} of ${N} approaches`)
  })

  it('the drawer unticked-all link still means "No change only"', () => {
    expect(compareUrl(72, [])).toBe('/strategy/builder?adjust=72&pick=A-36')
  })

  it('untick two -> N-2 columns; tick one back -> N-1 (the pick is what the compare shows)', async () => {
    const w2 = await open(ids.slice(0, N - 2).join(','))
    expect(cols(w2)).toBe(N - 2)
    expect(showing(w2)).toBe(`Showing ${N - 2} of ${N - 2} approaches`)
    const w1 = await open(ids.slice(0, N - 1).join(','))
    expect(cols(w1)).toBe(N - 1)
    expect(showing(w1)).toBe(`Showing ${N - 1} of ${N - 1} approaches`)
  })
})
