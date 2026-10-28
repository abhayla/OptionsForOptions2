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
// GC-UI step 3b (D-A41, ADR-202 (4)): the warning is one visible line; the server's full message is behind More
const shortText = async (w) => {
  await t(w, 'margin-shortfall-more').trigger('click')
  return t(w, 'margin-shortfall-text').text()
}
// D-A40: "Checked at" moved into the Margin available "?"
const hintOf = async (w, fig) => {
  const h = w.find(`[data-testid="figure-hint"][data-figure="${fig}"]`)
  await h.find('[data-testid="figure-hint-mark"]').trigger('click')
  return h.find('[data-testid="figure-hint-text"]').text()
}

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
  it('shortfall: the figures, the shortfall mark and the Checked-at time', async () => {
    const w = line(STATES.shortfall)
    expect(t(w, 'margin').attributes('data-margin-state')).toBe('CHECKED')
    expect(t(w, 'margin-figures').text()).toBe(STATES.shortfall.reason)
    // W-193 (I-8): the figures sentence is no longer printed in red; the block carries the loss border and one line
    expect(t(w, 'margin-figures').classes()).not.toContain('text-red-700')
    expect(t(w, 'margin').attributes('data-short')).toBe('true')
    expect(t(w, 'margin').classes()).toEqual(expect.arrayContaining(['border-l-4', 'border-loss']))
    expect(t(w, 'margin-short-line').text()).toBe('Not enough funds for this strategy')
    expect(t(w, 'margin-shortfall').classes()).toContain('text-loss')
    expect(w.findAll('[data-testid="margin-shortfall"]')).toHaveLength(1)
    expect(await shortText(w)).toBe('Available funds are below the margin needed.')
    expect(t(w, 'margin-checked-at').exists()).toBe(false)
    expect(await hintOf(w, 'margin_available')).toContain('Checked at 16 Oct 2026, 12:08:52 IST')
    expect(t(w, 'margin-text').exists()).toBe(false)
  })

  it('W-193 (UI-118): Margin needed and Margin available are the server strings as sent, each with one labelled mark', () => {
    const w = line(STATES.enough)
    expect(t(w, "margin-needed").attributes("data-raw")).toBe(STATES.enough.needed)
    expect(t(w, 'margin-available').attributes('data-raw')).toBe(STATES.enough.available)
    expect(t(w, 'funds-margins-title').text()).toBe('Funds & Margins')
    expect(t(w, 'margin').attributes('data-short')).toBe('false')
    expect(t(w, 'margin').classes()).not.toContain('border-loss')
    expect(t(w, 'margin-short-line').exists()).toBe(false)
    const marks = w.findAll('[data-testid="figure-hint-mark"]').map((m) => m.attributes('aria-label'))
    expect(marks).toEqual(['What is Margin needed?', 'What is Margin available?', 'What is Funds needed?'])
    // "Funds needed" as a figure row is absent: the reply has no such figure yet (REQ-081)
    expect(w.find('[data-testid="funds-needed"]').exists()).toBe(false)
  })

  it('W-193 (I-8): with the server message the shortfall text appears ONCE and the figures sentence is not repeated', async () => {
    const w = line(STATES.short)
    expect(w.findAll('[data-testid="margin-shortfall"]')).toHaveLength(1)
    expect(t(w, 'margin-figures').exists()).toBe(false)
    expect(t(w, 'margin-shortfall').text()).toBe('Not enough funds for this strategyMore') // one visible line (D-A41)
    await shortText(w)
    expect(w.text().split("Zerodha's own margin figure").length - 1).toBe(1)
    expect(t(w, 'margin-short-line').exists()).toBe(true)
  })

  it('short with the server line: shown verbatim, with both ways forward (REQ-055 AC-4)', async () => {
    const w = line(STATES.short)
    const text = await shortText(w)
    expect(text).toBe(STATES.short.shortfall_reason)
    expect(text).toContain('Reduce the quantity, review the strategy, or add funds')
    // text only: the one control is the More / Less switch; nothing places, builds or changes anything
    expect(t(w, 'margin-shortfall').findAll('a').length).toBe(0)
    expect(t(w, 'margin-shortfall').findAll('button').map((b) => b.attributes('data-testid'))).toEqual(['margin-shortfall-more'])
  })

  it('the browser never compares: figures that read needed < available with shortfall true still show the shortfall', async () => {
    const w = line(STATES.string_trap)
    expect(await shortText(w)).toBe('The server decided this one.')
    const none = line({ ...STATES.string_trap, shortfall: false, shortfall_reason: null })
    expect(t(none, 'margin-shortfall').exists()).toBe(false)
  })

  it('enough funds: the figures without a shortfall mark', async () => {
    const w = line(STATES.enough)
    expect(t(w, 'margin-figures').text()).toBe(STATES.enough.reason)
    expect(t(w, 'margin-figures').classes()).not.toContain('text-red-700')
    expect(t(w, 'margin-shortfall').exists()).toBe(false)
    expect(await hintOf(w, 'margin_available')).toContain('Checked at 16 Oct 2026, 12:08:52 IST')
  })

  it('REQ-055 AC-3: the browser adds no Zerodha label; the server text names the two figures apart', async () => {
    // W-193: on a shortfall the server's message carries the figures (once); the figures sentence is checked on `enough`
    const w = line(STATES.short)
    const shown = await shortText(w)
    expect(shown).toContain("Zerodha's own margin figure is ₹6,409.00")
    expect(shown).toContain('about ₹7,065.50 is needed (an estimate)')
    const text = t(line(STATES.enough), 'margin-figures').text()
    expect(text).toBe(STATES.enough.reason)
    expect(text).toContain("Zerodha's own margin figure is ₹6,409.00")
    expect(text).toContain('about ₹7,065.50 is needed (an estimate)')
    expect(w.text()).not.toContain('Margin (Zerodha)')
    expect(w.text()).not.toMatch(/Zerodha says/)
  })

  it('an old reply without broker_needed still renders its server line', () => {
    expect(STATES.old_reply.broker_needed).toBeUndefined()
    const w = line(STATES.old_reply)
    expect(t(w, 'margin-figures').text()).toBe(STATES.old_reply.reason)
    expect(t(w, 'margin-shortfall').exists()).toBe(true)
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
