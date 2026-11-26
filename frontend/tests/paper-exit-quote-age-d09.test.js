// D-09 (REQ-109 AC-4; GC-ICLIVE-B item 6): the Review paper orders dialog says how old the quote it shows is.
// Real case 23 Nov 2026: C4 exit of NIFTY 25500 PE showed 42.55; the quote was read 40 s before Confirm. The fill rule
// is unchanged (the server prices an exit at its own live price on Confirm); the screen only states the quote's time.
import { describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'
import { confirmRowsFor } from '@/lib/paperDrafts'
import { exitRowsFor } from '@/lib/paperList'

const QUOTE_AT = '2026-11-23T10:41:20+05:30' // 40 s before the 10:42:00 Confirm
const position = { contract_id: 501, price_state: 'live', ltp_text: '42.55', price_at: QUOTE_AT }
const text = (w) => w.get('[data-testid="paper-exit-price"]').text()
const open = (orders) => mount(PaperConfirmDialog, { props: { open: true, orders }, attachTo: document.body })

describe('D-09: an exit row states the age of the quote it shows', () => {
  it('builder Drafts exit row: "about 42.55, as of 10:41:20" and the server-sets-the-price meaning', async () => {
    const orders = [{ kind: 'exit', contract_id: 501, side: 'BUY', lots: 1, lot_size: 65, leg: { name: 'NIFTY 25500 PE' } }]
    const rows = confirmRowsFor(orders, { positions: [position] }, () => 'NIFTY 25500 PE')
    const w = open(rows)
    await flushPromises()
    expect(text(w)).toContain('about 42.55')
    expect(text(w)).toContain('as of 10:41:20')
    expect(text(w)).toContain('the server sets the exit price when you confirm')
    w.unmount()
  })
  it('Paper tab exit row carries the same time', async () => {
    const rows = exitRowsFor([{ contractId: 501, units: -65, name: 'NIFTY 25500 PE', open: true, lots: 1, lotSize: 65, ltpText: '42.55', priceAt: QUOTE_AT }])
    const w = open(rows)
    await flushPromises()
    expect(text(w)).toContain('as of 10:41:20')
    w.unmount()
  })
  it('no quote time from the server: no "as of" is shown, never a made-up time', async () => {
    const rows = confirmRowsFor([{ kind: 'exit', contract_id: 501, side: 'BUY', lots: 1, lot_size: 65, leg: {} }],
      { positions: [{ ...position, price_at: null }] }, () => 'x')
    const w = open(rows)
    await flushPromises()
    expect(text(w)).not.toContain('as of')
    expect(text(w)).toContain('about 42.55')
    w.unmount()
  })
})
