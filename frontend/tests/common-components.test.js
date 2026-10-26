// W-191 (ADR-193, UI study a.5 UI-009..UI-021): each shared part renders; the Drawer traps focus and closes on Esc;
// the Tooltip trigger is a real button reachable by Tab; and (ADR-193 (2), UI-006) the shell and shared parts carry no
// hard-coded hex colour - every colour is a token in style.css.
import { describe, expect, it, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { readFileSync, readdirSync } from 'node:fs'
import Card from '@/components/common/Card.vue'
import Tabs from '@/components/common/Tabs.vue'
import Chip from '@/components/common/Chip.vue'
import Stepper from '@/components/common/Stepper.vue'
import Drawer from '@/components/common/Drawer.vue'
import Tooltip from '@/components/common/Tooltip.vue'
import Modal from '@/components/common/Modal.vue'
import Toast from '@/components/common/Toast.vue'
import EmptyState from '@/components/states/EmptyState.vue'
import ErrorMessage from '@/components/common/ErrorMessage.vue'

afterEach(() => {
  document.body.innerHTML = ''
})

describe('shared parts render', () => {
  it('Card shows its title, actions and body', () => {
    const w = mount(Card, { props: { title: 'New Strategy' }, slots: { default: 'body', actions: '<button>Edit</button>' } })
    expect(w.get('[data-testid="card-title"]').text()).toBe('New Strategy')
    expect(w.text()).toContain('body')
    expect(w.text()).toContain('Edit')
  })

  it('Tabs: both variants are a tablist; arrows move the selection', async () => {
    for (const variant of ['segmented', 'underline']) {
      const w = mount(Tabs, {
        props: { tabs: [{ key: 'a', label: 'Payoff Graph' }, { key: 'b', label: 'Payoff Table' }], modelValue: 'a', variant },
        attachTo: document.body,
      })
      expect(w.get('[role="tablist"]').attributes('data-variant')).toBe(variant)
      expect(w.get('[data-testid="tab-a"]').attributes('aria-selected')).toBe('true')
      await w.get('[data-testid="tab-a"]').trigger('keydown', { key: 'ArrowRight' })
      expect(w.emitted('update:modelValue').at(-1)).toEqual(['b'])
      w.unmount()
    }
  })

  it('Chip renders B/S, CE/PE and state kinds', () => {
    for (const [kind, label] of [['buy', 'B'], ['sell', 'S'], ['opt', 'CE'], ['state', 'Draft']]) {
      const w = mount(Chip, { props: { kind, label } })
      expect(w.get('[data-testid="chip"]').text()).toBe(label)
      expect(w.get('[data-testid="chip"]').attributes('data-kind')).toBe(kind)
    }
  })

  it('Stepper shows the given value and only emits (no maths in the browser)', async () => {
    const w = mount(Stepper, { props: { value: '22550', label: 'strike' } })
    expect(w.get('[data-testid="stepper-value"]').text()).toBe('22550')
    await w.get('[data-testid="stepper-increment"]').trigger('click')
    await w.get('[data-testid="stepper-decrement"]').trigger('click')
    expect(Object.keys(w.emitted())).toEqual(expect.arrayContaining(['increment', 'decrement']))
    expect(w.get('[data-testid="stepper-value"]').text()).toBe('22550')
  })

  it('Modal renders title, body and actions; Esc emits close', async () => {
    const w = mount(Modal, { props: { open: true, title: 'Save strategy' }, slots: { default: 'Name', actions: '<button>Cancel</button><button>Save</button>' }, attachTo: document.body })
    await flushPromises()
    expect(w.get('[data-testid="modal-title"]').text()).toBe('Save strategy')
    expect(document.activeElement).toBe(w.get('[data-testid="modal"]').element)
    await w.get('[data-testid="modal"]').trigger('keydown', { key: 'Escape' })
    expect(w.emitted('close')).toHaveLength(1)
    w.unmount()
  })

  it('Toast shows one line and closes itself after its duration', async () => {
    const w = mount(Toast, { props: { open: true, message: 'Saved', duration: 10 } })
    expect(w.get('[data-testid="toast-message"]').text()).toBe('Saved')
    expect(w.get('[data-testid="toast"]').attributes('role')).toBe('status')
    await new Promise((r) => setTimeout(r, 30))
    expect(w.emitted('close')).toHaveLength(1)
  })

  it('EmptyState keeps its contract (message, one optional action) and shows an optional title', () => {
    const w = mount(EmptyState, { props: { message: 'Nothing here yet.', title: 'Coming soon: Adjustments', actionLabel: 'Create Strategy' } })
    expect(w.get('[data-testid="empty-state-title"]').text()).toBe('Coming soon: Adjustments')
    expect(w.get('[data-testid="empty-state-message"]').text()).toBe('Nothing here yet.')
    expect(w.findAll('button')).toHaveLength(1)
  })

  it('ErrorMessage restyle keeps all four parts, full and compact', () => {
    const parts = { what_happened: 'A', impact: 'B', what_is_blocked: 'C', next_action: 'D' }
    for (const compact of [false, true]) {
      const w = mount(ErrorMessage, { props: { parts, compact } })
      expect(w.text()).toContain('What this means: B')
      expect(w.text()).toContain('What is blocked: C')
      expect(w.text()).toContain('What to do next: D')
      const cls = w.get('[role="alert"]').classes()
      expect(cls).toContain('border-error')
      expect(cls).toContain('bg-error-soft')
      expect(cls).not.toContain('border-loss')
      expect(cls).not.toContain('bg-loss-soft')
    }
  })
})

describe('Modal keyboard (review round 2)', () => {
  it('Tab and Shift+Tab stay inside the dialog', async () => {
    const w = mount(Modal, { props: { open: true, title: 'Save' }, slots: { default: '<input data-testid="f" />', actions: '<button data-testid="cancel">Cancel</button><button data-testid="save">Save</button>' }, attachTo: document.body })
    await flushPromises()
    const dialog = w.get('[data-testid="modal"]')
    const close = w.get('[data-testid="modal-close"]').element
    const save = w.get('[data-testid="save"]').element
    save.focus()
    await dialog.trigger('keydown', { key: 'Tab' })
    expect(document.activeElement).toBe(close)
    await dialog.trigger('keydown', { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(save)
    w.unmount()
  })
})

describe('Drawer (UI-016)', () => {
  const mountDrawer = () =>
    mount(
      {
        components: { Drawer },
        data: () => ({ open: false }),
        template: `<div><button data-testid="opener" @click="open = true">open</button>
          <Drawer :open="open" title="Add a leg" side="left" @close="open = false">
            <input data-testid="first" /><button data-testid="middle">x</button>
            <template #footer><button data-testid="last">Add</button></template>
          </Drawer></div>`,
      },
      { attachTo: document.body },
    )

  it('moves focus inside, traps Tab and Shift+Tab, and closes on Esc returning focus to the opener', async () => {
    const w = mountDrawer()
    const opener = w.get('[data-testid="opener"]')
    opener.element.focus()
    await opener.trigger('click')
    await flushPromises()
    const drawer = w.get('[data-testid="drawer"]')
    expect(drawer.attributes('role')).toBe('dialog')
    expect(drawer.attributes('aria-modal')).toBe('true')
    const close = w.get('[data-testid="drawer-close"]').element
    const last = w.get('[data-testid="last"]').element
    expect(document.activeElement).toBe(close) // first focusable inside
    last.focus()
    await drawer.trigger('keydown', { key: 'Tab' })
    expect(document.activeElement).toBe(close) // wrapped forward
    await drawer.trigger('keydown', { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(last) // wrapped back
    await drawer.trigger('keydown', { key: 'Escape' })
    await flushPromises()
    expect(w.find('[data-testid="drawer"]').exists()).toBe(false)
    expect(document.activeElement).toBe(opener.element)
    w.unmount()
  })

  it('Esc closes it even when the key lands on the overlay, not in the panel', async () => {
    const w = mount(Drawer, { props: { open: true, title: 'Warnings' } })
    await w.get('[data-testid="drawer-overlay"]').trigger('keydown', { key: 'Escape' })
    expect(w.emitted('close')).toHaveLength(1)
  })

  it('an overlay click closes it', async () => {
    const w = mount(Drawer, { props: { open: true, title: 'Warnings' } })
    await w.get('[data-testid="drawer-overlay"]').trigger('click')
    expect(w.emitted('close')).toHaveLength(1)
  })
})

describe('Tooltip (UI-017, Revision 1 M6)', () => {
  it('the trigger is a button in the Tab order; focus shows the text, Esc hides it, a tap toggles it', async () => {
    const w = mount(Tooltip, { props: { text: 'The most this strategy can lose.' }, attachTo: document.body })
    const trigger = w.get('[data-testid="tooltip-trigger"]')
    expect(trigger.element.tagName).toBe('BUTTON')
    expect(trigger.attributes('type')).toBe('button')
    expect(trigger.element.tabIndex).toBe(0)
    expect(trigger.attributes('disabled')).toBeUndefined()
    await trigger.trigger('focus')
    expect(w.get('[data-testid="tooltip-text"]').text()).toBe('The most this strategy can lose.')
    expect(w.get('[role="tooltip"]').exists()).toBe(true)
    await trigger.trigger('keydown', { key: 'Escape' })
    expect(w.find('[data-testid="tooltip-text"]').exists()).toBe(false)
    await trigger.trigger('click')
    expect(w.find('[data-testid="tooltip-text"]').exists()).toBe(true)
    await trigger.trigger('click')
    expect(w.find('[data-testid="tooltip-text"]').exists()).toBe(false)
    w.unmount()
  })

  it('does not read the figure catalogue (REQ-136: only FigureHint.vue does)', () => {
    expect(readFileSync('src/components/common/Tooltip.vue', 'utf8')).not.toMatch(/figureDefinitions/)
  })
})

describe('tokens only (ADR-193 (2), UI-006)', () => {
  const HEX = /#[0-9a-fA-F]{3,6}\b/
  const files = [
    'src/App.vue',
    ...readdirSync('src/components/layout').map((f) => `src/components/layout/${f}`),
    ...readdirSync('src/components/common').map((f) => `src/components/common/${f}`),
    'src/components/states/EmptyState.vue',
  ].filter((f) => f.endsWith('.vue'))

  it('the scan covers the shell and every shared part', () => {
    for (const f of ['src/components/layout/AppHeader.vue', 'src/components/layout/AppLayout.vue', 'src/components/common/Drawer.vue', 'src/components/common/Tooltip.vue']) {
      expect(files).toContain(f)
    }
  })

  for (const f of files) {
    it(`${f} has no hard-coded hex colour`, () => {
      const src = readFileSync(f, 'utf8')
      const hit = src.split('\n').findIndex((line) => HEX.test(line))
      expect(hit, hit >= 0 ? `${f}:${hit + 1}: ${src.split('\n')[hit].trim()}` : '').toBe(-1)
    })
  }

  it('the detector fails on a planted hex colour (it is not blind)', () => {
    expect(HEX.test('<div class="bg-[#387ed1]">')).toBe(true)
    expect(HEX.test('color: #fff;')).toBe(true)
    expect(HEX.test('<div class="bg-accent">')).toBe(false)
  })

  it('every a.2 token is defined in style.css', () => {
    const css = readFileSync('src/style.css', 'utf8')
    for (const t of ['bg', 'surface', 'surface-muted', 'line', 'ink', 'ink-muted', 'ink-subtle', 'accent', 'accent-hover', 'accent-soft', 'profit', 'profit-soft', 'loss', 'loss-soft', 'warn', 'warn-soft', 'buy', 'buy-soft', 'sell', 'sell-soft', 'opt', 'opt-soft', 'oi-call', 'oi-put', 'estimate']) {
      expect(css, t).toMatch(new RegExp(`--color-${t}:\\s*#[0-9a-f]{6};`))
    }
    expect(css).toContain("--font-sans: 'Inter'")
  })
})
