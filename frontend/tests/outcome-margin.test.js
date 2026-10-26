// ADR-099: the margin slot of the outcome screen, one test per state. The margin blocks are the backend's own MarginOut
// output (tests/fixtures/outcome-margin-states.json, written from ofo.outcome.service): 7065.50 is the recorded
// 2026-10-16 strangle basket's required total, 671.50 ADR-099's real available funds. Expected time hand-computed:
// 06:38:52 UTC + 5:30 = 12:08:52 IST. The browser shows the API strings; it never parses or compares money.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import MarginLine from '@/components/strategy/MarginLine.vue'
import STATES from './fixtures/outcome-margin-states.json'
import CONDOR from './fixtures/outcome-condor.json'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const ON = { basket_margin_quote: true } // REQ-117: the flag the margin line asks
const line = (margin, capabilities = ON) => mount(MarginLine, { props: { margin, capabilities } })

// REQ-117 AC-4 (W-132): the margin line asks the flag `basket_margin_quote`; missing, unknown or unreadable = hidden.
const REASON = 'Margin from the broker is not available for this account.'
describe('margin line asks the basket_margin_quote flag (REQ-117)', () => {
  const ZERODHA = { basket_page_orders: true, broker_held_triggers: false, intraday_product: true,
    order_update_stream: true, funds_read: true, positions_read: true, basket_margin_quote: true }
  const withoutFlag = (({ basket_margin_quote: _removed, ...rest }) => rest)(ZERODHA)

  it('core: flag on shows the figures; the flag removed hides them with the plain reason', () => {
    expect(t(line(STATES.enough, ZERODHA), 'margin-figures').exists()).toBe(true)
    const w = line(STATES.enough, withoutFlag)
    expect(t(w, 'margin-hidden-reason').text()).toBe(REASON)
    expect(t(w, 'margin-figures').exists()).toBe(false)
    expect(t(w, 'margin-checked-at').exists()).toBe(false)
    expect(t(w, 'margin-text').exists()).toBe(false)
    expect(t(w, 'margin').attributes('data-margin-state')).toBe('HIDDEN')
  })

  it.each([
    ['false', { ...ZERODHA, basket_margin_quote: false }],
    ['the string "true"', { ...ZERODHA, basket_margin_quote: 'true' }],
    ['1', { ...ZERODHA, basket_margin_quote: 1 }],
    ['an empty body (a failed read)', {}],
    ['an unknown flag only', { basket_margin_quote_v2: true }],
    ['an array', [true]],
  ])('hidden when the flag is %s', (_label, body) => {
    const w = line(STATES.shortfall, body)
    expect(t(w, 'margin-hidden-reason').text()).toBe(REASON)
    expect(t(w, 'margin-figures').exists()).toBe(false)
    expect(t(w, 'margin-shortfall').exists()).toBe(false)
  })

  it('the reason names no broker', () => {
    expect(REASON).not.toMatch(/zerodha|kite/i)
  })

  it('while the flags are still being read nothing is drawn (null), and a missing prop is the same', () => {
    expect(line(STATES.enough, null).find('[data-testid="margin"]').exists()).toBe(false)
    expect(mount(MarginLine, { props: { margin: STATES.enough } }).find('[data-testid="margin"]').exists()).toBe(false)
  })
})

describe('outcome margin slot (ADR-099)', () => {
  it('shortfall: the figures, the shortfall mark and the Checked-at time', () => {
    const w = line(STATES.shortfall)
    expect(t(w, 'margin').attributes('data-margin-state')).toBe('CHECKED')
    expect(t(w, 'margin-figures').text()).toBe('Margin (Zerodha): Rs 7065.50 needed, Rs 671.50 available')
    expect(t(w, 'margin-figures').classes()).toContain('text-red-700')
    expect(t(w, 'margin-shortfall').text()).toBe('Available funds are below the margin needed.')
    expect(t(w, 'margin-checked-at').text()).toBe('Checked at 16 Oct 2026, 12:08:52 IST')
    expect(t(w, 'margin-text').exists()).toBe(false)
  })

  it('short with the server line: shown verbatim, with both ways forward (REQ-055 AC-4)', () => {
    const w = line(STATES.short)
    expect(t(w, 'margin-shortfall').text()).toBe(STATES.short.shortfall_reason)
    expect(t(w, 'margin-shortfall').text()).toContain('Reduce the quantity, review the strategy, or add funds')
    expect(t(w, 'margin-shortfall').findAll('button, a').length).toBe(0) // text only: nothing places, builds or changes anything
  })

  it('the browser never compares: figures that read needed < available with shortfall true still show the shortfall', () => {
    const w = line(STATES.string_trap)
    expect(t(w, 'margin-shortfall').text()).toBe('The server decided this one.')
    const none = line({ ...STATES.string_trap, shortfall: false, shortfall_reason: null })
    expect(t(none, 'margin-shortfall').exists()).toBe(false)
  })

  it('enough funds: the figures without a shortfall mark', () => {
    const w = line(STATES.enough)
    expect(t(w, 'margin-figures').text()).toBe('Margin (Zerodha): Rs 7065.50 needed, Rs 12500.00 available')
    expect(t(w, 'margin-figures').classes()).not.toContain('text-red-700')
    expect(t(w, 'margin-shortfall').exists()).toBe(false)
    expect(t(w, 'margin-checked-at').text()).toBe('Checked at 16 Oct 2026, 12:08:52 IST')
  })

  it('the shortfall mark follows the server flag only, never a browser comparison', () => {
    const w = line({ ...STATES.shortfall, shortfall: false })
    expect(t(w, 'margin-shortfall').exists()).toBe(false)
  })

  it('no session: the catalogue login text as today, no figures', () => {
    const w = line(STATES.no_session)
    expect(t(w, 'margin-text').text()).toBe('Margin from Zerodha is not shown yet; it needs your Kite login.')
    expect(t(w, 'margin-figures').exists()).toBe(false)
    expect(t(w, 'margin-checked-at').exists()).toBe(false)
  })

  it('could not read: the catalogue text, no figures', () => {
    const w = line(STATES.unreadable)
    expect(t(w, 'margin-text').text()).toBe('Margin from Zerodha could not be read just now, so no margin figure is shown.')
    expect(t(w, 'margin-figures').exists()).toBe(false)
  })

  it('an older answer without the new fields still shows its text', () => {
    expect(t(line(CONDOR.margin), 'margin-text').text()).toBe(CONDOR.margin.reason)
  })

  it('wraps instead of widening the page at 390 px (no fixed width, no nowrap)', () => {
    const w = line(STATES.shortfall)
    const html = w.html()
    expect(t(w, 'margin').classes()).toEqual(expect.arrayContaining(['min-w-0', 'break-words']))
    expect(html).not.toMatch(/whitespace-nowrap|w-\[\d|min-w-\[|overflow-x/)
  })
})
