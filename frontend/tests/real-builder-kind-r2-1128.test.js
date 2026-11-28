// Spec basis: ADR-330 point (73); coordinator 28 Nov: a missing or unknown kind opens the dialog as UNKNOWN (Confirm off, the plain reason), never as paper.
// F6: a real exit is never decided by legs (they never move); a lost reply re-sends the SAME key.
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'
import { KIND_UNREAD_LINE } from '@/lib/positionKind'

const EXIT = { key: 'k', contract_id: 5, side: 'SELL', text: 'NIFTY 22800 CE', lots: 1, lot_size: 65, price: '0', kind: 'exit' }
const open = (props) => mount(PaperConfirmDialog, { props: { open: true, orders: [EXIT], ...props }, attachTo: document.body })
const q = (id) => document.body.querySelector(`[data-testid="${id}"]`)

describe('PaperConfirmDialog with a kind nobody could read', () => {
  for (const kind of ['unknown', 'none', 'weird', '']) {
    it(`kind ${JSON.stringify(kind)}: neutral title, the plain reason, Confirm off, no paper wording`, () => {
      const w = open({ kind })
      expect(q('kind-locked').textContent).toBe(KIND_UNREAD_LINE)
      expect(q('paper-confirm-button').disabled).toBe(true)
      expect(q('paper-not-real')).toBeNull()
      expect(q('real-not-sent')).toBeNull()
      expect(document.body.textContent).not.toContain('Paper positions')
      w.unmount()
    })
  }
  it('paper and real keep Confirm available', () => {
    for (const kind of ['paper', 'real']) {
      const w = open({ kind })
      expect(q('kind-locked')).toBeNull()
      w.unmount()
    }
  })
})
