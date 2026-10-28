// RD-045 / RD-048 (REQ-049 AC-4): the Advanced details table explains a health word in one sentence and a missing bid or
// ask by its short reason, both from lib/dataHealthText.js; never a bare word or a bare dash.
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import AdvancedDetails from '@/components/strategy/AdvancedDetails.vue'
import { HEALTH_UNKNOWN_SENTENCE, MISSING_REASONS, healthSentence } from '@/lib/dataHealthText'

const show = (rows) => mount(AdvancedDetails, { props: { rows, nameOf: (r) => r.instrument_id } })
const cells = (w, id) => w.findAll(`[data-testid="${id}"]`).map((c) => c.text())

describe('Advanced details: health sentence and missing-value reason', () => {
  it('RD-045: stale, unavailable, available and a missing health read as sentences, never the bare word', () => {
    const w = show([
      { instrument_id: 'a', bid: '1', ask: '2', bid_display: '1.00', ask_display: '2.00', health: 'stale' },
      { instrument_id: 'b', bid: '1', ask: '2', bid_display: '1.00', ask_display: '2.00', health: 'unavailable' },
      { instrument_id: 'c', bid: '1', ask: '2', bid_display: '1.00', ask_display: '2.00', health: 'available' },
      { instrument_id: 'd', bid: '1', ask: '2' },
    ])
    expect(cells(w, 'adv-health')).toEqual([healthSentence('stale'), healthSentence('unavailable'), 'Available', HEALTH_UNKNOWN_SENTENCE])
    expect(cells(w, 'adv-health')).not.toContain('stale')
  })

  it('RD-048: a missing bid or ask shows its short reason in place, not a dash; a present value stays as given', () => {
    const w = show([
      { instrument_id: 'a', bid: '10.50', bid_display: '10.50', ask: null, health: 'available' },
      { instrument_id: 'b', bid: null, ask: '11.00', ask_display: '11.00', health: 'stale' },
    ])
    expect(cells(w, 'adv-bid')).toEqual(['10.50', MISSING_REASONS.no_quote])
    expect(cells(w, 'adv-ask')).toEqual([MISSING_REASONS.not_sent, '11.00'])
    expect(w.text()).not.toMatch(/(^|\s)-(\s|$)/)
  })
})
