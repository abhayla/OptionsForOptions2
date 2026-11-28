const { launch, shot, body, MAIN } = require('./common')
const LEG = 'NIFTY 9 Nov 23500 CE'
;(async () => {
  const { browser, page } = await launch(); let cut = true; const T0 = Date.now(); const ts = () => Math.round((Date.now() - T0) / 1000)
  page.on('request', (r) => { if (r.method() === 'POST' && /\/orders$/.test(r.url())) console.log(ts(), 's POST', JSON.parse(r.postData() || '{}').client_request_id) })
  await page.route(/\/paper\/strategies\/1\/orders$/, (route) => route.request().method() === 'POST' && cut ? route.abort('connectionreset') : route.continue())
  await page.goto(MAIN + '/positions/current-positions?tab=paper'); await page.waitForTimeout(8000)
  const tryExit = async () => { await page.getByRole('checkbox', { name: 'Select ' + LEG }).first().check({ timeout: 5000 }).catch(() => {}); await page.getByTestId('exit-selected-1').click({ timeout: 3000 }).catch(() => {}); await page.waitForTimeout(1500); const en = await page.getByRole('button', { name: 'Confirm' }).last().isEnabled().catch(() => false); return en }
  await tryExit(); await page.getByRole('button', { name: 'Confirm' }).last().click(); await page.waitForTimeout(4000); const cutAt = ts(); console.log(cutAt, 's cut sent'); cut = false
  await page.getByRole('button', { name: 'Cancel' }).last().click().catch(() => {})
  await page.reload(); await page.waitForTimeout(8000); const loadAt = ts(); console.log(loadAt, 's reloaded (first sight)')
  for (let i = 0; i < 12; i++) { await page.waitForTimeout(12000); const en = await tryExit(); console.log(ts(), `s (${ts() - loadAt} s after the reload, ${ts() - cutAt} s after the cut): Confirm enabled = ${en}`); if (en) { const d = (await page.getByRole('dialog').first().innerText().catch(() => '')).replace(/\s+/g, ' ').slice(-170); console.log('RELEASED; dialog tail:', d); await shot(page, 'fj2-1-released'); break } await page.getByRole('button', { name: 'Cancel' }).last().click({ timeout: 1000 }).catch(() => {}) }
  await browser.close()
})()
