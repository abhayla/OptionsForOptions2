// Lane TD helpers: one Chromium, 1366x768, small JPEG screenshots under docs/design/next-batch-2026-11-26/screens-td/
const path = require('path')
const { chromium } = require('playwright')
const OUT = path.resolve(__dirname, '../../docs/design/next-batch-2026-11-26/screens-td')
const MAIN = process.env.TD_MAIN  // origin of the preview serving the built frontend (set by the runner)
const DEAD = process.env.TD_DEAD  // origin of the preview whose /api points at a closed port
async function launch(size = { width: 1366, height: 768 }) {
  const browser = await chromium.launch()
  const ctx = await browser.newContext({ viewport: size })
  return { browser, ctx }
}
async function shot(page, name) {
  const file = path.join(OUT, name + '.jpg')
  await page.screenshot({ path: file, type: 'jpeg', quality: 55 })
  return file
}
const text = async (page, sel) => (await page.locator(sel).first().innerText().catch(() => '<absent>')).replace(/\s+/g, ' ').trim()
module.exports = { launch, shot, text, MAIN, DEAD, OUT }
