// P12 (S-07): a click on a section label toggles its menu when the page is already at that section's first path.
import { describe, expect, it, vi, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { routes } from '@/router/routes'
import AppHeader from '@/components/layout/AppHeader.vue'

async function mountAt(url) {
  const router = createRouter({ history: createMemoryHistory(), routes })
  router.push(url)
  await router.isReady()
  const w = mount(AppHeader, { global: { plugins: [router] }, attachTo: document.body })
  await flushPromises()
  return { w, router }
}
const menu = (w) => w.find('[data-testid="nav-menu"]')

afterEach(() => {
  vi.useRealTimers()
  document.body.innerHTML = ''
})

describe('section label click (P12)', () => {
  it('click Strategies label on its own path opens the menu, a second click closes it', async () => {
    const { w, router } = await mountAt('/strategies/my-strategies')
    expect(menu(w).exists()).toBe(false)
    await w.get('[data-testid="nav-strategies"]').trigger('click')
    await flushPromises()
    expect(menu(w).exists()).toBe(true)
    expect(menu(w).attributes('data-section')).toBe('strategies')
    expect(router.currentRoute.value.fullPath).toBe('/strategies/my-strategies')
    await w.get('[data-testid="nav-strategies"]').trigger('click')
    await flushPromises()
    expect(menu(w).exists()).toBe(false)
    w.unmount()
  })

  it('click on a label from another path navigates and leaves the menu closed', async () => {
    const { w, router } = await mountAt('/home')
    await w.get('[data-testid="nav-strategies"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/strategies/my-strategies')
    expect(menu(w).exists()).toBe(false)
    w.unmount()
  })

  it('Enter/Space on the toggle (click detail 0) still opens the menu and focuses the first item', async () => {
    const { w } = await mountAt('/strategies/my-strategies')
    await w.get('[data-testid="nav-menu-toggle-strategies"]').trigger('click', { detail: 0 })
    await flushPromises()
    expect(menu(w).exists()).toBe(true)
    expect(document.activeElement.getAttribute('role')).toBe('menuitem')
    w.unmount()
  })

  it('a click inside the open panel does not toggle it by the label rule', async () => {
    const { w } = await mountAt('/strategies/my-strategies')
    await w.get('[data-testid="nav-strategies"]').trigger('click')
    await flushPromises()
    await menu(w).trigger('click')
    await flushPromises()
    expect(menu(w).exists()).toBe(true)
    w.unmount()
  })
})
