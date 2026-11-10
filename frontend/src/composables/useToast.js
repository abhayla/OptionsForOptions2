// Copied/adapted from abhayla/algochanakya@bf9faf7:frontend/src/composables/useToast.js (ADR-047)
// Issue 689: an in-page toast list. Never the browser's native dialogs: one freezes the whole tab (live prices, later
// warnings) until someone clicks it.
import { reactive } from 'vue'

const ICON = { success: '✓', error: '✗', warning: '⚠', info: 'ℹ' }

/** The toasts on screen, oldest first; ToastHost.vue renders them. */
export const toasts = reactive([])
let nextId = 1
const MAX_ON_SCREEN = 5

export function dismissToast(id) {
  const i = toasts.findIndex((t) => t.id === id)
  if (i >= 0) toasts.splice(i, 1)
}

/** The toast's own action (its Open button): removes the toast, then runs onClick. */
export function openToast(id) {
  const t = toasts.find((x) => x.id === id)
  dismissToast(id)
  if (t?.onClick) t.onClick()
}

export function useToast() {
  /**
   * Show a toast. With `onClick` the toast carries an Open button that runs it; every toast has Dismiss.
   * @param {string} message
   * @param {string} type - success | error | warning | info
   */
  const showToast = (message, type = 'info', { onClick } = {}) => {
    // never expires (a warning must not vanish unread), so an identical one is not stacked and the oldest makes room;
    // the one box on screen takes the NEWEST action, or its Open would go to the old record
    const same = toasts.find((t) => t.message === message && t.type === type)
    if (same) {
      same.onClick = onClick || null
      return
    }
    if (toasts.length >= MAX_ON_SCREEN) toasts.shift()
    toasts.push({ id: nextId++, message, type, icon: ICON[type] || ICON.info, onClick: onClick || null })
  }

  return { showToast }
}
