// ADR-330 (19) (a): Add to Paper on an UNSAVED strategy first opens the name dialog (mode "paper"); this presses its Save with the
// prefilled name, so a test about what comes AFTER the name can go on. A strategy already saved opens no dialog: this does nothing.
import { flushPromises } from '@vue/test-utils'

export async function confirmPaperName(w) {
  const form = w.find('[data-testid="name-form"][data-mode="paper"]')
  if (!form.exists()) return
  await form.trigger('submit')
  await flushPromises()
}

// ADR-330 (28): when the page's prices are not live the confirm list carries a line to tick first; this ticks it if it is there
export async function tickNotLive(w) {
  const box = w.find('[data-testid="paper-not-live-ack"]')
  if (box.exists()) await box.setValue(true)
}
