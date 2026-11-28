// Lane FJ r3 (28 Nov 2026), PC round 1 O-A-08: the menu's "Settings" link opens /settings/app-settings, but typing /settings landed on
// "Subscription & Billing" (the first built item of the account list). /settings now lands on the same page the Settings link opens.
import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { routes } from '@/router/routes.js'
import { ACCOUNT_MENU_ITEMS } from '@/router/nav'

const at = async (path) => {
  const r = createRouter({ history: createMemoryHistory(), routes })
  await r.push(path)
  return r.currentRoute.value
}

describe('/settings lands where the Settings link lands', () => {
  it('the menu has a "Settings" item whose page is app-settings', () => {
    expect(ACCOUNT_MENU_ITEMS.find(([, label]) => label === 'Settings')?.[0]).toBe('app-settings')
  })
  it('/settings resolves to /settings/app-settings', async () => {
    expect((await at('/settings')).fullPath).toBe('/settings/app-settings')
  })
  it('the other settings pages and section redirects are unchanged', async () => {
    expect((await at('/settings/subscription-billing')).fullPath).toBe('/settings/subscription-billing')
    expect((await at('/settings/app-settings')).fullPath).toBe('/settings/app-settings')
    expect((await at('/strategies')).fullPath).not.toBe('/strategies')
  })
})
