// u506 (ISSUES.md:59, "The toast appears on top of the Search name box"): a floating toast covered the page's top-right
// corner, where the Search box and the bell sit, and a click meant for the box landed on the toast. The toasts now sit in
// the page flow under the header row (they push the page down, never over it) and stack downward. Structure, not pixels.
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

describe('u506: the toast pop-up never covers the page', () => {
  it('with one and with several toasts: the host is in the page flow, after the header and before the page content', async () => {
    const { showToast } = useToast()
    showToast('First one', 'info')
    showToast('Second one', 'info')
    showToast('Third one', 'info')
    const w = await layout()
    const host = w.get('[data-testid="toast-host"]').element
    const header = w.get('[data-testid="app-header"]').element
    const content = w.get('[data-testid="app-content"]').element
    expect(host.className).not.toMatch(/\b(fixed|absolute)\b/)
    expect(header.contains(host)).toBe(false)
    expect(header.compareDocumentPosition(host) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(host.compareDocumentPosition(content) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(host.className).toContain('flex-col') // several stack downward
    expect(w.findAll('[data-testid="toast"]')).toHaveLength(3)
    w.unmount()
  })

  // Coordinator round: a pop-up that moves the page while the user is about to click is a hazard (a click could land on a
  // Confirm). The slot is always there with a fixed height, so a toast appearing changes nothing around it.
  it('the toast slot has the same fixed height with 0, 1 and 3 toasts, so the page content never moves', async () => {
    const { showToast } = useToast()
    const slotOf = async () => {
      const w = await layout()
      const host = w.get('[data-testid="toast-host"]')
      const out = { cls: host.classes().filter((c) => /^(h-|min-h-|max-h-|overflow)/.test(c)).sort(), count: w.findAll('[data-testid="toast"]').length }
      w.unmount()
      return out
    }
    const none = await slotOf()
    showToast('First one', 'info')
    const one = await slotOf()
    showToast('Second one', 'info')
    showToast('Third one', 'info')
    const three = await slotOf()
    expect([none.count, one.count, three.count]).toEqual([0, 1, 3])
    expect(none.cls.find((c) => /^h-/.test(c))).toBeTruthy() // an explicit fixed height, not content-sized
    expect(none.cls.some((c) => /^overflow-y-/.test(c))).toBe(true) // extra toasts scroll inside the slot
    expect(one.cls).toEqual(none.cls)
    expect(three.cls).toEqual(none.cls)
  })

  it('a toast is dismissible', async () => {
    useToast().showToast('Only one', 'info')
    const w = await layout()
    await w.get('[data-testid="toast-dismiss"]').trigger('click')
    expect(w.findAll('[data-testid="toast"]')).toHaveLength(0)
    w.unmount()
  })
})
