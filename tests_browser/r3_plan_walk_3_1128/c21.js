// Lane W3: does the Review dialog's "Checking whether this exit leaves a sold option without protection..." ever resolve? ofo_tg #1 leg 1 expiry move, build a1d704225
const { chromium } = require('playwright'); const OUT = '/tmp/claude-0/sp'; const M = 'http://127.0.0.1:4173'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage()
  await page.goto(M + '/strategy/builder?strategy=1'); await sleep(8000); await page.getByLabel('Change expiry of leg 1').selectOption({ index: 1 }); await sleep(2500)
  await page.getByRole('button', { name: /Review/ }).first().click(); const t0 = Date.now()
  for (let i = 0; i < 3; i++) { await sleep(5000); const d = (await page.getByRole('dialog').first().innerText().catch(() => '')).replace(/\s+/g, ' '); console.log(`${Math.round((Date.now() - t0) / 1000)} s:`, /Checking whether this exit/.test(d) ? 'Checking... still shown' : 'resolved:', (d.match(/(Sold option with less protection[^.]*\.|Checking whether[^.]*\.\.\.|No sold option[^.]*\.|could not[^.]*\.)/) || ['<none>'])[0]) }
  await page.screenshot({ path: `${OUT}/c21-review-checking.jpg`, type: 'jpeg', quality: 55 }); await browser.close() })()
