// Shared Tab / Shift+Tab trap for dialogs (Modal, Drawer). Call from the dialog's keydown handler.
const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

export function focusables(container) {
  return container ? [...container.querySelectorAll(FOCUSABLE)] : []
}

// Returns true when the key was a Tab and has been handled (focus kept inside `container`).
export function trapTab(e, container) {
  if (e.key !== 'Tab' || !container) return false
  const list = focusables(container)
  if (!list.length) {
    e.preventDefault()
    container.focus()
    return true
  }
  const first = list[0]
  const last = list[list.length - 1]
  const at = document.activeElement
  if (e.shiftKey && (at === first || at === container)) {
    e.preventDefault()
    last.focus()
  } else if (!e.shiftKey && at === last) {
    e.preventDefault()
    first.focus()
  }
  return true
}
