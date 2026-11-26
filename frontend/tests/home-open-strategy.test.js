// S-18 (owner live test 25 Nov): Home "Recent strategies" > "Open in Strategy Builder" must carry the row's strategy id.
// Real ids from the owner's test: 168 and 169. Expected hrefs are written here, not read from the page.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

let strategiesAnswer = []
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: (url) => (url === '/strategies'
    ? Promise.resolve({ data: { strategies: strategiesAnswer } })
    : Promise.resolve({ data: { state: 'NOT_CONNECTED', answered_at: '2026-11-25T03:50:09+00:00', indices: [] } })) } }
})
import HomeOverviewPage from '@/pages/HomeOverviewPage.vue'
import { builderLinkOf } from '@/lib/strategyLinks'

class FakeSocket {
  constructor(url) { this.url = url; this.readyState = 0 }
  send() {}
  close() { this.readyState = 3 }
}
const draft = (id, updated_at) => ({ id, name: `Plan ${id}`, underlying: 'NIFTY', status: 'draft', status_word: 'Draft', revision: 1, created_at: updated_at, updated_at })
const T168 = '2026-11-25T09:00:00+05:30'
const T169 = '2026-11-25T10:00:00+05:30'

async function mountHome() {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/home/overview', component: HomeOverviewPage },
    { path: '/:p(.*)*', component: { template: '<div />' } }] })
  router.push('/home/overview')
  await router.isReady()
  const wrapper = mount(HomeOverviewPage, { global: { plugins: [router] } })
  await flushPromises()
  return { wrapper, router }
}
beforeEach(() => vi.stubGlobal('WebSocket', FakeSocket))
afterEach(() => vi.unstubAllGlobals())

describe('S-18 Home recent strategies open their own strategy', () => {
  it('each link points at its own id', async () => {
    strategiesAnswer = [draft(168, T168), draft(169, T169)]
    const { wrapper } = await mountHome()
    expect(wrapper.get('[data-testid="recent-open-168"]').attributes('href')).toBe('/strategy/builder?strategy=168')
    expect(wrapper.get('[data-testid="recent-open-169"]').attributes('href')).toBe('/strategy/builder?strategy=169')
  })

  it('clicking row 2 opens strategy 169, not 168', async () => {
    strategiesAnswer = [draft(168, T168), draft(169, T169)]
    const { wrapper, router } = await mountHome()
    await wrapper.get('[data-testid="recent-open-169"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/strategy/builder')
    expect(router.currentRoute.value.query.strategy).toBe('169')
  })

  it('a row with no usable id has no link but keeps its grid cell', async () => {
    strategiesAnswer = [draft(null, T168), draft(169, T169)]
    const { wrapper } = await mountHome()
    expect(wrapper.findAll('[data-testid="recent-row"]')).toHaveLength(2)
    expect(wrapper.findAll('a[data-testid^="recent-open-"]')).toHaveLength(1)
    expect(wrapper.find('[data-testid="recent-open-null"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-testid="recent-row"]').every((r) => r.element.children.length === 3)).toBe(true)
  })
})

describe('builderLinkOf', () => {
  it('positive integers (number or digit string) give the builder link', () => {
    expect(builderLinkOf(168)).toEqual({ path: '/strategy/builder', query: { strategy: '168' } })
    expect(builderLinkOf('169')).toEqual({ path: '/strategy/builder', query: { strategy: '169' } })
  })
  it.each([null, undefined, '', 'abc', 0, -1, 1.5, '1.5', '-1', '0', NaN, {}, []])('gives null for %j', (v) => {
    expect(builderLinkOf(v)).toBeNull()
  })
})
