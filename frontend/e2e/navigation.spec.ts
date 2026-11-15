// REQ-009 AC-1..AC-8. The strings below are copied from spec/requirements/REQ-009.md, not from the app.
import { test, expect } from '@playwright/test'
import { NavPage } from './pages/nav.page'

const SECTIONS: Record<string, { label: string; items: string[] }> = {
  'AC-1': { label: 'Home', items: ['Overview'] },
  'AC-2': {
    label: 'Strategies',
    items: ['My Strategies', 'Create Strategy', 'Strategy Builder', 'Live Strategies', 'Adjustments', 'Completed Strategies'],
  },
  'AC-3': {
    label: 'Positions',
    items: ['Current positions', 'Strategy-linked positions', 'Adjustment opportunities'],
  },
  'AC-4': { label: 'Market', items: ['Option Chain', 'Underlying/index view', 'Market context'] },
  'AC-6': { label: 'Alerts', items: ['Active', 'History', 'Notification settings'] },
  'AC-7': { label: 'Learn', items: ['Strategy education', 'Options concepts', 'Platform guidance'] },
}

// ADR-313 (u504): the menus list built pages only (nav.js UNBUILT_ITEMS). Orders has no built page, so it is not in the bar; the
// unbuilt items below still open by address (AC-5 test). EDITED WITHOUT RUNNING (needs the e2e stack): the menu checks open each
// section's menu button and read its items; a section link opens the section's first built page, not a section page.
const SECTION_ORDER = ['Home', 'Strategies', 'Positions', 'Market', 'Alerts', 'Learn']

const ACCOUNT_ITEMS = [
  'Subscription & Billing',
  'Free Eligibility',
  'Referrals',
  'Broker & Market Data',
  'Settings', // GC-SET (REQ-167), nav.js app-settings
]

test('the built sections are the primary nav, in order (REQ-009 statement; Orders is not built, ADR-313)', async ({ page }) => {
  await page.goto('/')
  const nav = new NavPage(page)
  await expect(nav.navLinks).toHaveText(SECTION_ORDER)
})

test('"/" opens My Strategies, a built page (ADR-313 (3))', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveURL(/\/strategies\/my-strategies$/)
  await expect(new NavPage(page).title).toHaveText('My Strategies')
})

for (const [ac, { label, items }] of Object.entries(SECTIONS)) {
  test(`${ac}: ${label} menu lists ${items.join(', ')}`, async ({ page }) => {
    await page.goto('/')
    const nav = new NavPage(page)
    const toggle = page.getByTestId(`nav-menu-toggle-${label.toLowerCase()}`)
    const titles = page.getByTestId('nav-menu-item').locator('span.font-medium')
    await toggle.click()
    expect([...(await titles.allTextContents())].sort()).toEqual([...items].sort())
    // each menu item opens its own page titled with the exact label
    for (const item of items) {
      await page.getByTestId('nav-menu-item').filter({ has: page.getByText(item, { exact: true }) }).click()
      await expect(nav.title).toHaveText(item)
      await toggle.click()
    }
  })
}

test('AC-5: Orders offers strategy-linked orders only, never an order-entry form', async ({ page }) => {
  await page.goto('/orders')
  const nav = new NavPage(page)
  const slugs = ['', '/pending', '/executed', '/failed-partial', '/execution-history']
  for (const slug of slugs) {
    await page.goto(`/orders${slug}`)
    await expect(nav.title).toBeVisible()
    const content = page.getByTestId('app-content')
    await expect(content.locator('form, input, select, textarea')).toHaveCount(0)
    await expect(content.getByRole('button')).toHaveCount(0)
    await expect(content.getByText(/place order|buy|sell/i)).toHaveCount(0)
  }
  await page.goto('/orders')
  await expect(page.getByTestId('page-note')).toContainText('Strategy-linked orders only')
  // no route exists for an order-entry page: it falls to the catch-all
  for (const entry of ['/orders/new', '/orders/place', '/orders/entry']) {
    await page.goto(entry)
    await expect(page.getByTestId('not-found')).toBeVisible()
  }
})

test('AC-8: the avatar menu opens Account & Settings with its built items', async ({ page }) => {
  await page.goto('/')
  const nav = new NavPage(page)
  await nav.openAccountMenu()
  await expect(page.getByTestId('account-menu-title')).toHaveText('Account & Settings')
  await expect(nav.accountMenuItems).toHaveText(ACCOUNT_ITEMS)
  for (const item of ACCOUNT_ITEMS) {
    await nav.accountMenuItems.filter({ hasText: new RegExp(`^${item.replace(/&/g, '\\&')}$`) }).click()
    await expect(nav.title).toHaveText(item)
    await nav.openAccountMenu()
  }
})

test('every nav link, menu item and account link resolves to a real page (fail closed)', async ({ page }) => {
  await page.goto('/')
  const nav = new NavPage(page)
  const hrefs = new Set<string>()
  for (const href of await nav.navLinks.evaluateAll((els) => els.map((e) => e.getAttribute('href') as string))) hrefs.add(href)
  // menu items: open each section's menu (a section link opens its first item, so it adds no new address)
  for (const label of SECTION_ORDER) {
    const toggle = page.getByTestId(`nav-menu-toggle-${label.toLowerCase()}`)
    await toggle.click()
    for (const href of await page.getByTestId('nav-menu-item').evaluateAll((els) => els.map((e) => e.getAttribute('href') as string))) hrefs.add(href)
    await toggle.click()
  }
  await nav.openAccountMenu()
  for (const href of await page
    .getByTestId('account-menu')
    .getByRole('link')
    .evaluateAll((els) => els.map((e) => e.getAttribute('href') as string)))
    hrefs.add(href)
  // every built menu item + /settings (the account title link) + its built items; section links equal their first item
  const subItemCount = Object.values(SECTIONS).reduce((n, s) => n + s.items.length, 0)
  expect(hrefs.size).toBe(subItemCount + 1 + ACCOUNT_ITEMS.length)
  for (const href of hrefs) {
    await page.goto(href)
    await expect(nav.title, href).toBeVisible()
    await expect(page.getByTestId('not-found'), href).toHaveCount(0)
  }
})

test('an unknown route shows the catch-all page', async ({ page }) => {
  await page.goto('/no-such-page')
  await expect(page.getByTestId('not-found')).toBeVisible()
})

test('shell screenshots', async ({ page }, info) => {
  await page.goto('/strategies')
  await page.screenshot({ path: `screenshots/strategies-${info.project.name}.png`, fullPage: true })
  await new NavPage(page).openAccountMenu()
  await page.screenshot({ path: `screenshots/account-menu-${info.project.name}.png` })
})
