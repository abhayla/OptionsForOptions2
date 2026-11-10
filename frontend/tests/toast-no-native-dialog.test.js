// #689: a toast is in the page; a native alert/confirm/prompt freezes the whole tab, so none is left in the source
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ToastHost from '@/components/layout/ToastHost.vue'
import { toasts, useToast } from '@/composables/useToast'

function sources(dir) {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n)
    return statSync(p).isDirectory() ? sources(p) : /\.(vue|js|ts)$/.test(n) ? [p] : []
  })
}

describe('toasts never use a native dialog (#689)', () => {
  afterEach(() => toasts.splice(0))

  it('no alert(), confirm() or prompt() call anywhere in frontend/src', () => {
    // a CALL of the browser's dialog (bare or window.), not a function of the same name being defined, nor a comment
    const call = /(?:\bwindow\.|(?<![\w.$]|function\s|async\s))(alert|confirm|prompt)\s*\([^)]*\)(?!\s*\{)/
    const offenders = sources(join(__dirname, '..', 'src')).filter((p) =>
      call.test(readFileSync(p, 'utf8').replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '')))
    expect(offenders).toEqual([])
  })

  it('showToast with an action puts an Open button in the page and never calls confirm', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm')
    const onClick = vi.fn()
    useToast().showToast('New adjustment opportunity. Open it?', 'info', { onClick })
    const w = mount(ToastHost)
    await w.vm.$nextTick()
    expect(w.get('[data-testid="toast"]').text()).toContain('New adjustment opportunity. Open it?')
    await w.get('[data-testid="toast-open"]').trigger('click')
    expect(onClick).toHaveBeenCalledOnce()
    expect(w.findAll('[data-testid="toast"]')).toHaveLength(0)
    expect(confirmSpy).not.toHaveBeenCalled()
  })

  it('Dismiss removes the toast without running its action', async () => {
    const onClick = vi.fn()
    useToast().showToast('x', 'info', { onClick })
    const w = mount(ToastHost)
    await w.vm.$nextTick()
    await w.get('[data-testid="toast-dismiss"]').trigger('click')
    expect(onClick).not.toHaveBeenCalled()
    expect(toasts).toHaveLength(0)
  })
})
