const path = require('path'), fs = require('fs')
const { chromium } = require('playwright')
const OUT = path.resolve(__dirname, '../../docs/design/next-batch-2026-11-26/screens-tg2')
async function launch(size = { width: 1366, height: 768 }) {
  const browser = await chromium.launch(); const ctx = await browser.newContext({ viewport: size }); const page = await ctx.newPage()
  return { browser, ctx, page } }
async function shot(page, name, full = false) {
  const file = path.join(OUT, name + '.jpg'); let q = 60
  for (;;) { await page.screenshot({ path: file, type: 'jpeg', quality: q, fullPage: full }); if (fs.statSync(file).size < 290000 || q <= 20) break; q -= 10 }
  return file }
const body = async (page) => (await page.locator('body').innerText()).replace(/\n+/g, ' | ')
module.exports = { launch, shot, body, OUT, MAIN: process.env.TG_MAIN || 'http://127.0.0.1:4173' }
