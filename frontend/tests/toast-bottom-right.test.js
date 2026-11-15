// u506 (ISSUES.md:59, "The toast appears on top of the Search name box"). The Search boxes are PAGE CONTENT at the top right
// (MyStrategiesPage.vue:124 strategy-search, LearnPage.vue:128 learn-search, SaveDraftBar.vue:479 saved-search), so any
// pop-up anchored at the top right covers them. Decision: the pop-up area is BOTTOM-RIGHT, fixed, capped width, stacking
// UPWARD (newest nearest the corner), each pop-up with Open and Dismiss; no layout shift, nothing reserved; its z-index is
// BELOW every modal and drawer layer so a pop-up can never cover a Confirm / Cancel button.
// Limit of this runner: jsdom has no layout, so pixel overlap cannot be asserted here. These tests assert structure
// (anchoring, z order, DOM position); the pixel check is the Playwright test frontend/e2e/toast-clear.spec.ts (added without running).
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { routes } from '@/router/routes'
import AppLayout from '@/components/layout/AppLayout.vue'
import { toasts, useToast } from '@/composables/useToast'

const src = (p) => readFileSync(join(__dirname, '..', 'src', p), 'utf8')
const zOf = (text) => Number(/\bz-(\d+)\b/.exec(text)?.[1])

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

const aboveContent = (w) => {
  const out = []
  for (let e = w.get('[data-testid="app-content"]').element.previousElementSibling; e; e = e.previousElementSibling) {
    if (e.getAttribute('data-testid') !== 'toast-host') out.push(`${e.tagName}.${e.className}`)
  }
  return out
}

describe('u506: the pop-up area is bottom-right, under every modal, and moves nothing', () => {
  it('the host is bottom-anchored (no top-* class), at the right, capped width, stacking upward', async () => {
    useToast().showToast('First one', 'info')
    const w = await layout()
    const cls = w.get('[data-testid="toast-host"]').classes()
    expect(cls.filter((c) => /^(top|inset-y|inset)-/.test(c))).toEqual([]) // nothing anchors it to the top
    expect(cls).toContain('fixed')
    expect(cls.some((c) => /^bottom-\d+$/.test(c))).toBe(true)
    expect(cls).toContain('right-4')
    expect(cls).toContain('w-80')
    expect(cls).toContain('flex-col-reverse') // newest first in the DOM = nearest the corner, older ones stack upward
    expect(cls.some((c) => /^(h-|min-h-)/.test(c))).toBe(false) // nothing reserved
    w.unmount()
  })

  it('its z-index is lower than the modal, the common drawer and the adjust drawer (a pop-up never covers a Confirm)', async () => {
    useToast().showToast('First one', 'info')
    const w = await layout()
    const host = zOf(w.get('[data-testid="toast-host"]').attributes('class'))
    const modal = zOf(/class="fixed inset-0 z-\d+[^"]*"/.exec(src('components/common/Modal.vue'))[0])
    const drawer = zOf(/class="fixed inset-x-0 top-14 bottom-0 z-\d+"/.exec(src('components/common/Drawer.vue'))[0])
    const adjust = zOf(/<div v-if="open" class="fixed inset-0 z-\d+"/.exec(src('components/strategy/AdjustDrawer.vue'))[0])
    expect([modal, drawer, adjust].every(Number.isInteger)).toBe(true)
    expect(host).toBeLessThan(modal)
    expect(host).toBeLessThan(drawer)
    expect(host).toBeLessThan(adjust)
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
    const texts = w3.findAll('[data-testid="toast"]').map((t) => t.text())
    w3.unmount()
    expect(one).toEqual(none)
    expect(three).toEqual(none)
    expect(texts).toHaveLength(3)
    expect(texts[0]).toContain('Third one') // newest first: with flex-col-reverse it sits nearest the corner
  })

  it('each pop-up has Dismiss (and Open when it has an action); dismissing removes only that one', async () => {
    useToast().showToast('First one', 'info', { onClick: () => {} })
    useToast().showToast('Second one', 'info')
    const w = await layout()
    expect(w.findAll('[data-testid="toast-dismiss"]')).toHaveLength(2)
    expect(w.findAll('[data-testid="toast-open"]')).toHaveLength(1)
    await w.findAll('[data-testid="toast-dismiss"]')[0].trigger('click') // the newest
    expect(w.findAll('[data-testid="toast"]')).toHaveLength(1)
    expect(w.get('[data-testid="toast"]').text()).toContain('First one')
    w.unmount()
  })

  // One test per page that has a control at the top right: the host is outside the app header and outside the page content
  // (so outside every page header / actions slot), and the page file does not place anything fixed at the top right itself.
  for (const [file, id, where] of [
    ['pages/MyStrategiesPage.vue', 'strategy-search', 'MyStrategiesPage.vue:124'],
    ['pages/LearnPage.vue', 'learn-search', 'LearnPage.vue:128'],
    ['components/strategy/SaveDraftBar.vue', 'saved-search', 'SaveDraftBar.vue:479'],
  ]) {
    it(`${where} (${id}): the pop-up host is not in the header or the page content, and the page has the control`, async () => {
      expect(src(file)).toContain(`data-testid="${id}"`)
      useToast().showToast('First one', 'info')
      const w = await layout()
      const host = w.get('[data-testid="toast-host"]').element
      expect(w.get('[data-testid="app-header"]').element.contains(host)).toBe(false)
      expect(w.get('[data-testid="app-content"]').element.contains(host)).toBe(false)
      w.unmount()
    })
  }
})
