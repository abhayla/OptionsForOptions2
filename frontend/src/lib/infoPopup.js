// ADR-330 (3b): the ONE info pop-up. A short message that disappears by itself (kept only in History server-side). Every caller
// uses showInfo; useToast.js keeps the list and is imported only here and by ToastHost.vue (guard tests/one-popup-module.test.js).
import { dismissToast, useToast } from '@/composables/useToast'

/** How long an info pop-up stays on screen. The one home of this number. */
export const INFO_POPUP_MS = 6000

/** Show an info pop-up that dismisses itself after INFO_POPUP_MS. With `onClick` it also carries an Open button. */
export function showInfo(text, { onClick } = {}) {
  const id = useToast().showToast(text, 'info', { onClick })
  setTimeout(() => dismissToast(id), INFO_POPUP_MS)
}
