// W-191 (ADR-193, UI study a.1 UI-001..UI-004) over REQ-009 AC-1..AC-8: the restyled top bar still lists the seven
// sections and every item in the spec's words, opens them as menus, and the account menu keeps its ten items.
// Expected strings are typed here from spec/requirements/REQ-009.md, never read from nav.js.
import { describe, expect, it, vi, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { routes } from '@/router/routes'
import AppHeader from '@/components/layout/AppHeader.vue'
import AppLayout from '@/components/layout/AppLayout.vue'

const SECTIONS = {
  home: ['Home', ['Overview', 'Important alerts', 'Active strategies', 'Account status']],
  strategies: ['Strategies', ['My Strategies', 'Create Strategy', 'Strategy Builder', 'Live Strategies', 'Adjustments', 'Completed Strategies']],
  positions: ['Positions', ['Current positions', 'Strategy-linked positions', 'Adjustment opportunities', 'P&L/risk']],
  market: ['Market', ['Option Chain', 'Underlying/index view', 'Market context']],
  orders: ['Orders', ['Pending', 'Executed', 'Failed/partial', 'Execution history']],
  alerts: ['Alerts', ['Active', 'History', 'Notification settings']],
  learn: ['Learn', ['Strategy education', 'Options concepts', 'Platform guidance']],
}
const ACCOUNT_ITEMS = [
  'Profile',
  'Zerodha connection',
  'Subscription & Billing',
  'Free Eligibility',
  'Referrals',
  'Notifications',
  'Security',
  'Preferences',
  'Strategy Preferences',
  'Broker & Market Data',
]

async function mountAt(url, component = AppHeader) {
  const router = createRouter({ history: createMemoryHistory(), routes })
  router.push(url)
  await router.isReady()
  const w = mount(component, { global: { plugins: [router] }, attachTo: document.body })
  await flushPromises()
  return { w, router }
}
const texts = (w, sel) => w.findAll(sel).map((e) => e.text().replace(/\s+/g, ' ').trim())
const itemTitles = (w) => w.findAll('[data-testid="nav-menu-item"]').map((e) => e.find('span.block').text())

afterEach(() => {
  vi.useRealTimers()
  document.body.innerHTML = ''
})

describe('top bar sections (REQ-009 statement, AC-1..AC-7)', () => {
  it('the primary nav holds exactly the seven section links, in order, each to its section page', async () => {
    const { w } = await mountAt('/home')
    const links = w.get('[data-testid="primary-nav"]').findAll('a')
    expect(links.map((a) => a.text())).toEqual(Object.values(SECTIONS).map(([label]) => label))
    expect(links.map((a) => a.attributes('href'))).toEqual(Object.keys(SECTIONS).map((k) => `/${k}`))
    w.unmount()
  })

  for (const [key, [label, items]] of Object.entries(SECTIONS)) {
    it(`${label}: its menu lists ${items.join(', ')} in the spec's words, each to its own page`, async () => {
      const { w } = await mountAt('/home')
      await w.get(`[data-testid="nav-menu-toggle-${key}"]`).trigger('click')
      const menu = w.get('[data-testid="nav-menu"]')
      expect(menu.attributes('data-section')).toBe(key)
      expect(menu.attributes('role')).toBe('menu')
      const titles = itemTitles(w)
      expect([...titles].sort()).toEqual([...items].sort())
      if (key !== 'strategies') expect(titles).toEqual(items) // REQ-009 order; Strategies is grouped Build/Follow/Done
      for (const a of w.findAll('[data-testid="nav-menu-item"]')) {
        const label2 = a.find('span.block').text()
        const slug = Object.fromEntries((await import('@/router/nav')).SECTIONS.find((s) => s.key === key).items.map(([s, l]) => [l, s]))[label2]
        expect(a.attributes('href')).toBe(`/${key}/${slug}`)
      }
      w.unmount()
    })
  }

  it('Strategies opens a three-column mega menu (Build / Follow / Done) with one-line descriptions', async () => {
    const { w } = await mountAt('/home')
    await w.get('[data-testid="nav-menu-toggle-strategies"]').trigger('click')
    const menu = w.get('[data-testid="nav-menu"]')
    expect(menu.classes()).toContain('inset-x-0')
    expect(menu.text()).toContain('Build')
    expect(menu.text()).toContain('Follow')
    expect(menu.text()).toContain('Done')
    expect(menu.text()).toContain('Build a strategy from legs or ready-made shapes and see every outcome')
    w.unmount()
  })

  it('clicking a menu item opens its page and closes the menu', async () => {
    const { w, router } = await mountAt('/home')
    await w.get('[data-testid="nav-menu-toggle-market"]').trigger('click')
    await w.findAll('[data-testid="nav-menu-item"]')[0].trigger('click')
    // the page component is a lazy import, so the navigation settles after it loads
    await vi.waitFor(() => expect(router.currentRoute.value.fullPath).toBe('/market/option-chain'), { timeout: 3000 })
    await flushPromises()
    expect(w.find('[data-testid="nav-menu"]').exists()).toBe(false)
    w.unmount()
  })
})

describe('menu focus and aria-current (review round 2)', () => {
  it('an open menu closes when focus moves to another section control, but not into its own items', async () => {
    const { w } = await mountAt('/home')
    const toggle = w.get('[data-testid="nav-menu-toggle-orders"]')
    await toggle.trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="nav-menu"]').exists()).toBe(true)
    const item = w.get('[data-testid="nav-menu-item"]').element
    await toggle.trigger('focusout', { relatedTarget: item })
    expect(w.find('[data-testid="nav-menu"]').exists()).toBe(true)
    await toggle.trigger('focusout', { relatedTarget: w.get('[data-testid="nav-alerts"]').element })
    await flushPromises()
    expect(w.find('[data-testid="nav-menu"]').exists()).toBe(false)
    w.unmount()
  })

  it('links carry aria-current="page" only on their own page; never "true"', async () => {
    const { w } = await mountAt('/home')
    expect(w.get('[data-testid="nav-home"]').attributes('aria-current')).toBe('page')
    expect(w.get('[data-testid="nav-orders"]').attributes('aria-current')).toBeUndefined()
    w.unmount()
    const again = await mountAt('/strategies/my-strategies')
    expect(again.w.get('[data-testid="nav-strategies"]').attributes('aria-current')).not.toBe('true')
    again.w.unmount()
  })
})

describe('menu keyboard and hover (UI-002)', () => {
  it('ArrowDown on the menu button opens it and focuses the first item; arrows move; Esc closes and returns focus', async () => {
    const { w } = await mountAt('/home')
    const toggle = w.get('[data-testid="nav-menu-toggle-orders"]')
    expect(toggle.element.tagName).toBe('BUTTON')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    toggle.element.focus()
    await toggle.trigger('keydown', { key: 'ArrowDown' })
    await flushPromises()
    const items = w.findAll('[data-testid="nav-menu-item"]')
    expect(toggle.attributes('aria-expanded')).toBe('true')
    expect(document.activeElement).toBe(items[0].element)
    await w.get('[data-testid="nav-menu"]').trigger('keydown', { key: 'ArrowDown' })
    await flushPromises()
    expect(document.activeElement).toBe(items[1].element)
    await w.get('[data-testid="nav-menu"]').trigger('keydown', { key: 'ArrowUp' })
    await flushPromises()
    expect(document.activeElement).toBe(items[0].element)
    await w.get('[data-testid="nav-menu"]').trigger('keydown', { key: 'Escape' })
    await flushPromises()
    expect(w.find('[data-testid="nav-menu"]').exists()).toBe(false)
    expect(document.activeElement).toBe(toggle.element)
    w.unmount()
  })

  it('a mouse hover opens the menu after 150 ms; a touch pointer never hover-opens', async () => {
    vi.useFakeTimers()
    const { w } = await mountAt('/home')
    const li = w.get('[data-testid="nav-learn"]').element.parentElement
    li.dispatchEvent(Object.assign(new Event('pointerenter'), { pointerType: 'touch' }))
    vi.advanceTimersByTime(300)
    await flushPromises()
    expect(w.find('[data-testid="nav-menu"]').exists()).toBe(false)
    li.dispatchEvent(Object.assign(new Event('pointerenter'), { pointerType: 'mouse' }))
    vi.advanceTimersByTime(100)
    await flushPromises()
    expect(w.find('[data-testid="nav-menu"]').exists()).toBe(false)
    vi.advanceTimersByTime(60)
    await flushPromises()
    expect(w.get('[data-testid="nav-menu"]').attributes('data-section')).toBe('learn')
    // the click that follows a hover-open keeps the menu open; a second click closes it
    await w.get('[data-testid="nav-menu-toggle-learn"]').trigger('click')
    expect(w.find('[data-testid="nav-menu"]').exists()).toBe(true)
    await w.get('[data-testid="nav-menu-toggle-learn"]').trigger('click')
    expect(w.find('[data-testid="nav-menu"]').exists()).toBe(false)
    w.unmount()
  })
})

describe('active section, breadcrumb and page width (UI-001, UI-004)', () => {
  it('the active section is marked with accent text and the 3 px bar; the breadcrumb shows the page title', async () => {
    const { w } = await mountAt('/market/option-chain')
    const link = w.get('[data-testid="nav-market"]')
    expect(link.classes()).toContain('text-accent')
    expect(link.attributes('aria-current')).toBeUndefined() // the section link is not the current page (review round 2)
    expect(w.findAll('[data-testid="nav-active-bar"]')).toHaveLength(1)
    expect(w.get('[data-testid="nav-active-bar"]').classes()).toContain('h-[3px]')
    expect(w.get('[data-testid="breadcrumb-title"]').text()).toBe('Option Chain')
    w.unmount()
  })

  it('builder and option chain are full width; every other page is the centred 1200 px column', async () => {
    for (const [url, width] of [
      ['/strategies/strategy-builder', 'full'],
      ['/strategy/builder', 'full'],
      ['/market/option-chain', 'full'],
      ['/home/overview', 'column'],
      ['/positions', 'column'],
      ['/settings/profile', 'column'],
    ]) {
      const { w } = await mountAt(url, AppLayout)
      expect(w.get('[data-testid="app-content"]').attributes('data-width'), url).toBe(width)
      w.unmount()
    }
  })
})

describe('avatar menu (REQ-009 AC-8, UI-003)', () => {
  it('opens Account & Settings with its ten items in order, then Log out', async () => {
    const { w } = await mountAt('/home')
    await w.get('[data-testid="avatar-menu"]').trigger('click')
    expect(w.get('[data-testid="account-menu-title"]').text()).toBe('Account & Settings')
    expect(texts(w, '[data-testid="account-menu-item"]')).toEqual(ACCOUNT_ITEMS)
    const logout = w.get('[data-testid="account-logout"]')
    expect(logout.text()).toBe('Log out')
    expect(logout.attributes('title')).toBeTruthy() // a disabled action says why
    w.unmount()
  })
})
