// Lane W2 I-181 on the BUILDER's Exit (strategy 1, scenario): a key per Confirm; same key on the resend after the window; a new one after a refusal
const { launch, shot, body, MAIN } = require('./common')
const T0 = Date.now(); const ts = () => Math.round((Date.now() - T0) / 1000) + 's'
const keys = []
;(async () => {
  const { browser, page } = await launch()
  let mode = 'pass'
  page.on('request', (r) => { if (r.method() === 'POST' && /\/paper\/strategies\/\d+\/orders$/.test(r.url())) { const j = JSON.parse(r.postData() || '{}'); keys.push(j.client_request_id); console.log(ts(), 'POST key', j.client_request_id, 'rows', (j.orders || []).length) } })
  await page.route(/\/paper\/strategies\/\d+\/orders$/, (route) => route.request().method() === 'POST' && mode === 'abort' ? route.abort('connectionreset') : route.continue())
  const go = async () => { await page.goto(MAIN + '/strategy/builder?strategy=1'); await page.waitForTimeout(9000) }
  const press = async () => {
    await page.getByRole('button', { name: /^Exit$/ }).first().click({ timeout: 5000 }); await page.waitForTimeout(2500)
    await page.getByRole('button', { name: 'Confirm' }).last().click({ timeout: 4000 }); await page.waitForTimeout(5000)
    console.log(ts(), 'dialog tail:', (await page.getByRole('dialog').first().innerText().catch(() => '<closed>')).replace(/\s+/g, ' ').slice(-260))
    await page.getByRole('button', { name: 'Cancel' }).last().click({ timeout: 1500 }).catch(() => {}); await page.waitForTimeout(500)
  }
  await go(); await press(); await shot(page, 'i181-8-builder-c1')
  await page.reload(); await page.waitForTimeout(9000); await press()
  console.log('builder: two Confirms, keys', JSON.stringify(keys), 'different:', keys[0] !== keys[1])
  mode = 'abort'; await go(); await press(); await shot(page, 'i181-9-builder-cut')
  const k3 = keys[keys.length - 1]
  await page.waitForTimeout(135000); mode = 'pass'; await go(); await press(); await shot(page, 'i181-10-builder-resend')
  console.log('builder resend after window: key', keys[keys.length - 1], 'equals cut key:', keys[keys.length - 1] === k3)
  await browser.close()
})()
