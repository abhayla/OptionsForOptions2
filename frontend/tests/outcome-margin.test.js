// ADR-099: the margin slot of the outcome screen, one test per state. The margin blocks are the backend's own MarginOut
// output (tests/fixtures/outcome-margin-states.json, written from ofo.outcome.service): 7065.50 is the recorded
// 2026-10-16 strangle basket's required total, 671.50 ADR-099's real available funds. Expected time hand-computed:
// 06:38:52 UTC + 5:30 = 12:08:52 IST. The browser shows the API strings; it never parses or compares money.
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import MarginLine from '@/components/strategy/MarginLine.vue'
import STATES from './fixtures/outcome-margin-states.json'
import CONDOR from './fixtures/outcome-condor-advanced.json'

const t = (w, id) => w.find(`[data-testid="${id}"]`)
const line = (margin) => mount(MarginLine, { props: { margin } })

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
