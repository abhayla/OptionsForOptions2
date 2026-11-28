const { chromium } = require('playwright'); const OUT = '/tmp/claude-0/sp2'; const M = 'http://127.0.0.1:4173'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage()
  const dlg = async () => (await page.getByRole('dialog').first().innerText().catch(() => '<none>')).replace(/\s+/g, ' ')
  // switch T-01 off for trade 2 so Reset has something to put back
  await page.goto(`${M}/strategies/adjustments?trade=2`); await sleep(6000); await page.getByText(/When to look/).first().click(); await sleep(1500)
  const cb = page.getByRole('checkbox', { name: /Spot within this % of a short strike/ }).first(); await cb.uncheck(); await sleep(500); await page.getByRole('button', { name: 'Save changes' }).click(); await sleep(4000)
  await page.goto(`${M}/strategy/builder?strategy=2`); await sleep(7000); await page.getByRole('button', { name: 'Edit plan' }).click(); await sleep(2500)
  await page.getByRole('button', { name: 'Reset to playbook' }).first().click(); await sleep(1500); await page.getByRole('button', { name: 'Reset to playbook' }).last().click(); await sleep(4000)
  const d = await dlg(); const i = d.indexOf('Customise triggers'); console.log('sheet after reset, around the buttons:', d.slice(Math.max(0, i - 200), i + 700)); await page.screenshot({ path: `${OUT}/d4-after-reset.jpg`, type: 'jpeg', quality: 55 })
  console.log('marker sentences:', JSON.stringify(d.match(/[^.]*(Switched on again|Put back|Nothing differed|changed)[^.]*\./g)))
  await browser.close() })()
