// u506 (ISSUES.md:59, "The toast appears on top of the Search name box"): the pop-up covered the Search box and the bell.
// Decision: the pop-ups are an overlay anchored just under the header at the right edge: fixed, capped width, stacking
// downward, each dismissible. They move no page content (no reserved slot, no shift) and never cover the header row.
// Structure, not pixels.
import { afterEach, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { routes } from '@/router/routes'
import AppLayout from '@/components/layout/AppLayout.vue'
import { toasts, useToast } from '@/composables/useToast'

afterEach(() => {
  toasts.splice(0)
  document.body.innerHTML = ''
})

async function layout() {
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push('/strategies/my-strategies')
  await router.isReady()
  const w = mount(AppLayout, { global: { plugins: [router] }, attachTo: document.body })
  await flushPromises()
  return w
}

// what decides where the page content sits: every element before it in the layout, by tag and classes
const aboveContent = (w) => {
  const out = []
  for (let e = w.get('[data-testid="app-content"]').element.previousElementSibling; e; e = e.previousElementSibling) {
    if (e.getAttribute('data-testid') !== 'toast-host') out.push(`${e.tagName}.${e.className}`)
  }
  return out
}

describe('u506: the pop-up overlays under the header and never moves or covers the header row', () => {
  it('the pop-up container is outside the header, fixed just below it at the right edge, with a capped width', async () => {
    useToast().showToast('First one', 'info')
    const w = await layout()
    const host = w.get('[data-testid="toast-host"]')
    expect(w.get('[data-testid="app-header"]').element.contains(host.element)).toBe(false)
    expect(host.classes()).toContain('fixed')
    expect(host.classes()).toContain('top-16') // the header is 56 px (h-14): this is under it
    expect(host.classes()).toContain('right-4')
    expect(host.classes()).toContain('w-80')
    expect(host.classes()).toContain('flex-col') // several stack downward
    expect(host.classes().some((c) => /^(h-|min-h-)/.test(c))).toBe(false) // no reserved slot
    w.unmount()
  })

  it('with 0, 1 and 3 pop-ups the page content sits in the same place: nothing above it changes', async () => {
    const { showToast } = useToast()
    const w0 = await layout()
    const none = aboveContent(w0)
    w0.unmount()
    showToast('First one', 'info')
    const w1 = await layout()
    const one = aboveContent(w1)
    expect(w1.findAll('[data-testid="toast"]')).toHaveLength(1)
    w1.unmount()
    showToast('Second one', 'info')
    showToast('Third one', 'info')
    const w3 = await layout()
    const three = aboveContent(w3)
    expect(w3.findAll('[data-testid="toast"]')).toHaveLength(3)
    w3.unmount()
    expect(one).toEqual(none)
    expect(three).toEqual(none)
  })

  it('each pop-up has a dismiss control and dismissing removes only that one', async () => {
    useToast().showToast('First one', 'info')
    useToast().showToast('Second one', 'info')
    const w = await layout()
    const dismiss = w.findAll('[data-testid="toast-dismiss"]')
    expect(dismiss).toHaveLength(2)
    await dismiss[0].trigger('click')
    expect(w.findAll('[data-testid="toast"]')).toHaveLength(1)
    expect(w.get('[data-testid="toast"]').text()).toContain('Second one')
    w.unmount()
  })
})
