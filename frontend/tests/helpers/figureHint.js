// GC-UI step 3b (ADR-202 (1); REQ-034 AC-7 as changed by ADR-204): a summary figure's sentence, funds line and exact
// value are lines of its "?" (FigureHint), drawn only while it is open. hintLines opens the "?", reads its lines and
// closes it again. A missing "?" THROWS, so a check built on it can never pass because the figure vanished.
export async function hintLines(w, fig) {
  const hint = w.find(`[data-testid="figure-hint"][data-figure="${fig}"]`)
  if (!hint.exists()) throw new Error(`no "?" for ${fig}`)
  await hint.find('[data-testid="figure-hint-mark"]').trigger('click')
  const lines = hint.findAll('[data-testid="figure-hint-line"]').map((l) => l.text())
  await hint.find('[data-testid="figure-hint-mark"]').trigger('click')
  return lines
}
