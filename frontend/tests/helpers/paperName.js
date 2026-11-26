// ADR-330 (19) (a): Add to Paper on an UNSAVED strategy first opens the name dialog (mode "paper"); this presses its Save with the
// prefilled name, so a test about what comes AFTER the name can go on. A strategy already saved opens no dialog: this does nothing.
import { flushPromises } from '@vue/test-utils'

export async function confirmPaperName(w) {
  const form = w.find('[data-testid="name-form"][data-mode="paper"]')
  if (!form.exists()) return
  await form.trigger('submit')
  await flushPromises()
}
