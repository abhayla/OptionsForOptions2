// GC-6 BILLING-SHELL (ADR-146): the three in-app billing pages show exactly the approved texts and nothing to act on.
import { describe, it, expect } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { readFileSync } from 'node:fs'
import { routes } from '@/router/routes'
import { ACCOUNT_ITEMS } from '@/router/nav'
import { PRICING_TEXT } from '@/lib/landingText'

const PAGES = [
  ['/settings/subscription-billing', 'Subscription & Billing', ['Plan: Free during early access', PRICING_TEXT]],
  ['/settings/free-eligibility', 'Free Eligibility', ['Not available yet. We will announce it before it starts.']],
  ['/settings/referrals', 'Referrals', ['Not available yet. We will announce it before it starts.']],
]

async function open(path) {
  const router = createRouter({ history: createMemoryHistory(), routes })
  router.push(path)
  await router.isReady()
  const App = { template: '<router-view />' }
  const w = mount(App, { global: { plugins: [router] } })
  await flushPromises()
  await new Promise((r) => setTimeout(r, 0))
  await flushPromises()
  return w
}

describe('ADR-146 billing pages', () => {
  for (const [path, title, lines] of PAGES) {
    describe(path, () => {
      it('shows the title and exactly the approved lines, in order', async () => {
        const w = await open(path)
        expect(w.get('[data-testid="page-title"]').text()).toBe(title)
        expect(w.findAll('[data-testid="billing-line"]').map((p) => p.text())).toEqual(lines)
      })
      it('has no Subscribe, Apply or Invite control and no button at all', async () => {
        const w = await open(path)
        expect(w.findAll('button, a, input, [role="button"]')).toHaveLength(0)
        expect(w.text()).not.toMatch(/subscribe|apply|invite/i)
      })
      it('shows no trial or day countdown', async () => {
        const w = await open(path)
        expect(w.text()).not.toMatch(/trial|days? (left|remaining)|\d+\s*days?|countdown/i)
      })
    })
  }

  it('the three pages stay in the Account menu (REQ-009 AC-8)', () => {
    const slugs = ACCOUNT_ITEMS.map(([s]) => s)
    for (const s of ['subscription-billing', 'free-eligibility', 'referrals']) expect(slugs).toContain(s)
  })

  it('390 px class check: no fixed pixel widths, no nowrap', () => {
    const src = readFileSync('src/pages/BillingShellPage.vue', 'utf8')
    expect(src).not.toMatch(/\b(?:min-|max-)?w-\[\d+px\]|\bw-\d{2,}\b|width:\s*\d+px|whitespace-nowrap/)
  })
})
