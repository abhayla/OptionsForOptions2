// --btn "Name" clicks a button, tab or checkbox by its exact name.
// Lane TC: one screen, one screenshot, text read back. node shot.mjs <name> <path> [WxH] [--click "text" ...] [--wait ms] [--full]
// Writes docs/design/next-batch-2026-11-26/screens-tc/<name>.jpg (JPEG q55, 1366x768 unless WxH) and prints the page text.
import { createRequire } from 'module'
import fs from 'fs'
const require = createRequire(import.meta.url)
const { chromium } = require('playwright')
const a = process.argv.slice(2)
const name = a[0], path = a[1]
let w = 1366, h = 768
const clicks = []
const btns = []
const scrolls = []
let wait = 6000, full = false, base = process.env.BASE || 'http://127.0.0.1:4173'
for (let i = 2; i < a.length; i++) {
  if (/^\d+x\d+$/.test(a[i])) [w, h] = a[i].split('x').map(Number)
  else if (a[i] === '--click') clicks.push(a[++i])
  else if (a[i] === '--btn') btns.push(a[++i])
  else if (a[i] === '--wait') wait = Number(a[++i])
  else if (a[i] === '--full') full = true
}
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: 1 })
const errs = []
page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 200)) })
page.on('pageerror', (e) => errs.push('pageerror: ' + String(e).slice(0, 200)))
await page.goto(base + path, { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(wait)
for (const c of clicks) {
  try { await page.getByText(c, { exact: false }).first().click({ timeout: 4000 }); await page.waitForTimeout(Number(process.env.POSTWAIT || 2500)) }
  catch (e) { console.log('CLICK FAILED: ' + c) }
}
for (const b of btns) {
  try { await page.getByRole('button', { name: b, exact: true }).first().click({ timeout: 4000 }); await page.waitForTimeout(Number(process.env.POSTWAIT || 2500)) }
  catch (e) { try { await page.getByRole('tab', { name: b, exact: true }).first().click({ timeout: 3000 }); await page.waitForTimeout(2500) } catch (e2) { try { await page.getByLabel(b, { exact: true }).first().check({ timeout: 3000 }); await page.waitForTimeout(2500) } catch (e3) { console.log('BTN FAILED: ' + b) } } }
}
const dir = process.env.SHOTDIR || 'docs/design/next-batch-2026-11-26/screens-tc'
fs.mkdirSync(dir, { recursive: true })
const file = `${dir}/${name}.jpg`
await page.screenshot({ path: file, type: 'jpeg', quality: 55, fullPage: full })
const text = await page.evaluate(() => document.body.innerText)
const bad = ['undefined', 'NaN', 'null', '[object Object]', 'Traceback'].filter((s) => text.includes(s))
console.log(`FILE ${file} (${fs.statSync(file).size} bytes) viewport ${w}x${h}`)
console.log('MUST-NOT-SHOW hits: ' + (bad.join(', ') || 'none'))
console.log('CONSOLE ERRORS: ' + (errs.join(' | ') || 'none'))
console.log('--- TEXT ---\n' + text.replace(/\n{2,}/g, '\n').slice(0, Number(process.env.MAXTXT || 2500)))
await browser.close()
