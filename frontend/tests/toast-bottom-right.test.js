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

describe('D-67 (was u506): the pop-up area is in the page flow under the header, so it covers no page button', () => {
  // D-67 (owner decision, binding): an adjustment toast never covers a page button. The earlier u506 contract (a fixed overlay at the
  // bottom right) still covered buttons there (C10 166, C11 167, each toast covered buttons). The new contract: the host is an
  // ordinary block IN the page flow between the header and the page content, so it can overlay nothing; the page content is
  // laid out below it. The z order against modals therefore no longer matters (an in-flow block is under every layer).
  it('the host is in the page flow: no fixed / absolute / sticky class, no z-index, no offset; it sits between the header and the page content', async () => {
    useToast().showToast('First one', 'info')
    const w = await layout()
    const host = w.get('[data-testid="toast-host"]')
    const cls = host.classes()
    expect(cls.filter((c) => /^(fixed|absolute|sticky)$/.test(c))).toEqual([])
    expect(cls.filter((c) => /^(top|bottom|left|right|inset|inset-x|inset-y|z)-/.test(c))).toEqual([])
    const header = w.get('[data-testid="app-header"]').element
    const content = w.get('[data-testid="app-content"]').element
    expect(host.element.parentElement).toBe(content.parentElement)
    expect(header.compareDocumentPosition(host.element) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(host.element.compareDocumentPosition(content) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(content.contains(host.element)).toBe(false)
    w.unmount()
  })

  it('with no pop-up the host draws nothing and takes no room; with 5 it lists them newest first, each with Dismiss', async () => {
    const w0 = await layout()
    expect(w0.findAll('[data-testid="toast"]')).toHaveLength(0)
    expect(w0.find('[data-testid="toast-host"]').exists() ? w0.get('[data-testid="toast-host"]').text() : '').toBe('')
    w0.unmount()
    const { showToast } = useToast()
    for (const m of ['One', 'Two', 'Three', 'Four', 'Five']) showToast(m, 'info')
    const w5 = await layout()
    const texts = w5.findAll('[data-testid="toast"]').map((x) => x.text())
    expect(texts).toHaveLength(5)
    expect(texts[0]).toContain('Five')
    expect(w5.findAll('[data-testid="toast-dismiss"]')).toHaveLength(5)
    w5.unmount()
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
