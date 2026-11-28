const { chromium } = require('playwright'); const M = 'http://127.0.0.1:4173'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage()
  await page.goto(M + '/strategy/builder'); await sleep(5000); await page.getByRole('button', { name: 'Ready-made' }).click().catch(() => {}); await sleep(1000)
  await page.getByRole('button', { name: 'Bull Put Spread' }).first().click(); await sleep(6000)
  console.log(await page.evaluate(() => [...document.querySelectorAll('*')].filter(e => e.children.length === 0 && /^(B|S)$/.test((e.textContent || '').trim())).slice(0, 4).map(e => `${e.tagName}|${e.className.toString().slice(0, 60)}|role=${e.getAttribute('role')}|aria=${e.getAttribute('aria-label')}|parent=${e.parentElement.tagName}:${e.parentElement.getAttribute('aria-label')}:${e.parentElement.getAttribute('title')}`)))
  await browser.close() })()
