// Spec basis: ADR-330 point (73) (owner 28 Nov: real and paper same screens; a real action is only stored, nothing sent to Zerodha); ADR-016 to ADR-019; ADR-281.
// Lane R2: the confirm dialog of a REAL position says before the press that the action is only stored, never "placing" or "placed";
// the paper dialog is unchanged. No sentence of the real set claims an order exists.
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'
import * as K from '@/lib/positionKind'
import { EXIT_DONE_TEXT, exitEndText } from '@/lib/usePaperExit'

const EXIT = { key: 'k', contract_id: 5, side: 'SELL', text: 'NIFTY 3 Nov 22800 CE', lots: 2, lot_size: 65, price: '0', kind: 'exit' }
const ADD = { ...EXIT, key: 'a', side: 'BUY', kind: 'add', price: '10.05' }
const open = (props) => mount(PaperConfirmDialog, { props: { open: true, orders: [EXIT], ...props }, attachTo: document.body })
const body = () => document.body.textContent

describe('PaperConfirmDialog kind real', () => {
  it('exit rows: the stored-only sentence shows before the press; Confirm is the same button', () => {
    const w = open({ kind: 'real' })
    expect(document.body.querySelector('[data-testid="real-not-sent"]').textContent).toBe(K.REAL_EXIT_DIALOG_TEXT)
    expect(document.body.querySelector('[data-testid="paper-not-real"]')).toBeNull()
    expect(document.body.querySelector('[data-testid="paper-confirm-button"]')).not.toBeNull()
    w.unmount()
  })
  it('add rows: the add sentence, not the exit one', () => {
    const w = open({ kind: 'real', orders: [ADD] })
    expect(document.body.querySelector('[data-testid="real-not-sent"]').textContent).toBe(K.REAL_ADD_DIALOG_TEXT)
    w.unmount()
  })
  it('while the post runs it says storing, never placing; after a stored answer it says stored, not sent', () => {
    const busy = open({ kind: 'real', busy: true })
    expect(body()).toContain(K.REAL_STORING_TEXT)
    expect(body()).not.toContain('Placing exit')
    busy.unmount()
    const placed = open({ kind: 'real', state: 'placed' })
    expect(document.body.querySelector('[data-testid="paper-placed"]').textContent).toBe(K.REAL_STORED_NOT_REFRESHED_TEXT)
    expect(document.body.querySelector('[data-testid="paper-placed"]').textContent).toContain(K.NOT_SENT_LINE)
    placed.unmount()
  })
  it('paper is unchanged: the not-a-real-trade line, Placing exit, Placed on paper', () => {
    const p = open({ busy: true })
    expect(document.body.querySelector('[data-testid="paper-not-real"]').textContent).toContain('not a real trade')
    expect(document.body.querySelector('[data-testid="real-not-sent"]')).toBeNull()
    expect(body()).toContain('Placing exit')
    p.unmount()
    const q = open({ state: 'placed' })
    expect(document.body.querySelector('[data-testid="paper-placed"]').textContent).toContain('Placed on paper')
    q.unmount()
  })
})

describe('the done line and the sentence set', () => {
  it('a real exit is "Exit stored ... Not sent to Zerodha", with no order number; paper keeps "Exit placed on paper"', () => {
    expect(exitEndText('done', ['NIFTY 22800 CE'], { kind: 'real', orders: [{ id: 5 }], sent: 1 })).toBe(`NIFTY 22800 CE: ${K.REAL_EXIT_STORED_TEXT}`)
    expect(exitEndText('done', ['NIFTY 22800 CE'], { kind: 'paper', orders: [{ id: 5 }], sent: 1 })).toContain(EXIT_DONE_TEXT)
    expect(exitEndText('done', [], { orders: [{ id: 5 }], sent: 1 })).toContain(EXIT_DONE_TEXT)
  })
  it('every real sentence says nothing is sent or only stored; none says placed, executed or sent to Zerodha without a "not"', () => {
    const sentences = [K.REAL_EXIT_DIALOG_TEXT, K.REAL_ADD_DIALOG_TEXT, K.REAL_EXIT_STORED_TEXT, K.REAL_STOPS_TEXT, K.REAL_ROW_TEXT, K.REAL_STORED_NOT_REFRESHED_TEXT]
    for (const s of sentences) {
      expect(s).not.toMatch(/\b(placed|executed|filled)\b/i)
      expect(/(not sent|nothing is sent|does not place|are not sent|only)/i.test(s) || /^Watching/.test(s) || /^Stored in the app/.test(s)).toBe(true)
    }
    expect(K.REAL_STORING_TEXT).not.toMatch(/placing|placed/i)
  })
})
