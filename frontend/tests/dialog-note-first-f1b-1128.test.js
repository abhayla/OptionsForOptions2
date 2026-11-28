// Lane F1b item 3, W-25: at 1366 x 768 the Exit all dialog's body scrolls (608 px of content in 512 px) and the sentence about the discarded staged change sat BELOW the four exit rows, out of sight
// while Confirm was in view (measured in a browser, 28 Nov: the note was not on screen). The note now comes before the rows, so it is always in the first screen of the body.
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'

const orders = ['A', 'B', 'C', 'D'].map((t, i) => ({ key: `r${i}`, side: 'SELL', text: `NIFTY ${t}`, lots: 2, lot_size: 65, price: '101.25', kind: 'exit', contract_id: 700 + i }))
describe('W-25 the discard note is before the rows', () => {
  it('note present: it precedes the order list in the document; absent: nothing is printed', () => {
    const w = mount(PaperConfirmDialog, { props: { open: true, orders, note: 'Exit all closes every open leg. The change waiting on NIFTY A is not sent and will be discarded.', strategyId: 5 }, attachTo: document.body })
    const note = document.querySelector('[data-testid="paper-discard-note"]')
    const list = document.querySelector('[data-testid="paper-orders"]')
    expect(note).not.toBeNull()
    expect(note.compareDocumentPosition(list) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    w.unmount()
    const w2 = mount(PaperConfirmDialog, { props: { open: true, orders, strategyId: 5 }, attachTo: document.body })
    expect(document.querySelector('[data-testid="paper-discard-note"]')).toBeNull()
    w2.unmount()
  })
})
