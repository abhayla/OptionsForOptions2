// W-119 (REQ-024, REQ-026, REQ-068; ADR-003, ADR-008): Create Strategy with fake route replies. Labels asserted are the
// REQ texts quoted verbatim; numbers asserted are the fake outcome reply's strings, shown exactly as sent (one engine).
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { expandTemplate, expiryLabels, matchTemplates, rangeLists, readingFromRange, viewFromRange, FORBIDDEN_WORDS } from '@/lib/guided'

const posts = []
let plannedPrice = '120.50'
let level = '22812.40' // the fake index level
let contractsNow = null // null = CONTRACTS
const leg = (action, instrument, strike_steps) => ({ action, instrument, strike_steps, expiry_slot: 'near', quantity_multiplier: 1 })
const TEMPLATES = { templates: [
  { id: 'bull_call_spread', name: 'Bull Call Spread', description: 'd', level: 'Beginner', views: ['bullish'], objectives: ['directional'],
    legs: [leg('BUY', 'CE', 0), leg('SELL', 'CE', 2)] },
  { id: 'cash_secured_put', name: 'Cash Secured Put', description: 'd', level: 'Intermediate', views: ['bullish'], objectives: ['income'],
    legs: [leg('SELL', 'PE', -2)] },
  { id: 'iron_condor', name: 'Iron Condor', description: 'd', level: 'Advanced', views: ['range-bound'], objectives: ['income'],
    legs: [leg('SELL', 'PE', -1), leg('BUY', 'PE', -3), leg('SELL', 'CE', 1), leg('BUY', 'CE', 3)] },
] }
const ct = (token, type, strike) => ({ contract_id: token, exchange_segment: 'NSE_FO', exchange_token: token, instrument_type: type,
  expiry: '2026-10-13', strike, lot_size: 65, symbol: `NIFTY${strike}${type}` })
const CONTRACTS = [ct(1, 'PE', '22600.00'), ct(2, 'PE', '22700.00'), ct(3, 'CE', '22800.00'), ct(4, 'PE', '22800.00'),
  ct(5, 'CE', '22900.00'), ct(6, 'CE', '23000.00'), ct(7, 'CE', '23100.00'), ct(8, 'PE', '22500.00')]
const SUMMARY = { what_can_i_lose: 'L', what_can_i_make: 'M', where_do_i_start_losing: 'S', max_profit: '6175.00', max_loss: '-6825.00',
  max_profit_unlimited: false, max_loss_unlimited: false, breakevens: ['22905.00'], lower_be: null, upper_be: '22905.00', risk_boundaries: [] }

vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return { ...actual, default: {
    get: (url) => {
      if (url === '/strategy-templates') return Promise.resolve({ data: TEMPLATES })
      if (url === '/catalogue/NIFTY/expiries') return Promise.resolve({ data: { underlying: 'NIFTY', expiries: ['2026-10-13', '2026-10-20', '2026-10-27'] } })
      if (url.startsWith('/catalogue/NIFTY/contracts')) return Promise.resolve({ data: { underlying: 'NIFTY', contracts: contractsNow ?? CONTRACTS } })
      if (url === '/market/indices') return Promise.resolve({ data: { state: 'LIVE', indices: [{ underlying: 'NIFTY', value: level }] } })
      return Promise.reject(new Error(url))
    },
    post: (url, body) => {
      posts.push({ url, body })
      if (url === '/strategies/planned-entry') {
        return Promise.resolve({ data: { entries: body.instrument_ids.map((id) => ({ exchange_segment: 'NSE_FO', exchange_token: Number(id.split(':')[1]),
          planned_entry: plannedPrice, captured_at: plannedPrice ? '2026-10-13T09:20:00+05:30' : null })) } })
      }
      return Promise.resolve({ data: { summary: SUMMARY, margin: null } })
    },
  } }
})
import { routes } from '@/router/routes'

async function mountPage() {
  const router = createRouter({ history: createMemoryHistory(), routes })
  router.push('/strategies/create-strategy')
  await router.isReady()
  const App = { template: '<router-view />' }
  const w = mount(App, { global: { plugins: [router] } })
  await flushPromises()
  return { w, router }
}
const pick = async (w, testid, key) => { await w.find(`[data-testid="${testid}"][data-key="${key}"]`).trigger('click'); await flushPromises() }
async function toResults(w, objective, view) {
  await w.find('[data-testid="path-guided"]').trigger('click')
  await pick(w, 'objective', objective)
  if (view) await pick(w, 'market-view', view)
  await w.find('[data-testid="pick-expiry"]').setValue('2026-10-13')
  await flushPromises()
  await w.find('[data-testid="show-strategies"]').trigger('click')
  await flushPromises()
}

beforeEach(() => { posts.length = 0; plannedPrice = '120.50'; level = '22812.40'; contractsNow = null })

describe('Create Strategy page', () => {
  it('REQ-024 AC-6: offers the two paths with their exact titles', async () => {
    const { w } = await mountPage()
    expect(w.find('[data-testid="page-title"]').text()).toBe('Create Strategy')
    expect(w.find('[data-testid="path-guided"]').text()).toBe('Guided Strategy BuilderHelp me build a strategy')
    expect(w.find('[data-testid="path-advanced"]').text()).toBe('Advanced Manual BuilderI know what I want')
  })

  it('REQ-024 AC-1/AC-5: the advanced path opens an empty Builder', async () => {
    const { w, router } = await mountPage()
    const push = vi.spyOn(router, 'push').mockResolvedValue(undefined)
    await w.find('[data-testid="path-advanced"]').trigger('click')
    expect(push).toHaveBeenCalledWith('/strategy/builder')
  })

  it('REQ-024 AC-3: the six objectives, verbatim, at Step 1 of 4', async () => {
    const { w } = await mountPage()
    await w.find('[data-testid="path-guided"]').trigger('click')
    expect(w.find('[data-testid="step-indicator"]').text()).toBe('Step 1 of 4')
    expect(w.findAll('[data-testid="objective"]').map((b) => b.text())).toEqual(['Earn premium', 'Limit risk',
      'Benefit if market rises', 'Benefit if market falls', 'Trade a big move', 'I already know my strategy'])
  })

  it('REQ-024 AC-7: the five simple market views; Back returns to Step 1', async () => {
    const { w } = await mountPage()
    await w.find('[data-testid="path-guided"]').trigger('click')
    await pick(w, 'objective', 'rises')
    expect(w.findAll('[data-testid="market-view"]').map((b) => b.text())).toEqual(['Bullish', 'Bearish', 'Neutral', 'Big move', 'Not sure'])
    await w.find('[data-testid="step-back"]').trigger('click')
    expect(w.find('[data-testid="step-indicator"]').text()).toBe('Step 1 of 4')
  })

  it('REQ-024 AC-8: cards show name, view, and the engine numbers exactly as the outcome route sent them', async () => {
    const { w } = await mountPage()
    await toResults(w, 'rises', 'bullish')
    const cards = w.findAll('[data-testid="strategy-card"]')
    expect(cards.map((c) => c.attributes('data-template-id'))).toEqual(['bull_call_spread', 'cash_secured_put'])
    expect(cards[0].find('[data-testid="card-max-profit"]').text()).toBe('6175.00')
    expect(cards[0].find('[data-testid="card-max-loss"]').text()).toBe('-6825.00')
    expect(cards[0].find('[data-testid="card-breakevens"]').text()).toBe('22905.00')
    expect(w.find('[data-testid="results-heading"]').text()).toBe('Strategies you could consider')
    const outcome = posts.filter((p) => p.url === '/strategies/outcome')[0].body
    expect(outcome.legs.map((l) => [l.instrument_id, l.action, l.planned_entry])).toEqual([['NSE_FO:3', 'BUY', '120.50'], ['NSE_FO:6', 'SELL', '120.50']])
    await cards[0].find('[data-testid="card-details-toggle"]').trigger('click')
    expect(cards[0].find('[data-testid="card-details"]').text()).toContain('L')
  })

  it('REQ-024 AC-8: no planned entry means no numbers, never a guess', async () => {
    plannedPrice = null
    const { w } = await mountPage()
    await toResults(w, 'rises', 'bullish')
    expect(w.findAll('[data-testid="card-not-priced"]').length).toBe(2)
    expect(w.find('[data-testid="card-max-profit"]').exists()).toBe(false)
    expect(posts.some((p) => p.url === '/strategies/outcome')).toBe(false)
  })

  it('REQ-024 AC-4: "I already know my strategy" skips discovery and lists the library, Beginner first', async () => {
    const { w } = await mountPage()
    await w.find('[data-testid="path-guided"]').trigger('click')
    await pick(w, 'objective', 'know')
    expect(w.find('[data-testid="step-indicator"]').text()).toBe('Step 3 of 4')
    await w.find('[data-testid="pick-expiry"]').setValue('2026-10-13')
    await flushPromises()
    await w.find('[data-testid="show-strategies"]').trigger('click')
    await flushPromises()
    expect(w.findAll('[data-testid="strategy-card"]').map((c) => c.attributes('data-template-id'))).toEqual(['bull_call_spread', 'cash_secured_put', 'iron_condor'])
  })

  it('REQ-024 AC-2: Open in Strategy Builder carries the chosen legs with their planned entries', async () => {
    const { w, router } = await mountPage()
    await toResults(w, 'earn-premium', 'bullish')
    const push = vi.spyOn(router, 'push').mockResolvedValue(undefined)
    await w.find('[data-testid="open-in-builder"]').trigger('click')
    const target = push.mock.calls[0][0]
    expect(target.path).toBe('/strategy/builder')
    expect(target.query.ux).toBe('guided')
    const draft = JSON.parse(target.query.draft)
    expect(draft.underlying).toBe('NIFTY')
    expect(draft.legs.map((l) => [l.instrument_id, l.action, l.lots, l.planned_entry])).toEqual([['NSE_FO:1', 'SELL', 1, '120.50']])
  })

  it('REQ-026 AC-1/AC-4/AC-7: Not sure -> range pick lists, results line names the range and expiry (provisional wording)', async () => {
    const { w } = await mountPage()
    await w.find('[data-testid="path-guided"]').trigger('click')
    await pick(w, 'objective', 'earn-premium')
    await pick(w, 'market-view', 'not-sure')
    await w.find('[data-testid="pick-expiry"]').setValue('2026-10-13')
    await flushPromises()
    expect(w.find('[data-testid="pick-lower"]').element.value).toBe('22812.40')
    expect(w.find('[data-testid="pick-upper"]').element.value).toBe('22812.40')
    expect(w.find('input').exists()).toBe(false) // REQ-026 AC-5: no typed numbers, no slider
    await w.find('[data-testid="pick-lower"]').setValue('22600')
    await w.find('[data-testid="pick-upper"]').setValue('23000')
    await w.find('[data-testid="show-strategies"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="results-heading"]').text())
      .toBe('Based on your expected range of 22600–23000 by This Week — 13 Oct, here are strategies you could consider')
    expect(w.find('[data-testid="range-note"]').text()).toBe('Your expected range is an input, not a prediction.')
    expect(w.findAll('[data-testid="strategy-card"]').map((c) => c.attributes('data-template-id'))).toEqual(['iron_condor'])
  })

  describe('range reading (ADR-121 (1), ADR-122)', () => {
    // NIFTY 24,350: every 100-point strike 23,500..25,100, both sides, so the range lists reach the ADR examples.
    const wide = () => {
      level = '24350.00'
      const out = []
      let t = 100
      for (let k = 23500; k <= 25100; k += 100) { out.push(ct(t += 1, 'CE', `${k}.00`)); out.push(ct(t += 1, 'PE', `${k}.00`)) }
      contractsNow = out
    }
    const toRange = async (w, lo, hi) => {
      await w.find('[data-testid="path-guided"]').trigger('click')
      await pick(w, 'objective', 'earn-premium')
      await pick(w, 'market-view', 'not-sure')
      await w.find('[data-testid="pick-expiry"]').setValue('2026-10-13')
      await flushPromises()
      await w.find('[data-testid="pick-lower"]').setValue(lo)
      await w.find('[data-testid="pick-upper"]').setValue(hi)
      await flushPromises()
    }
    const cardIds = (w) => w.findAll('[data-testid="strategy-card"]').map((c) => c.attributes('data-template-id'))

    it('24,350 with 24,300-25,100 reads "Your range leans up" and shows bullish cards', async () => {
      wide()
      const { w } = await mountPage()
      await toRange(w, '24300', '25100')
      expect(w.find('[data-testid="range-reading"]').text()).toBe('Your range leans up')
      expect(w.find('[data-testid="strategy-card"]').exists()).toBe(false) // cards only after Show strategies
      await w.find('[data-testid="show-strategies"]').trigger('click')
      await flushPromises()
      expect(cardIds(w)).toEqual(['cash_secured_put'])
    })

    it('24,350 with 24,000-24,600 reads "Your range is balanced" and shows range-bound cards', async () => {
      wide()
      const { w } = await mountPage()
      await toRange(w, '24000', '24600')
      expect(w.find('[data-testid="range-reading"]').text()).toBe('Your range is balanced')
      await w.find('[data-testid="show-strategies"]').trigger('click')
      await flushPromises()
      expect(cardIds(w)).toEqual(['iron_condor'])
    })

    it('24,350 with 23,500-24,500 reads "Your range leans down"', async () => {
      wide()
      const { w } = await mountPage()
      await toRange(w, '23500', '24500')
      expect(w.find('[data-testid="range-reading"]').text()).toBe('Your range leans down')
    })

    it('ADR-124: the pick-reading options read exactly Mildly bullish / Mildly bearish / Neutral, no suffix', async () => {
      const cases = [
        ['24300', '25100', ['Mildly bullish', 'Mildly bearish', 'Neutral']],
        ['23500', '24500', ['Mildly bearish', 'Mildly bullish', 'Neutral']],
        ['24000', '24600', ['Neutral', 'Mildly bullish', 'Mildly bearish']],
      ]
      for (const [lo, hi, expected] of cases) {
        wide()
        const { w } = await mountPage()
        await toRange(w, lo, hi)
        const texts = w.find('[data-testid="pick-reading"]').findAll('option').map((o) => o.text())
        expect(texts).toEqual(expected)
        expect([...texts].sort()).toEqual(['Mildly bearish', 'Mildly bullish', 'Neutral'])
      }
    })

    it('changing the reading changes the cards', async () => {
      wide()
      const { w } = await mountPage()
      await toRange(w, '24300', '25100')
      await w.find('[data-testid="pick-reading"]').setValue('balanced')
      await w.find('[data-testid="show-strategies"]').trigger('click')
      await flushPromises()
      expect(cardIds(w)).toEqual(['iron_condor'])
    })
  })

  it('ADR-003: no forbidden advice word anywhere on the results screen', async () => {
    const { w } = await mountPage()
    await toResults(w, 'know', null)
    const text = w.text().toLowerCase()
    for (const word of FORBIDDEN_WORDS) expect(text).not.toContain(word)
  })
})

describe('guided helpers', () => {
  it('ADR-121 (1): more than twice is directional, exactly twice is not; each side', () => {
    expect(readingFromRange('24350', '24300', '25100')).toBe('up') // 50 below, 750 above
    expect(readingFromRange('24350', '24000', '24600')).toBe('balanced') // 350 / 250
    expect(readingFromRange('24350', '23500', '24500')).toBe('down') // 850 / 150
    expect(readingFromRange('100', '90', '120')).toBe('balanced') // 10 / 20: exactly twice
    expect(readingFromRange('100', '90', '121')).toBe('up') // 10 / 21
    expect(readingFromRange('100', '80', '110')).toBe('balanced') // 20 / 10: exactly twice
    expect(readingFromRange('100', '79', '110')).toBe('down') // 21 / 10
    expect(viewFromRange('100', '90', '121')).toBe('bullish')
    expect(viewFromRange('100', '79', '110')).toBe('bearish')
    expect(viewFromRange('100', '90', '120')).toBe('range-bound')
  })

  it('REQ-026 AC-2: expiry labels are real dates with This Week / Next Week / Monthly / Next Monthly', () => {
    expect(expiryLabels(['2026-10-13', '2026-10-20', '2026-10-27', '2026-11-24']).map((e) => e.label))
      .toEqual(['This Week — 13 Oct', 'Next Week — 20 Oct', 'Monthly — 27 Oct', 'Next Monthly — 24 Nov'])
  })

  it('REQ-026 AC-3/AC-5/AC-6: lists start at the current level, 100-point listed strikes only, lower below / upper above', () => {
    const l = rangeLists('22812.40', CONTRACTS, 'NIFTY')
    expect(l.lower).toEqual(['22812.40', '22800', '22700', '22600', '22500'])
    expect(l.upper).toEqual(['22812.40', '22900', '23000', '23100'])
    expect(() => rangeLists(null, CONTRACTS, 'NIFTY')).toThrow()
    expect(() => viewFromRange('22812.40', '22900', '23000')).toThrow() // lower above the current level is refused
  })

  it('REQ-026 AC-5: the per-index cap bounds the list (NIFTY 3,000 points)', () => {
    const far = [...CONTRACTS, ct(9, 'PE', '19700.00'), ct(10, 'PE', '19900.00')]
    expect(rangeLists('22812.40', far, 'NIFTY').lower).toContain('19900')
    expect(rangeLists('22812.40', far, 'NIFTY').lower).not.toContain('19700')
  })

  it('REQ-068 AC-4: when nothing matches both, the view-only list is returned and flagged', () => {
    const r = matchTemplates(TEMPLATES.templates, 'limit-risk', 'bullish')
    expect(r.fallback).toBe(true)
    expect(r.list.map((t) => t.id)).toEqual(['bull_call_spread', 'cash_secured_put'])
  })

  it('REQ-028: a template leg that is not a listed contract drops the template, never a substitute strike', () => {
    expect(expandTemplate(TEMPLATES.templates[0], CONTRACTS.filter((c) => c.exchange_token !== 6), '22812.40')).toBeNull()
    expect(expandTemplate({ legs: [{ ...leg('BUY', 'CE', 0), expiry_slot: 'far' }] }, CONTRACTS, '22812.40')).toBeNull()
  })
})
