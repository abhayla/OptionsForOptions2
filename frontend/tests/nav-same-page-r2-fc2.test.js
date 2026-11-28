// Lane FC2 (R2, 28 Nov) UX-A19 / board I-72: clicking a menu item for the page that is already shown must close the menu.
// AppHeader.vue closed its menu only when route.fullPath changed (watch), so a same-page click navigated nowhere and the menu stayed
// open. Seen red on this base (as it.fails, run as a plain it: "expected true to be false"); fixed by @click="closeMenu()" on the item.
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
afterEach(() => { vi.useRealTimers(); document.body.innerHTML = '' })

describe('UX-A19 same-page click on a menu item', () => {
  it('Create Strategy clicked while on Create Strategy: the menu closes (twice in a row too)', async () => {
    const { w } = await mountAt('/strategies/create-strategy')
    for (let n = 0; n < 2; n += 1) {
      await w.get('[data-testid="nav-menu-toggle-strategies"]').trigger('click')
      await flushPromises()
      expect(w.find('[data-testid="nav-menu"]').exists()).toBe(true)
      const item = w.findAll('[data-testid="nav-menu-item"]').find((i) => i.text().includes('Create Strategy'))
      expect(item).toBeTruthy()
      await item.trigger('click')
      await flushPromises()
      expect(w.find('[data-testid="nav-menu"]').exists()).toBe(false)
    }
    w.unmount()
  })
})
