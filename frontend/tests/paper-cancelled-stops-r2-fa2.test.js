// Lane FA2 item 1 (review F3, ADR-330 (48), ADR-017): the order reply names each stop the move cancelled (`cancelled_stops`: leg, contract, level);
// the Exit/review dialog shows one line per entry from that reply alone, even when every follow-up read (stops list, book) fails.
// Real case 27 Nov 09:59: a leg moved 1 Dec to 8 Dec, its stop cancelled without a word, the moved leg had none.
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'
import { STOP_CANCELLED_LINE, STOP_REPLY_UNREADABLE_TEXT } from '@/lib/tracking'

// every read the dialog or the page makes after the post fails
vi.mock('@/services/api', () => ({ default: { get: () => Promise.reject(new Error('down')), post: () => Promise.reject(new Error('down')) } }))

const ORDERS = [{ key: 'a', kind: 'open', side: 'SELL', text: 'NIFTY 8 Dec 22650 PE', lots: 1, lot_size: 65, price: '100.00', contract_id: 9 }]
const lines = (w) => w.findAll('[data-testid="paper-cancelled-stop"]').map((l) => l.text())
const mountWith = (extra) => mount(PaperConfirmDialog, { props: { open: true, orders: ORDERS, state: 'placed', ...extra }, attachTo: document.body })

describe('F3 dialog half: cancelled stops from the reply alone', () => {
  it('list present: one line per cancelled stop, in the past tense, with the level', async () => {
    const w = mountWith({ cancelledStops: [{ leg: 'NIFTY 1 Dec 22650 PE', contract: 5574, level: '120.00' }, { leg: 'NIFTY 1 Dec 22700 CE', contract: 5575, level: '80.00' }] })
    await flushPromises()
    expect(lines(w)).toEqual([STOP_CANCELLED_LINE({ leg: 'NIFTY 1 Dec 22650 PE', level: '120.00' }), STOP_CANCELLED_LINE({ leg: 'NIFTY 1 Dec 22700 CE', level: '80.00' })])
    expect(lines(w)[0]).toBe('The stop on NIFTY 1 Dec 22650 PE (level 120.00) was removed with the move; set a new one on the new leg.')
    expect(w.find('[data-testid="paper-stops-reply-unreadable"]').exists()).toBe(false)
    w.unmount()
  })
  it('list empty: no line, nothing claimed', async () => {
    const w = mountWith({ cancelledStops: [] })
    await flushPromises()
    expect(lines(w)).toEqual([])
    expect(w.find('[data-testid="paper-stops-reply-unreadable"]').exists()).toBe(false)
    w.unmount()
  })
  it('field absent on an old reply (null): no line, nothing claimed', async () => {
    const w = mountWith({})
    await flushPromises()
    expect(lines(w)).toEqual([])
    w.unmount()
  })
  it('an entry without a leg name falls back to the contract text; one with no readable name at all is printed as "a leg", never dropped', async () => {
    const w = mountWith({ cancelledStops: [{ leg: '', contract_text: 'NIFTY 22650 PE', level: '120.00' }, { level: '5' }, null] })
    await flushPromises()
    expect(lines(w)).toEqual([
      'The stop on NIFTY 22650 PE (level 120.00) was removed with the move; set a new one on the new leg.',
      'The stop on a leg (level 5) was removed with the move; set a new one on the new leg.',
      'The stop on a leg was removed with the move; set a new one on the new leg.',
    ])
    w.unmount()
  })
  it('reply unreadable: the plain may-have-been-cancelled sentence shows', async () => {
    const w = mountWith({ stopsReplyUnreadable: true })
    await flushPromises()
    const t = w.get('[data-testid="paper-stops-reply-unreadable"]').text()
    expect(t).toBe('The stop on the old leg may have been cancelled, and the new leg has no stop until you set one.')
    expect(t).toBe(STOP_REPLY_UNREADABLE_TEXT)
    w.unmount()
  })
})
