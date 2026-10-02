// REQ-009 AC-1..AC-8. The strings below are copied from spec/requirements/REQ-009.md, not from the app.
import { test, expect } from '@playwright/test'
import { NavPage } from './pages/nav.page'

const SECTIONS: Record<string, { label: string; items: string[] }> = {
  'AC-1': { label: 'Home', items: ['Overview', 'Important alerts', 'Active strategies', 'Account status'] },
  'AC-2': {
    label: 'Strategies',
    items: ['My Strategies', 'Create Strategy', 'Strategy Builder', 'Live Strategies', 'Adjustments', 'Completed Strategies'],
  },
  'AC-3': {
    label: 'Positions',
    items: ['Current positions', 'Strategy-linked positions', 'Adjustment opportunities', 'P&L/risk'],
  },
  'AC-4': { label: 'Market', items: ['Option Chain', 'Underlying/index view', 'Market context'] },
  'AC-5': { label: 'Orders', items: ['Pending', 'Executed', 'Failed/partial', 'Execution history'] },
  'AC-6': { label: 'Alerts', items: ['Active', 'History', 'Notification settings'] },
  'AC-7': { label: 'Learn', items: ['Strategy education', 'Options concepts', 'Platform guidance'] },
}

const SECTION_ORDER = ['Home', 'Strategies', 'Positions', 'Market', 'Orders', 'Alerts', 'Learn']

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

test('the seven sections are the primary nav, in order (REQ-009 statement)', async ({ page }) => {
  await page.goto('/')
  const nav = new NavPage(page)
  await expect(nav.navLinks).toHaveText(SECTION_ORDER)
})

for (const [ac, { label, items }] of Object.entries(SECTIONS)) {
  test(`${ac}: ${label} lists ${items.join(', ')}`, async ({ page }) => {
    await page.goto('/')
    const nav = new NavPage(page)
    await nav.openSection(label)
    await expect(nav.title).toHaveText(label)
    await expect(nav.subItems).toHaveText(items)
    // each sub-item resolves to its own page titled with the exact label
    for (const item of items) {
      await nav.subItems.filter({ hasText: new RegExp(`^${item.replace(/[/&]/g, '\\$&')}$`) }).click()
      await expect(nav.title).toHaveText(item)
      await nav.openSection(label)
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

test('AC-8: the avatar menu opens Account & Settings with its ten items', async ({ page }) => {
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

test('every nav link, sub-item link and account link resolves to a real page (fail closed)', async ({ page }) => {
  await page.goto('/')
  const nav = new NavPage(page)
  const hrefs = new Set<string>()
  for (const href of await nav.navLinks.evaluateAll((els) => els.map((e) => e.getAttribute('href') as string))) hrefs.add(href)
  await nav.openAccountMenu()
  for (const href of await page
    .getByTestId('account-menu')
    .getByRole('link')
    .evaluateAll((els) => els.map((e) => e.getAttribute('href') as string)))
    hrefs.add(href)
  // sub-item links from each section page
  for (const section of [...hrefs].filter((h) => SECTION_ORDER.map((s) => `/${s.toLowerCase()}`).includes(h) || h === '/settings')) {
    await page.goto(section)
    for (const href of await nav.subItems.evaluateAll((els) => els.map((e) => e.getAttribute('href') as string))) hrefs.add(href)
  }
  // 7 sections + every sub-item + /settings + its ten items, derived from the spec strings above
  const subItemCount = Object.values(SECTIONS).reduce((n, s) => n + s.items.length, 0)
  expect(hrefs.size).toBe(SECTION_ORDER.length + subItemCount + 1 + ACCOUNT_ITEMS.length)
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
