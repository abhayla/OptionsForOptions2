// GC-UI step 3b (ADR-202 (1), ADR-204; docs/process/ui-match-differences-2026-10-28.md rows D-A04, D-A21, D-A29..D-A33,
// D-A36, D-A37, D-A42): the summary block in Sensibull's form. The figures are strategy 54's REAL reply (debit spread,
// read 2026-10-28, D:\Abhay\scratch\gcui-checker\run4-live-close) with the server's REQ-152 / REQ-153 display strings;
// the funds figure and the two percent texts (which would reveal it) are placeholders: this repo is public.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SummaryCards from '@/components/strategy/SummaryCards.vue'
import FigureHint from '@/components/common/FigureHint.vue'
import { summaryFigure } from '@/lib/summaryFigures'
import { MAX_NOT_AVAILABLE } from '@/lib/displayFormat'

const MAKE = 'At most ₹7,152.21 at expiry, including about ₹140.79 of charges and taxes.'
const LOSE = 'At most ₹5,847.79 at expiry, including about ₹140.79 of charges and taxes. Holding a bought option to expiry in the money adds STT on its value; squaring off before expiry avoids it.'
const START = 'If NIFTY ends below 22,687.80 at expiry, before about ₹140.79 of charges and taxes.'
const S54 = {
  max_profit: '7152.21', max_profit_display: '+7,152', max_loss: '5847.79', max_loss_display: '\u22125,848',
  max_profit_unlimited: false, max_loss_unlimited: false,
  breakevens: ['22687.8'], breakevens_display: ['22,688 (\u22120.1%)'],
  what_can_i_make: MAKE, what_can_i_lose: LOSE, where_do_i_start_losing: START,
  time_value: '-152.75', time_value_display: '\u2212153', intrinsic_value: '6942.00', intrinsic_value_display: '+6,942',
  value_label: 'value of the options, not P&L', reward_risk: '1.22',
  funds_share: { funds: 'FUNDS', read_at: '2026-10-28T09:49:05.571132Z', max_profit_percent: 'P1', max_loss_percent: 'P2',
    max_profit_text: 'P1% of funds', max_loss_text: 'P2% of funds' },
}
const FUNDS_LINE = 'Percentages are of Rs FUNDS available funds, read 28 Oct 2026, 15:19:05 IST'

const props = (s, extra = {}) => ({
  maxProfit: summaryFigure(s, 'profit'), maxLoss: summaryFigure(s, 'loss'),
  maxProfitExact: s.max_profit, maxLossExact: s.max_loss,
  breakevens: s.breakevens_display ?? [], breakevensExact: s.breakevens ?? [],
  whatCanIMake: s.what_can_i_make, whatCanILose: s.what_can_i_lose, whereIStartLosing: s.where_do_i_start_losing,
  rewardRisk: s.reward_risk ?? null, timeValue: s.time_value_display ?? null, timeValueExact: s.time_value ?? null,
  intrinsicValue: s.intrinsic_value_display ?? null, intrinsicValueExact: s.intrinsic_value ?? null,
  valueLabel: s.value_label ?? null, valueReason: s.value_reason ?? null, fundsShare: s.funds_share ?? null, ...extra,
})
const t = (w, id) => w.find(`[data-testid="${id}"]`)
const hint = (w, fig) => w.find(`[data-testid="figure-hint"][data-figure="${fig}"]`)
async function hintText(w, fig) {
  await hint(w, fig).find('[data-testid="figure-hint-mark"]').trigger('click')
  return hint(w, fig).find('[data-testid="figure-hint-text"]').text()
}

describe('D-A21 / D-A29: Max Profit / Max Loss are the server display strings in small signed pills, percent inline', () => {
  it('prints "+7,152" and "\u22125,848" as sent, the percent text inline in the same pill', () => {
    const w = mount(SummaryCards, { props: props(S54) })
    expect(t(w, 'max-profit').text()).toBe('+7,152')
    expect(t(w, 'max-loss').text()).toBe('\u22125,848')
    expect(t(w, 'max-profit-pill').text()).toBe('+7,152(P1% of funds)')
    expect(t(w, 'max-loss-pill').text()).toBe('\u22125,848(P2% of funds)')
    expect(w.text()).not.toMatch(/7,152\.21|5,847\.79|₹7|₹5/)
  })
  it('funds unreadable: no percent, the figures stay (REQ-081 AC-10)', () => {
    const w = mount(SummaryCards, { props: props({ ...S54, funds_share: null }) })
    expect(t(w, 'max-profit-pill').text()).toBe('+7,152')
    expect(t(w, 'max-profit-percent').exists()).toBe(false)
    expect(w.text()).not.toMatch(/Percentages are of/)
  })
})

describe('D-A30 / D-A31: the plain sentences and the funds line sit in each figure\u2019s "?", words unchanged', () => {
  it('no visible "At most ..." or funds line; both reachable verbatim in the tooltips with the exact value', async () => {
    const w = mount(SummaryCards, { props: props(S54) })
    expect(w.text()).not.toContain('At most')
    expect(w.text()).not.toContain('Percentages are of')
    const make = await hintText(w, 'max_profit')
    expect(make).toContain(MAKE)
    expect(make).toContain(FUNDS_LINE)
    expect(make).toContain('Exact value: 7152.21')
    const lose = await hintText(w, 'max_loss')
    expect(lose).toContain(LOSE)
    expect(lose).toContain(FUNDS_LINE)
    expect(lose).toContain('Exact value: 5847.79')
  })
})

describe('D-A32 / D-A33 / D-A04: Breakeven [Target / Expiry] (?) then the small server value with its percent', () => {
  it('prints "22,688 (\u22120.1%)", the "?" after the switch, the If-NIFTY sentence in the tooltip', async () => {
    const w = mount(SummaryCards, { props: props(S54) })
    expect(t(w, 'breakevens').text()).toBe('22,688 (\u22120.1%)')
    expect(t(w, 'breakevens').classes()).not.toContain('font-semibold')
    const row = t(w, 'breakeven-row').html()
    expect(row.indexOf('breakeven-expiry')).toBeLessThan(row.indexOf('data-figure="breakeven_expiry"'))
    expect(w.text()).not.toContain('If NIFTY ends below')
    const be = await hintText(w, 'breakeven_expiry')
    expect(be).toContain(START)
    expect(be).toContain('Exact value: 22687.8')
  })
  it('no breakeven: "-"', () => {
    const w = mount(SummaryCards, { props: props({ ...S54, breakevens: [], breakevens_display: [] }) })
    expect(t(w, 'breakevens').text()).toBe('-')
  })
})

describe('D-A36: Time value / Intrinsic value print the display strings; the caption is in their "?"', () => {
  it('"\u2212153" and "+6,942"; "value of the options, not P&L" is not visible but is in both tooltips', async () => {
    const w = mount(SummaryCards, { props: props(S54) })
    expect(t(w, 'time-value').text()).toBe('\u2212153')
    expect(t(w, 'intrinsic-value').text()).toBe('+6,942')
    expect(t(w, 'value-label').exists()).toBe(false)
    expect(await hintText(w, 'time_value')).toContain('value of the options, not P&L')
    expect(await hintText(w, 'intrinsic_value')).toContain('Exact value: 6942.00')
  })
  it('a true zero is "0"; a missing figure is "-" with the reason visible', () => {
    const z = mount(SummaryCards, { props: props({ ...S54, intrinsic_value: '0', intrinsic_value_display: '0' }) })
    expect(t(z, 'intrinsic-value').text()).toBe('0')
    const n = mount(SummaryCards, { props: props({ ...S54, time_value: null, time_value_display: null,
      intrinsic_value: null, intrinsic_value_display: null, value_reason: 'No quote for one leg.' }) })
    expect(t(n, 'time-value').text()).toBe('-')
    expect(t(n, 'value-reason').text()).toBe('No quote for one leg.')
  })
})

describe('D-A42: "estimated from spot" is one small label beside the figures (ADR-061: never silent)', () => {
  it('shown once when the server says it, absent otherwise', () => {
    const w = mount(SummaryCards, { props: props(S54, { estimateLabel: 'estimated from spot' }) })
    expect(w.findAll('[data-testid="output-label"]')).toHaveLength(1)
    expect(t(w, 'output-label').text()).toBe('estimated from spot')
    expect(t(mount(SummaryCards, { props: props(S54) }), 'output-label').exists()).toBe(false)
  })
})

describe('summaryFigure: answer states', () => {
  it('display as sent; Unlimited; calendar "Not available"; an older reply without the display field "-"', () => {
    expect(summaryFigure(S54, 'profit')).toBe('+7,152')
    expect(summaryFigure({ ...S54, max_profit_unlimited: true, max_profit: null, max_profit_display: null }, 'profit')).toBe('Unlimited')
    expect(summaryFigure({ max_loss: null, max_loss_display: null, max_loss_unlimited: false }, 'loss')).toBe(MAX_NOT_AVAILABLE)
    expect(summaryFigure({ max_loss: '5847.79', max_loss_unlimited: false }, 'loss')).toBe('-')
    expect(summaryFigure(null, 'loss')).toBe('-')
  })
})

describe('D-A37: the help icon is the circled "?" form', () => {
  it('FigureHint draws a question mark, and extra lines after the definition', async () => {
    const w = mount(FigureHint, { props: { id: 'max_profit', lines: ['Line one.', null, 'Line two.'] } })
    expect(w.find('[data-testid="figure-hint-mark"]').attributes('data-icon')).toBe('question')
    await w.find('[data-testid="figure-hint-mark"]').trigger('click')
    expect(w.findAll('[data-testid="figure-hint-line"]').map((l) => l.text())).toEqual(['Line one.', 'Line two.'])
  })
  it('a labelled hint with no catalogue id draws when it has lines', async () => {
    const w = mount(FigureHint, { props: { id: 'important_info', label: 'Important info', lines: ['A sentence.'] } })
    expect(w.find('[data-testid="figure-hint-mark"]').attributes('aria-label')).toBe('What is Important info?')
    expect(mount(FigureHint, { props: { id: 'not_a_figure' } }).html()).toBe('<!--v-if-->')
  })
})
