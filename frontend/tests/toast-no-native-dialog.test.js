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

// a CALL of the browser's dialog (bare, via window/globalThis/self, or `?.(`), not a function of the same name being
// defined, nor a comment. Known limit: the comment stripper also eats the rest of a line after a string holding //.
const call = /(?:\b(?:window|globalThis|self)\.|(?<![\w.$]|function\s|async\s))(alert|confirm|prompt)(?:\s*\?\.)?\s*\([^)]*\)(?!\s*\{)/

describe('toasts never use a native dialog (#689)', () => {
  it('the scan regex matches the call shapes and not a definition or a method of another object', () => {
    for (const hit of ["confirm('x')", "window.confirm('x')", "globalThis.confirm('x')", "self.confirm('x')", "confirm?.('x')", 'alert (1)']) {
      expect(call.test(hit), hit).toBe(true)
    }
    for (const miss of ['function confirm(x) {', 'async prompt(x) {', 'dialog.confirm(x)', 'myself.confirm(x)', 'const confirmed = 1']) {
      expect(call.test(miss), miss).toBe(false)
    }
  })

  afterEach(() => toasts.splice(0))

  it('no alert(), confirm() or prompt() call anywhere in frontend/src', () => {
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
  it('an identical toast (same message and type) is not added again; a different type is', () => {
    const { showToast } = useToast()
    showToast('same', 'info')
    showToast('same', 'info')
    showToast('same', 'warning')
    expect(toasts.map((t) => t.type)).toEqual(['info', 'warning'])
  })

  it('at most 5 stay on screen: the sixth drops the oldest', () => {
    const { showToast } = useToast()
    for (let i = 1; i <= 6; i++) showToast(`m${i}`, 'info')
    expect(toasts.map((t) => t.message)).toEqual(['m2', 'm3', 'm4', 'm5', 'm6'])
  })
})
