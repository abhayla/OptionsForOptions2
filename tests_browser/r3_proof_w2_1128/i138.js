// Lane W2 I-138 / I-183 (page-captured request): a same-key resend after the durable claim is answered (201 replay), not 582; the same key with other orders; an unknown kind
const { launch, shot, body, MAIN } = require('./common')
const { execSync } = require('child_process')
const cnt = () => execSync(`psql -d ofo_dev -Atc "select count(*) from paper_orders where strategy_id=1"`, { env: { ...process.env, PGPASSWORD: 'postgres_ci_dummy_pw', PGUSER: 'postgres', PGHOST: 'localhost' } }).toString().trim()
;(async () => {
  const { browser, page } = await launch()
  let cap = null
  page.on('request', (r) => { if (r.method() === 'POST' && /\/paper\/strategies\/1\/orders$/.test(r.url())) cap = { url: r.url(), data: r.postData() } })
  await page.goto(MAIN + '/positions/current-positions?tab=paper'); await page.waitForTimeout(9000)
  await page.getByRole('checkbox', { name: 'Select NIFTY 9 Nov 23700 CE' }).first().check()
  await page.getByTestId('exit-selected-1').click(); await page.waitForTimeout(2500)
  await page.getByRole('button', { name: 'Confirm' }).last().click(); await page.waitForTimeout(6000)
  console.log('captured body:', cap.data, '| orders in DB after first:', cnt())
  const post = async (data, tag) => { const r = await page.request.post(cap.url, { data, headers: { 'content-type': 'application/json' } }); const t = await r.text(); console.log(tag, r.status(), t.replace(/\s+/g, ' ').slice(0, 220), '| orders in DB:', cnt()) }
  await post(cap.data, 'RESEND same key, same orders ->')
  await post(cap.data, 'RESEND again ->')
  const j = JSON.parse(cap.data); j.orders[0].quantity = String(Number(j.orders[0].quantity) + 1)
  await post(JSON.stringify(j), 'SAME key, different orders ->')
  const k = JSON.parse(cap.data); k.client_request_id = '00000000-0000-4000-8000-000000000bad'; k.orders[0].kind = 'bogus'
  await post(JSON.stringify(k), 'UNKNOWN kind, new key ->')
  await shot(page, 'i138-after'); await browser.close()
})()
