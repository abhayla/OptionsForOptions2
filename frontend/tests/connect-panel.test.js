// REQ-015 AC-11 (RD-010, ADR-175): the Connect Zerodha panel carries the "is it safe" explainer, the no-extra-charges
// line and the account-opening link, which has ONE home (lib/connectHelp.js, configured, never typed).
import { describe, it, expect, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

let status = null
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: { get: () => Promise.resolve({ data: status }), post: () => Promise.resolve({ data: {} }) } }
})
import BrokerSettingsPage from '@/pages/BrokerSettingsPage.vue'
import { openAccountUrl } from '@/lib/connectHelp'

const OK = { state: 'connected', fix: null }
const DOWN = { state: 'disconnected', fix: 'connect_zerodha' }
const body = (s) => ({ account_connection: s, live_market_data: s, position_sync: s, order_execution: s, last_successful_sync: null, historical_data: 'not_available' })
async function open(s) {
  status = body(s)
  const w = mount(BrokerSettingsPage, { global: { stubs: { ErrorMessage: true } } })
  await flushPromises()
  return w
}
const LINK = 'https://example.test/open-account?partner=ABC123'

afterEach(() => vi.unstubAllEnvs())

describe('AC-11: the Connect Zerodha panel', () => {
  it('not connected: the explainer, the no-extra-charges line and the configured link, exactly', async () => {
    vi.stubEnv('VITE_ZERODHA_OPEN_ACCOUNT_URL', LINK)
    const w = await open(DOWN)
    expect(w.get('[data-testid="safe-title"]').text()).toBe('Is it safe to connect?')
    expect(w.get('[data-testid="safe-explainer"]').text()).toContain('never sees your Zerodha password, PIN or OTP')
    expect(w.get('[data-testid="no-extra-charges"]').text()).toContain('adds no charge from this app')
    const a = w.get('[data-testid="open-account"]')
    expect(a.attributes('href')).toBe(LINK)
    expect(a.attributes('rel')).toBe('noopener noreferrer')
    expect(a.text()).toBe('Don\'t have a Zerodha account? Open one')
  })

  it('connected: the panel is not shown', async () => {
    vi.stubEnv('VITE_ZERODHA_OPEN_ACCOUNT_URL', LINK)
    expect((await open(OK)).find('[data-testid="connect-help"]').exists()).toBe(false)
  })

  it.each([['absent', undefined], ['empty', ''], ['not a URL', 'open me'], ['http, not https', 'http://example.test/x'], ['javascript scheme', 'javascript:alert(1)']])(
    'link setting %s -> no link, the explainer still shows',
    async (_n, value) => {
      vi.stubEnv('VITE_ZERODHA_OPEN_ACCOUNT_URL', value)
      const w = await open(DOWN)
      expect(openAccountUrl(value)).toBeNull()
      expect(w.find('[data-testid="open-account"]').exists()).toBe(false)
      expect(w.find('[data-testid="safe-explainer"]').exists()).toBe(true)
    },
  )

  it('no advice wording in the panel (ADR-003)', async () => {
    const text = (await open(DOWN)).get('[data-testid="connect-help"]').text()
    expect(text).not.toMatch(/you should|best trade|guaranteed|recommend/i)
  })
})

describe('AC-11: the link has one home', () => {
  const walk = (d) => readdirSync(d).flatMap((f) => (statSync(join(d, f)).isDirectory() ? walk(join(d, f)) : [join(d, f)]))
  const src = walk(resolve(__dirname, '../src')).filter((f) => /\.(vue|js)$/.test(f))
  it('only lib/connectHelp.js names the setting or an account-opening address', () => {
    const hits = src.filter((f) => /VITE_ZERODHA_OPEN_ACCOUNT_URL|open-account|partner=/i.test(readFileSync(f, 'utf8')) && !/connectHelp\.js$/.test(f))
    // the page uses data-testid="open-account" only; that is not an address
    const real = hits.filter((f) => /VITE_ZERODHA_OPEN_ACCOUNT_URL|partner=|https?:\/\/[^'"\s]*open-account/i.test(readFileSync(f, 'utf8')))
    expect(real).toEqual([])
  })
})
