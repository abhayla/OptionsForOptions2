// ADR-330 (10): "Every exit confirmation names 'Paper' or 'Real (Zerodha order)' in its title." One title door in lib/paperDrafts.js.
// ADR-281: real orders are hidden, so no real exit button is rendered (the real title exists for the day one is built).
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'
import { positionKindWord, exitConfirmTitle, paperDialogTitle } from '@/lib/paperDrafts'

const EXIT = { key: 'k', contract_id: 5, side: 'SELL', text: 'NIFTY 3 Nov 22800 CE', lots: 2, lot_size: 65, price: '10.05', kind: 'exit' }
const ADD = { ...EXIT, key: 'a', side: 'BUY', kind: 'add' }

describe('exit title door (ADR-330 (10))', () => {
  it('positionKindWord: paper -> Paper, real -> Real (Zerodha order)', () => {
    expect(positionKindWord('paper')).toBe('Paper')
    expect(positionKindWord('real')).toBe('Real (Zerodha order)')
  })
  it('exitConfirmTitle names the kind', () => {
    expect(exitConfirmTitle('paper', [EXIT])).toContain('Paper')
    expect(exitConfirmTitle('paper', [EXIT])).toBe('Exit Paper positions')
    expect(exitConfirmTitle('real', [EXIT])).toContain('Real (Zerodha order)')
  })
  it('an unknown kind fails closed to Paper (never a blank or a real word)', () => {
    expect(positionKindWord(undefined)).toBe('Paper')
    expect(positionKindWord('x')).toBe('Paper')
  })
  it('the paper door: only exits -> the exit title; adds and mixed keep their titles', () => {
    expect(paperDialogTitle([EXIT])).toBe('Exit Paper positions')
    expect(paperDialogTitle([ADD])).toBe('Add to Paper')
    expect(paperDialogTitle([EXIT, ADD])).toBe('Review paper orders')
  })
  it('PaperConfirmDialog title: default kind paper; kind real names the Zerodha order', () => {
    const open = (props) => mount(PaperConfirmDialog, { props: { open: true, orders: [EXIT], ...props }, attachTo: document.body })
    const a = open({})
    expect(document.body.querySelector('[data-testid="modal-title"]').textContent).toBe('Exit Paper positions')
    a.unmount()
    const b = open({ kind: 'real' })
    expect(document.body.querySelector('[data-testid="modal-title"]').textContent).toContain('Real (Zerodha order)')
    b.unmount()
  })
})
