// Lane W3 item 3: D-TG-4 (Stop % beside Stop Rs, no "show different values" message), ofo_tg #1, build a1d704225
const { chromium } = require('playwright'); const OUT = '/tmp/claude-0/sp'; const M = 'http://127.0.0.1:4173'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage()
  const dlg = async () => (await page.getByRole('dialog').first().innerText().catch(() => '<none>')).replace(/\s+/g, ' ')
  await page.goto(M + '/strategy/builder?strategy=1'); await sleep(8000); await page.getByRole('button', { name: 'Edit plan' }).click(); await sleep(2500)
  const inputs = page.getByRole('dialog').first().locator('input:not([type=time]):not([type=date])'); console.log('values:', await inputs.evaluateAll(x => x.map(e => e.value)))
  await inputs.nth(2).fill('50'); await inputs.nth(3).fill('812.50'); await sleep(1500); let d = await dlg(); console.log('while typing, different-values sentence:', (d.match(/[^.]*show different values[^.]*\./) || ['<none>'])[0])
  await page.getByRole('button', { name: 'Save plan' }).click(); await sleep(5000); d = await dlg(); console.log('after Save plan: dialog open', /Save plan/.test(d), '| sentences:', JSON.stringify((d.match(/[^.]*(different values|could not|Saved|not valid|refused)[^.]*\./g) || []).slice(0, 4)))
  await page.screenshot({ path: `${OUT}/c10-d-tg4.jpg`, type: 'jpeg', quality: 55 })
  const r = await (await page.request.get('http://127.0.0.1:4173/api/strategies/1/adjustment-plan')).json(); console.log('stored plan stop/stop_rupees:', JSON.stringify({ stop: r.plan?.stop, stop_rupees: r.plan?.stop_rupees, stop_source: r.plan?.stop_source }))
  await browser.close() })()
