// GC-SET step 2 (REQ-167 AC-2, AC-5): the Settings page. Answers have the shapes of GET /api/settings and the write
// routes (tests_app/test_settings_route.py); every sentence asserted is the answer's own text or this page's fixed words.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { mapError } from '@/services/api'
import { ACCOUNT_ITEMS } from '@/router/nav.js'

const answers = {}
const calls = []
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const reply = (method) => (url, payload) => {
    calls.push([method, url, payload])
    const a = answers[`${method} ${url}`]
    if (a instanceof Error || a?.reason || a?.parts) return Promise.reject(a)
    return a ? Promise.resolve({ data: typeof a === 'function' ? a(payload) : a }) : Promise.reject({ message: 'no answer', status: 404 })
  }
  return { ...actual, default: { get: reply('GET'), post: reply('POST') } }
})
import SettingsPage from '@/pages/SettingsPage.vue'

const KEY = 'pricing.risk_free_rate'
const setting = (over = {}) => ({
  key: KEY, group: 'Pricing', label: 'Risk-free interest rate', unit: 'fraction', type: 'decimal', min: '0', max: '0.5',
  what_it_changes: 'The yearly interest rate used in option prices.', default: '0.065', value: '0.065', is_default: true,
  effective_from: null, set_by: null, earlier_values: [], ...over,
})
const page = (s = setting(), charges = null) => ({ groups: [{ name: 'Pricing', settings: [s] }], charges })
const CHARGES = { name: 'Charges', read_on: '2026-10-15', source_url: 'https://zerodha.com/charges',
  rates: { brokerage_per_order: '20', stt_sell_rate: '0.001', stt_exercise_rate: '0.00125', transaction_rate_nse_fo: '0.0003503',
    transaction_rate_bse_fo: '0.0000325', sebi_rate: '0.000001', stamp_buy_rate: '0.00003', gst_rate: '0.18' } }

async function open(body = page()) {
  answers['GET /settings'] = body
  const w = mount(SettingsPage)
  await flushPromises()
  return w
}

beforeEach(() => {
  for (const k of Object.keys(answers)) delete answers[k]
  calls.length = 0
})

describe('Settings page', () => {
  it('is reachable from the nav as "Settings" under Account & Settings', () => {
    expect(ACCOUNT_ITEMS).toContainEqual(['app-settings', 'Settings'])
  })

  it('shows value in force, default, unit, who set it and what it changes, decimals exactly as sent', async () => {
    const w = await open(page(setting({ value: '0.0700', is_default: false, set_by: 'owner', effective_from: '2026-11-01T10:00:00+05:30' })))
    const row = w.find(`[data-testid="setting-${KEY}"]`)
    expect(row.find('[data-testid="setting-value"]').text()).toBe('0.0700') // no float formatting
    expect(row.find('[data-testid="setting-default"]').text()).toBe('0.065')
    expect(row.text()).toContain('Risk-free interest rate')
    expect(row.text()).toContain('owner')
    expect(row.text()).toContain('The yearly interest rate used in option prices.')
    expect(w.find('[data-testid="settings-group-Pricing"]').exists()).toBe(true)
  })

  it('shows "Default" as the since-time when no row is stored', async () => {
    const w = await open()
    expect(w.find(`[data-testid="setting-${KEY}"]`).text()).toContain('Default')
  })

  it('saves a change: the value goes as the typed string and the row shows the answer', async () => {
    answers[`POST /settings/${KEY}`] = setting({ value: '0.07', is_default: false, set_by: 'owner', effective_from: '2026-11-01T10:00:00+05:30',
      earlier_values: [{ value: '0.07', effective_from: '2026-11-01T10:00:00+05:30', set_by: 'owner', state: 'in_force' }] })
    const w = await open()
    await w.find(`[data-testid="edit-${KEY}"]`).trigger('click')
    await w.find('[data-testid="input-value"]').setValue('0.07')
    await w.find('[data-testid="input-note"]').setValue('RBI move')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(calls.find((c) => c[0] === 'POST')).toEqual(['POST', `/settings/${KEY}`, { value: '0.07', note: 'RBI move' }])
    expect(w.find('[data-testid="setting-value"]').text()).toBe('0.07')
    expect(w.find(`[data-testid="earlier-values-${KEY}"]`).text()).toContain('In force')
  })

  it('shows the server refusal reason inline and keeps the value in force', async () => {
    answers[`POST /settings/${KEY}`] = { message: 'x', status: 422, reason: 'Risk-free interest rate is a fraction. Enter 0.065 for 6.5%.' }
    const w = await open()
    await w.find(`[data-testid="edit-${KEY}"]`).trigger('click')
    await w.find('[data-testid="input-value"]').setValue('6.5')
    await w.find('[data-testid="input-note"]').setValue('typo')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(w.find('[data-testid="refusal"]').text()).toContain('Enter 0.065 for 6.5%')
    expect(w.find('[data-testid="setting-value"]').text()).toBe('0.065')
  })

  it('sends no effective time for "now" (blank or not after the browser clock); only a chosen future time is sent', async () => {
    answers[`POST /settings/${KEY}`] = setting()
    const w = await open()
    const submit = async (time) => {
      calls.length = 0
      if (!w.find('[data-testid="input-value"]').exists()) await w.find(`[data-testid="edit-${KEY}"]`).trigger('click')
      await w.find('[data-testid="input-value"]').setValue('0.07')
      await w.find('[data-testid="input-note"]').setValue('n')
      await w.find('[data-testid="input-time"]').setValue(time)
      await w.find('form').trigger('submit')
      await flushPromises()
      return calls.find((c) => c[0] === 'POST')[2]
    }
    expect(await submit('')).not.toHaveProperty('effective_from')
    expect(await submit('2020-01-01T10:00')).not.toHaveProperty('effective_from') // already past: the server's clock is "now"
    expect(await submit('2099-01-01T10:00')).toHaveProperty('effective_from')
  })

  it('the rate set form carries the plain fraction hint', async () => {
    const w = await open(page(setting(), CHARGES))
    await w.find('[data-testid="add-rate-set"]').trigger('click')
    expect(w.find('[data-testid="rate-hint"]').text()).toContain('enter 0.001 for 0.1%')
  })

  it('Reset to default posts a reset (a new row) and shows its answer', async () => {
    answers[`POST /settings/${KEY}/reset`] = setting({ is_default: false, set_by: 'owner', effective_from: '2026-11-01T11:00:00+05:30' })
    const w = await open(page(setting({ value: '0.07', is_default: false })))
    await w.find(`[data-testid="edit-${KEY}"]`).trigger('click')
    await w.find('[data-testid="reset"]').trigger('click')
    await flushPromises()
    expect(calls.some((c) => c[0] === 'POST' && c[1] === `/settings/${KEY}/reset`)).toBe(true)
    expect(w.find('[data-testid="setting-value"]').text()).toBe('0.065')
  })

  it('lists the earlier values, newest first, with scheduled rows marked', async () => {
    const w = await open(page(setting({ earlier_values: [
      { value: '0.08', effective_from: '2099-01-01T10:00:00+05:30', set_by: 'owner', state: 'scheduled' },
      { value: '0.07', effective_from: '2026-11-01T10:00:00+05:30', set_by: 'owner', state: 'in_force' }] })))
    const rows = w.findAll('[data-testid="earlier-value-row"]')
    expect(rows.map((r) => r.text().split(' - ')[0])).toEqual(['0.08', '0.07'])
    expect(rows[0].text()).toContain('Scheduled')
  })

  it('Charges group shows the rate set in force and adds a new set with its source address', async () => {
    answers['POST /settings/charges'] = CHARGES
    const w = await open(page(setting(), CHARGES))
    expect(w.find('[data-testid="charge-gst_rate"]').text()).toContain('0.18')
    expect(w.find('[data-testid="charges-in-force"]').text()).toContain('https://zerodha.com/charges')
    await w.find('[data-testid="add-rate-set"]').trigger('click')
    for (const [k, v] of Object.entries(CHARGES.rates)) await w.find(`[data-testid="rate-${k}"]`).setValue(v)
    await w.find('[data-testid="rate-source"]').setValue('https://zerodha.com/charges')
    await w.find('[data-testid="rate-set-form"]').trigger('submit')
    await flushPromises()
    const post = calls.find((c) => c[0] === 'POST')
    expect(post[1]).toBe('/settings/charges')
    expect(post[2].gst_rate).toBe('0.18')
    expect(post[2].source_url).toBe('https://zerodha.com/charges')
  })

  it('a refused rate set shows its reason', async () => {
    answers['POST /settings/charges'] = { message: 'x', status: 422, reason: 'gst_rate is not an allowed number. Write it as text, for example 0.001.' }
    const w = await open(page(setting(), CHARGES))
    await w.find('[data-testid="add-rate-set"]').trigger('click')
    for (const [k, v] of Object.entries(CHARGES.rates)) await w.find(`[data-testid="rate-${k}"]`).setValue(v)
    await w.find('[data-testid="rate-source"]').setValue('https://zerodha.com/charges')
    await w.find('[data-testid="rate-set-form"]').trigger('submit')
    await flushPromises()
    expect(w.find('[data-testid="rate-refusal"]').text()).toContain('gst_rate is not an allowed number')
  })

  it('shows no value when the settings cannot be read', async () => {
    const w = mount(SettingsPage)
    await flushPromises()
    expect(w.find('[data-testid="settings-unavailable"]').exists()).toBe(true)
    expect(w.find('[data-testid="setting-value"]').exists()).toBe(false)
  })

  it('the api error mapper keeps a refusal reason and nothing else of the body', () => {
    const out = mapError({ response: { status: 422, data: { reason: 'Enter 0.065 for 6.5%.', detail: 'secret' } } })
    expect(out.reason).toBe('Enter 0.065 for 6.5%.')
    expect(JSON.stringify(out)).not.toContain('secret')
  })

  describe('a time setting (unit "time", sent as HHMM)', () => {
    const TKEY = 'facts.contract_list_publish_time'
    const timeSetting = (over = {}) => setting({ key: TKEY, group: 'Exchange and broker facts', label: 'Contract list is published at (IST, HHMM)',
      unit: 'time', type: 'integer', min: '0', max: '2359', default: '830', value: '830', ...over })
    const timePage = (s = timeSetting()) => ({ groups: [{ name: 'Exchange and broker facts', settings: [s] }], charges: null })

    it('shows value, default and earlier values as HH:MM, not as the HHMM number', async () => {
      const w = await open(timePage(timeSetting({ value: '1545', is_default: false, set_by: 'owner', effective_from: '2026-11-01T10:00:00+05:30',
        earlier_values: [{ value: '900', effective_from: '2026-11-01T10:00:00+05:30', set_by: 'owner', state: 'earlier' }] })))
      const row = w.find(`[data-testid="setting-${TKEY}"]`)
      expect(row.find('[data-testid="setting-value"]').text()).toBe('15:45')
      expect(row.find('[data-testid="setting-default"]').text()).toBe('08:30')
      expect(w.find('[data-testid="earlier-value-row"]').text()).toContain('09:00')
    })

    it('takes HH:MM and sends the HHMM whole number', async () => {
      answers[`POST /settings/${TKEY}`] = timeSetting({ value: '900', is_default: false, set_by: 'owner', effective_from: '2026-11-01T10:00:00+05:30' })
      const w = await open(timePage())
      await w.find(`[data-testid="edit-${TKEY}"]`).trigger('click')
      expect(w.find('[data-testid="input-value"]').attributes('type')).toBe('time')
      await w.find('[data-testid="input-value"]').setValue('09:00')
      await w.find('[data-testid="input-note"]').setValue('Kite moved it')
      await w.find('form').trigger('submit')
      await flushPromises()
      expect(calls.find((c) => c[0] === 'POST')).toEqual(['POST', `/settings/${TKEY}`, { value: '900', note: 'Kite moved it' }])
      expect(w.find(`[data-testid="setting-${TKEY}"] [data-testid="setting-value"]`).text()).toBe('09:00')
    })

    it('refuses text that is not a time of day, without sending anything', async () => {
      const w = await open(timePage())
      await w.find(`[data-testid="edit-${TKEY}"]`).trigger('click')
      await w.find('[data-testid="input-value"]').setValue('25:70')
      await w.find('[data-testid="input-note"]').setValue('x')
      await w.find('form').trigger('submit')
      await flushPromises()
      expect(calls.some((c) => c[0] === 'POST')).toBe(false)
      expect(w.find('[data-testid="refusal"]').text()).toBe('Enter a time as HH:MM, for example 09:30.')
    })
  })
})
