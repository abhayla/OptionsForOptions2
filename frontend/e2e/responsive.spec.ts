// REQ-004 AC-1: "Every screen works at desktop and phone widths from the first release."
// The route list is read from the router's own route table (src/router/routes.js), so a route added later is checked at
// both widths (the 390 and 1280 projects in playwright.config.js) without editing this file. Fail closed: a route with
// a parameter and no sample value, or an empty route list, is an error, never a silent skip.
import { test, expect } from '@playwright/test'
import fs from 'node:fs'
import { findClippedElements, describeClipped, SCROLLER_ATTR } from './clipping-check'
// @ts-expect-error plain JS module, no type declarations
import { routes } from '../src/router/routes.js'
// @ts-expect-error plain JS module, no type declarations
import { SECTIONS, ACCOUNT_ITEMS } from '../src/router/nav.js'

type RouteRecord = { path: string; redirect?: unknown; meta?: { responsiveSample?: string } }

function visitPaths(): string[] {
  const paths: string[] = []
  for (const r of routes as RouteRecord[]) {
    if (r.redirect) continue // '/' only redirects; its target is its own route
    if (r.path.includes(':')) {
      if (r.path === '/:pathMatch(.*)*') {
        paths.push('/this-address-does-not-exist') // the not-found page
        continue
      }
      const sample = r.meta?.responsiveSample
      if (!sample) throw new Error(`route ${r.path} has a parameter and no meta.responsiveSample: the responsive check cannot visit it`)
      paths.push(sample)
      continue
    }
    paths.push(r.path)
  }
  if (paths.length === 0) throw new Error('the router returned no routes to check')
  return paths
}

const PATHS = visitPaths()

test('the route list covers every nav.js section, sub-item, account item, /settings, /health-status and not-found', () => {
  const expected = new Set<string>(['/settings', '/health-status', '/this-address-does-not-exist'])
  for (const s of SECTIONS) {
    expected.add(`/${s.key}`)
    for (const [slug] of s.items) expected.add(`/${s.key}/${slug}`)
  }
  for (const [slug] of ACCOUNT_ITEMS) expected.add(`/settings/${slug}`)
  for (const p of expected) expect(PATHS, `route ${p} is not in the checked list`).toContain(p)
  expect(PATHS.length).toBeGreaterThanOrEqual(expected.size)
})

for (const path of PATHS) {
  test(`responsive: ${path}`, async ({ page }, info) => {
    const width = page.viewportSize()!.width
    const where = `route ${path} at ${width}px`
    await page.goto(path)
    await expect(page.getByTestId('page-title'), `${where}: page title not visible`).toBeVisible()

    // no horizontal page scroll
    const m = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, inner: window.innerWidth }))
    expect(m.scroll, `${where}: horizontal page scroll (scrollWidth ${m.scroll} > innerWidth ${m.inner})`).toBeLessThanOrEqual(m.inner)

    // clipped content: overflow:hidden keeps scrollWidth small, so measure the boxes (issue #110)
    const clipped = await findClippedElements(page)
    expect(clipped, describeClipped(path, width, clipped)).toEqual([])

    // primary navigation visible and every link reachable within the viewport (the strip may scroll inside itself)
    const nav = page.getByTestId('primary-nav')
    await expect(nav, `${where}: primary navigation not visible`).toBeVisible()
    const links = nav.getByRole('link')
    const count = await links.count()
    expect(count, `${where}: primary navigation has no links`).toBe(SECTIONS.length)
    for (let i = 0; i < count; i++) {
      await links.nth(i).scrollIntoViewIfNeeded()
      const box = await links.nth(i).boundingBox()
      expect(box, `${where}: nav link ${i} has no box`).not.toBeNull()
      expect(box!.x >= 0 && box!.x + box!.width <= width, `${where}: nav link ${i} is clipped outside the viewport`).toBe(true)
    }
    // the account button stays on screen
    const avatar = await page.getByTestId('avatar-menu').boundingBox()
    expect(avatar, `${where}: account button missing`).not.toBeNull()
    expect(avatar!.x + avatar!.width, `${where}: account button pushed off screen`).toBeLessThanOrEqual(width)

    const after = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
    expect(after, `${where}: horizontal page scroll after scrolling the navigation`).toBe(true)

    fs.mkdirSync('test-results/responsive', { recursive: true })
    const name = path.replace(/^\//, '').replace(/\//g, '__') || 'root'
    await page.screenshot({ path: `test-results/responsive/${name}-${info.project.name}.png`, fullPage: true })
  })
}

// Proof for issue #110: an over-wide table clipped by overflow:hidden passes the page-scroll check but must fail the
// clipping check naming route and width; the same table inside a marked scroller must pass.
const WIDE_TABLE = `<div id="fx" style="overflow:hidden"><table style="width:900px"><tr><td>wide</td></tr></table></div>`

test('clipped over-wide table is caught, naming route and width; a marked scroller passes', async ({ page }) => {
  const width = page.viewportSize()!.width
  await page.goto('/home')
  expect(await findClippedElements(page), 'baseline route must be clean').toEqual([])

  await page.evaluate((html) => document.querySelector('[data-testid="app-content"]')!.insertAdjacentHTML('beforeend', html), WIDE_TABLE)
  const pageScrollOk = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
  expect(pageScrollOk, 'the old page-scroll check is blind to this fixture').toBe(true)
  const bad = await findClippedElements(page)
  if (width < 900) {
    expect(bad.length, 'clipped table not detected').toBeGreaterThan(0)
    const msg = describeClipped('/home', width, bad)
    expect(msg).toContain('route /home')
    expect(msg).toContain(`at ${width}px`)
    expect(msg).toContain('table')
  }

  await page.evaluate((a) => document.querySelector('#fx')!.setAttribute(a, ''), SCROLLER_ATTR)
  // the marker alone is not trusted: a marked overflow:hidden element hides content, it does not scroll it
  const markedHidden = await findClippedElements(page)
  expect(markedHidden.length, 'marked overflow:hidden element must still fail').toBeGreaterThan(0)
  expect(describeClipped('/home', width, markedHidden)).toContain(`at ${width}px`)

  // a marked element whose computed overflow-x is auto scrolls on purpose: its wide table is allowed
  await page.evaluate(() => ((document.querySelector('#fx') as HTMLElement).style.overflowX = 'auto'))
  const still = await findClippedElements(page)
  expect(still, 'marked overflow-x:auto scroller must pass').toEqual([])
})

test('account menu fits the viewport and does not cause horizontal scroll', async ({ page }) => {
  const width = page.viewportSize()!.width
  await page.goto('/home')
  await page.getByTestId('avatar-menu').click()
  const menu = page.getByTestId('account-menu')
  await expect(menu).toBeVisible()
  const box = (await menu.boundingBox())!
  expect(box.x, `account menu at ${width}px starts off screen`).toBeGreaterThanOrEqual(0)
  expect(box.x + box.width, `account menu at ${width}px ends off screen`).toBeLessThanOrEqual(width)
  const ok = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
  expect(ok, `account menu at ${width}px causes horizontal scroll`).toBe(true)
})

test('account menu: aria wiring, closes on Escape and on a click outside', async ({ page }) => {
  await page.goto('/home')
  const button = page.getByTestId('avatar-menu')
  const menu = page.getByTestId('account-menu')
  await expect(button).toHaveAttribute('aria-expanded', 'false')
  const controls = await button.getAttribute('aria-controls')
  expect(controls).toBeTruthy()

  await button.click()
  await expect(menu).toBeVisible()
  await expect(button).toHaveAttribute('aria-expanded', 'true')
  await expect(menu).toHaveAttribute('id', controls!)

  await page.keyboard.press('Escape')
  await expect(menu).toHaveCount(0)
  await expect(button).toBeFocused()
  await expect(button).toHaveAttribute('aria-expanded', 'false')

  await button.click()
  await expect(menu).toBeVisible()
  await page.mouse.click(5, page.viewportSize()!.height - 5) // bottom-left corner, outside the menu
  await expect(menu).toHaveCount(0)
  await expect(button).toHaveAttribute('aria-expanded', 'false')
})
