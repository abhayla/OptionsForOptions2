// D-21 (ADR-320 (3)): every approach of the Compare shows a "What changes" block, before against after, eight measures
// each marked up or down, one plain reason line where a number moves against the action's name, and no verdict word.
// The figures are the server's texts (ADJ-02, Reduce A-29, the nearest fixture to strategy 164); nothing is computed here.
import { describe, it, expect, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { flushPromises, mount } from '@vue/test-utils'
import adj02 from './fixtures/adjust-approaches-adj02.json'
import whatChanges from './fixtures/adjust-what-changes-adj02.json'

vi.mock('chart.js/auto', () => ({ default: class { constructor() {} destroy() {} update() {} } }))

import AdjustCompare from '@/components/strategy/AdjustCompare.vue'

const MEASURES = ['profit_range', 'breakeven_distance', 'pop', 'max_profit', 'max_loss', 'credit', 'margin', 'net_delta']
const VERDICT = /\b(better|worse|best|worst|recommend\w*|should|winner|prefer\w*)\b/i

async function open() {
  const reply = JSON.parse(JSON.stringify(adj02))
  reply.what_changes = JSON.parse(JSON.stringify(whatChanges))
  const client = { post: vi.fn(async () => ({ data: reply })), get: vi.fn(async () => ({ data: {} })) }
  const w = mount(AdjustCompare, { props: { strategyId: 72, client } })
  await flushPromises()
  return w
}

describe('Compare: What changes', () => {
  it('draws one block per approach with the eight measures, before against after, each marked up or down', async () => {
    const w = await open()
    const block = w.find('[data-testid="adjust-wc-A-29"]')
    expect(block.exists()).toBe(true)
    expect(block.find('[data-testid="adjust-wc-title-A-29"]').text()).toBe('What changes')
    for (const m of MEASURES) {
      const row = block.find(`[data-testid="adjust-wc-A-29-${m}"]`)
      expect(row.exists(), m).toBe(true)
      const r = whatChanges['A-29'].rows.find((x) => x.id === m)
      expect(row.find('[data-testid="adjust-wc-before"]').text()).toBe(r.before_text)
      expect(row.find('[data-testid="adjust-wc-after"]').text()).toBe(r.after_text)
      expect(row.find('[data-testid="adjust-wc-direction"]').text()).toBe(r.direction_text)
    }
    expect(block.find('[data-testid="adjust-wc-A-29-max_loss"] [data-testid="adjust-wc-direction"]').text()).toBe('up')
  })

  it('shows the reason line only where the server sent one, and "not available" with its reason', async () => {
    const w = await open()
    expect(w.find('[data-testid="adjust-wc-reason-A-29"]').text()).toBe(whatChanges['A-29'].reason_line)
    expect(w.find('[data-testid="adjust-wc-reason-A-36"]').exists()).toBe(false)
    const delta = w.find('[data-testid="adjust-wc-A-31-net_delta"]')
    expect(delta.find('[data-testid="adjust-wc-after"]').text()).toBe('Not available')
    expect(delta.find('[data-testid="adjust-wc-unavailable"]').text()).toContain('No position left after exit')
  })

  it('holds no verdict word in the block, in the server texts or in the component source', async () => {
    const w = await open()
    const rendered = w.findAll('[data-testid^="adjust-wc-"]').map((x) => x.text()).join(' ')
    expect(rendered.length).toBeGreaterThan(200)
    expect(VERDICT.test(rendered)).toBe(false)
    expect(VERDICT.test(JSON.stringify(whatChanges))).toBe(false)
    const source = readFileSync('src/components/strategy/AdjustWhatChanges.vue', 'utf8') // vitest runs in frontend/
    expect(VERDICT.test(source)).toBe(false)
  })

  it('draws no block when the reply carries none (no spot, or an older reply)', async () => {
    const reply = JSON.parse(JSON.stringify(adj02))
    const client = { post: vi.fn(async () => ({ data: reply })), get: vi.fn(async () => ({ data: {} })) }
    const w = mount(AdjustCompare, { props: { strategyId: 72, client } })
    await flushPromises()
    expect(w.find('[data-testid^="adjust-wc-"]').exists()).toBe(false)
  })
})
