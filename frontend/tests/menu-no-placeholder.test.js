// u504 (ISSUES.md:16, :29, :81): a first-time user landed on "Home is coming" / "Strategies is coming". Every link the top bar
// and the account menu offer must open a built page, and "/" must open the first real page a trader needs (ADR-193 (4) does
// not name a landing page, so it is My Strategies). Unbuilt pages stay reachable by their own address (ADR-193 (4)).
import { afterEach, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { routes } from '@/router/routes'
import AppHeader from '@/components/layout/AppHeader.vue'
import PlaceholderPage from '@/pages/PlaceholderPage.vue'

afterEach(() => {
  document.body.innerHTML = ''
})

async function landedComponent(router, url) {
  await router.push(url)
  await router.isReady()
  return { page: router.currentRoute.value.matched.at(-1).components.default, path: router.currentRoute.value.fullPath }
}

describe('u504: no menu entry leads to the placeholder page', () => {
  it('"/" opens My Strategies, a built page', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes })
    const { page, path } = await landedComponent(router, '/')
    expect(path).toBe('/strategies/my-strategies')
    expect(page).not.toBe(PlaceholderPage)
  })

  it('every link in the top bar, every section menu and the account menu opens a built page', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes })
    await router.push('/strategies/my-strategies')
    await router.isReady()
    const w = mount(AppHeader, { global: { plugins: [router] }, attachTo: document.body })
    await flushPromises()
    const hrefs = new Set([...w.get('[data-testid="primary-nav"]').findAll('a')].map((a) => a.attributes('href')))
    hrefs.add(w.get('[data-testid="brand"]').attributes('href'))
    for (const toggle of w.findAll('[data-testid^="nav-menu-toggle-"]')) {
      await toggle.trigger('click')
      for (const a of w.findAll('[data-testid="nav-menu-item"]')) hrefs.add(a.attributes('href'))
    }
    await w.get('[data-testid="avatar-menu"]').trigger('click')
    hrefs.add(w.get('[data-testid="account-menu-title"]').attributes('href'))
    for (const a of w.findAll('[data-testid="account-menu-item"]')) hrefs.add(a.attributes('href'))
    expect(hrefs.size).toBeGreaterThan(10)
    const stuck = []
    for (const href of hrefs) {
      const { page } = await landedComponent(router, href)
      if (page === PlaceholderPage) stuck.push(href)
    }
    expect(stuck).toEqual([])
    w.unmount()
  })

  it('a section with no built page (Orders) is not in the top bar; its pages still open by address', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes })
    await router.push('/orders/pending')
    await router.isReady()
    const w = mount(AppHeader, { global: { plugins: [router] }, attachTo: document.body })
    await flushPromises()
    expect(w.find('[data-testid="nav-orders"]').exists()).toBe(false)
    expect(router.currentRoute.value.matched.at(-1).components.default).toBe(PlaceholderPage)
    w.unmount()
  })
})
