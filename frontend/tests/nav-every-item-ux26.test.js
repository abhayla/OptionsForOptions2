// UX-26 (27 Nov live test): "one top-menu item did not open on click". A real click on EVERY item of EVERY section menu
// must land on that item's own path. If this passes, the report is "test-tool click, no defect".
import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { routes } from '@/router/routes'
import { MENU_SECTIONS } from '@/router/nav'
import AppHeader from '@/components/layout/AppHeader.vue'

afterEach(() => { document.body.innerHTML = '' })

describe('UX-26: every top-menu item opens on a click', () => {
  for (const section of MENU_SECTIONS) {
    it(`${section.label}: each item navigates to its own path`, async () => {
      const router = createRouter({ history: createMemoryHistory(), routes })
      router.push('/home')
      await router.isReady()
      const w = mount(AppHeader, { global: { plugins: [router] }, attachTo: document.body })
      await flushPromises()
      const count = (await (async () => {
        await w.get(`[data-testid="nav-menu-toggle-${section.key}"]`).trigger('click', { detail: 0 })
        await flushPromises()
        return w.findAll('[data-testid="nav-menu-item"]').length
      })())
      expect(count).toBe(section.items.length)
      for (let n = 0; n < count; n++) {
        await router.push('/home/overview')
        await flushPromises()
        if (!w.find('[data-testid="nav-menu"]').exists()) {
          await w.get(`[data-testid="nav-menu-toggle-${section.key}"]`).trigger('click', { detail: 0 })
          await flushPromises()
        }
        const item = w.findAll('[data-testid="nav-menu-item"]')[n]
        const target = router.resolve(item.element.getAttribute('href')).path
        await item.trigger('click')
        await vi.waitFor(() => expect(router.currentRoute.value.path, `${section.label} item ${n + 1}`).toBe(target), { timeout: 4000 }) // a page loads lazily
        expect(target).not.toBe('/home')
      }
      w.unmount()
    })
  }
})
