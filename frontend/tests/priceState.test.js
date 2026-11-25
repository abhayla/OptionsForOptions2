// B4/F1 (Phase 2 of the modular plan): ONE price-freshness rule and its wording. States: live, stale (the server says
// prices are paused), missing (not connected), closed (the server's after-close sentence), read_failed (the last book read
// failed with a book on screen: the Positions rule `listIsStale`, REQ-109 AC-5). Wording is the existing wording, not new.
import { describe, it, expect } from 'vitest'
import { effectScope, ref } from 'vue'
import {
  NOT_CONNECTED_TEXT, NOT_LIVE_EXIT, PAUSED_TEXT, bookNotLive, listIsStale, pausedText, priceState, usePriceFreshness,
} from '@/lib/priceState'
import { PAPER_NOT_CONNECTED, PAPER_PAUSED, listIsStale as listIsStaleOld } from '@/lib/paperList'
import { NOT_CONNECTED_TEXT as TRACKING_NOT_CONNECTED, pausedText as trackingPaused } from '@/lib/tracking'

const AS_OF = '2026-10-08T10:15:30+05:30'
const BOOK = { state: 'LIVE' }

describe('priceState: one state per answer', () => {
  it('live: a LIVE book read well', () => {
    expect(priceState({ readFailed: false, held: BOOK, serverState: 'LIVE' })).toBe('live')
  })
  it('stale: the server says prices are paused, with no after-close sentence', () => {
    expect(priceState({ readFailed: false, held: BOOK, serverState: 'PAUSED' })).toBe('stale')
  })
  it('missing: not connected', () => {
    expect(priceState({ readFailed: false, held: BOOK, serverState: 'NOT_CONNECTED' })).toBe('missing')
  })
  it('missing: a state the screen does not know never reads as live (fail closed)', () => {
    expect(priceState({ readFailed: false, held: BOOK, serverState: 'WEIRD' })).toBe('missing')
    expect(priceState({ readFailed: false, held: BOOK, serverState: undefined })).toBe('missing')
  })
  it('closed: paused with the server\'s after-close sentence (D-64)', () => {
    expect(priceState({ readFailed: false, held: BOOK, serverState: 'PAUSED', closedText: 'The market is closed.' })).toBe('closed')
  })
  it('read_failed: a failed read with a book on screen, whatever the old book said', () => {
    expect(priceState({ readFailed: true, held: BOOK, serverState: 'LIVE' })).toBe('read_failed')
  })
  it('a failed read with nothing on screen is not a stale book (the Positions rule)', () => {
    expect(priceState({ readFailed: true, held: null, serverState: undefined })).not.toBe('read_failed')
  })
  it('an exited book has no live price to wait for: it is not a paused one', () => {
    expect(priceState({ readFailed: false, held: BOOK, serverState: 'EXITED' })).toBe('live')
  })
})

describe('the rule and the wording each screen already had are the one in priceState', () => {
  it('listIsStale is the same function the paper list exported', () => {
    expect(listIsStaleOld).toBe(listIsStale)
    expect(listIsStale(true, {})).toBe(true)
    expect(listIsStale(true, null)).toBe(false)
    expect(listIsStale(false, {})).toBe(false)
  })
  it('the tracking and paper-list not-connected sentences are one string', () => {
    expect(TRACKING_NOT_CONNECTED).toBe(NOT_CONNECTED_TEXT)
    expect(PAPER_NOT_CONNECTED).toBe(NOT_CONNECTED_TEXT)
    expect(NOT_CONNECTED_TEXT).toBe('Paper P&L paused - live prices are not connected')
  })
  it('the paused sentence, with and without its time, is unchanged text', () => {
    expect(PAPER_PAUSED).toBe(PAUSED_TEXT)
    expect(PAUSED_TEXT).toBe('Paper P&L paused - prices not live')
    expect(pausedText(AS_OF)).toBe(`${PAUSED_TEXT}, as of 10:15:30 IST`)
    expect(trackingPaused(AS_OF)).toBe(pausedText(AS_OF))
    expect(trackingPaused(null)).toBe(pausedText(null))
  })
  it('the exit refusal sentence is the Positions one', () => {
    expect(NOT_LIVE_EXIT).toBe('Prices are not live; try again when they update')
  })
  it('bookNotLive: PAUSED and NOT_CONNECTED only', () => {
    expect(bookNotLive({ state: 'PAUSED' })).toBe(true)
    expect(bookNotLive({ state: 'NOT_CONNECTED' })).toBe(true)
    expect(bookNotLive({ state: 'LIVE' })).toBe(false)
    expect(bookNotLive(null)).toBe(false)
  })
})

describe('usePriceFreshness: the screen state a gate reads', () => {
  const run = (input) => {
    const scope = effectScope()
    const out = scope.run(() => usePriceFreshness(input))
    return { out, scope }
  }
  it('live: readOk, no exit reason', () => {
    const { out, scope } = run({ readFailed: () => false, held: () => BOOK, serverState: () => 'LIVE' })
    expect(out.state.value).toBe('live')
    expect(out.readOk.value).toBe(true)
    expect(out.exitReason.value).toBeNull()
    scope.stop()
  })
  it('stale and missing: the read is fine (the server judges the exit), the state says not live', () => {
    for (const [serverState, state] of [['PAUSED', 'stale'], ['NOT_CONNECTED', 'missing']]) {
      const { out, scope } = run({ readFailed: () => false, held: () => BOOK, serverState: () => serverState })
      expect(out.state.value).toBe(state)
      expect(out.readOk.value).toBe(true)
      scope.stop()
    }
  })
  it('closed: the same read-ok answer, the state says closed', () => {
    const { out, scope } = run({ readFailed: () => false, held: () => BOOK, serverState: () => 'PAUSED', closedText: () => 'The market is closed.' })
    expect(out.state.value).toBe('closed')
    expect(out.readOk.value).toBe(true)
    scope.stop()
  })
  it('read_failed: not readOk, exit reason is the exit sentence, and it follows the refs as they change', () => {
    const failed = ref(false)
    const book = ref(BOOK)
    const { out, scope } = run({ readFailed: failed, held: book, serverState: () => book.value?.state })
    expect(out.readOk.value).toBe(true)
    failed.value = true
    expect(out.state.value).toBe('read_failed')
    expect(out.readOk.value).toBe(false)
    expect(out.readFailed.value).toBe(true)
    expect(out.exitReason.value).toBe(NOT_LIVE_EXIT)
    book.value = null
    expect(out.readOk.value).toBe(true) // nothing on screen: nothing stale
    scope.stop()
  })
})
