// ADR-330 (10): "Every exit confirmation names 'Paper' or 'Real (stored, not sent)' in its title." One title door in lib/paperDrafts.js.
// ADR-281: real orders are hidden, so no real exit button is rendered (the real title exists for the day one is built).
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PaperConfirmDialog from '@/components/strategy/PaperConfirmDialog.vue'
import { positionKindWord, exitConfirmTitle, paperDialogTitle } from '@/lib/paperDrafts'

const EXIT = { key: 'k', contract_id: 5, side: 'SELL', text: 'NIFTY 3 Nov 22800 CE', lots: 2, lot_size: 65, price: '10.05', kind: 'exit' }
const ADD = { ...EXIT, key: 'a', side: 'BUY', kind: 'add' }

describe('exit title door (ADR-330 (10))', () => {
  it('positionKindWord: paper -> Paper, real -> Real (stored, not sent)', () => {
    expect(positionKindWord('paper')).toBe('Paper')
    expect(positionKindWord('real')).toBe('Real (stored, not sent)')
  })
  it('exitConfirmTitle names the kind', () => {
    expect(exitConfirmTitle('paper', [EXIT])).toContain('Paper')
    expect(exitConfirmTitle('paper', [EXIT])).toBe('Exit Paper positions')
    expect(exitConfirmTitle('real', [EXIT])).toContain('Real (stored, not sent)')
  })
  it('an unknown kind throws (fail closed; round 2, more in chunk-c-round2.test.js)', () => {
    expect(() => positionKindWord(undefined)).toThrow()
    expect(() => positionKindWord('x')).toThrow()
  })
  it('the paper door: only exits -> the exit title; adds and mixed keep their titles', () => {
    expect(paperDialogTitle([EXIT])).toBe('Exit Paper positions')
    expect(paperDialogTitle([ADD])).toBe('Add to Paper')
    expect(paperDialogTitle([EXIT, ADD])).toBe('Review Paper orders')
  })
  it('PaperConfirmDialog title: default kind paper; kind real says it is stored, not sent', () => {
    const open = (props) => mount(PaperConfirmDialog, { props: { open: true, orders: [EXIT], ...props }, attachTo: document.body })
    const a = open({})
    expect(document.body.querySelector('[data-testid="modal-title"]').textContent).toBe('Exit Paper positions')
    a.unmount()
    const b = open({ kind: 'real' })
    expect(document.body.querySelector('[data-testid="modal-title"]').textContent).toContain('Real (stored, not sent)')
    b.unmount()
  })
})
