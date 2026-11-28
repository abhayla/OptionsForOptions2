// Lane F2 (coordinator, TG2 W-29 step 57): a closed trade showed a "Plan watch" heading with "This trade is closed; nothing is watched."
// under it. ADR-330 (57): a closed or settled trade has no Plan watch box. The plan block (PlanEntry) is not touched.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const calls = []
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const get = (url) => { calls.push(url); return Promise.reject({ status: 500, parts: null }) }
  return { ...actual, default: { get, post: get, put: get } }
})
import PlanWatch from '@/components/strategy/PlanWatch.vue'
import { resetPlanWatchQueueForTests } from '@/lib/planWatchQueue'

const mounted = []
beforeEach(() => { calls.length = 0; resetPlanWatchQueueForTests() })
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()) })

describe('a closed trade has no Plan watch box', () => {
  it('no box, no heading, no sentence, no read', async () => {
    const w = mount(PlanWatch, { props: { strategyId: 7, closed: true } })
    mounted.push(w)
    await flushPromises()
    expect(w.find('[data-testid="plan-watch"]').exists()).toBe(false)
    expect(w.find('[data-testid="plan-watch-title"]').exists()).toBe(false)
    expect(w.find('[data-testid="plan-watch-closed"]').exists()).toBe(false)
    expect(w.text()).not.toContain('Plan watch')
    expect(w.text()).not.toContain('nothing is watched')
    expect(calls).toEqual([])
  })
  it('the same trade open: the box is there with its heading and reads', async () => {
    const w = mount(PlanWatch, { props: { strategyId: 7, closed: false } })
    mounted.push(w)
    await flushPromises()
    expect(w.find('[data-testid="plan-watch-title"]').text()).toBe('Plan watch')
    expect(calls).toContain('/strategies/7/plan-watch')
  })
  it('a closed trade that opens again (a re-buy): the box appears and reads from then on', async () => {
    const w = mount(PlanWatch, { props: { strategyId: 7, closed: true } })
    mounted.push(w)
    await flushPromises()
    expect(w.find('[data-testid="plan-watch"]').exists()).toBe(false)
    await w.setProps({ closed: false })
    await flushPromises()
    expect(w.find('[data-testid="plan-watch-title"]').text()).toBe('Plan watch')
    expect(calls).toContain('/strategies/7/plan-watch')
  })
})
