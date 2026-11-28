// Lane W2 group A on the STORED path (scenario PATH-01 accepts paper orders): W2_PHASE=ok -> two stored exits, keys; W2_PHASE=cut -> reply lost after the server stored (I-14, I-181, I-188)
const { launch, shot, body, MAIN } = require('./common')
const { execSync } = require('child_process')
const T0 = Date.now(); const ts = () => Math.round((Date.now() - T0) / 1000) + 's'
const orders = () => execSync(`psql -d ofo_dev -Atc "select count(*) from paper_orders where strategy_id=1"`, { env: { ...process.env, PGPASSWORD: 'postgres_ci_dummy_pw', PGUSER: 'postgres', PGHOST: 'localhost' } }).toString().trim()
const PH = process.env.W2_PHASE || 'ok'
;(async () => {
  const { browser, page } = await launch()
  let mode = 'pass'; const keys = []
  page.on('request', (r) => { if (r.method() === 'POST' && /\/paper\/strategies\/1\/orders$/.test(r.url())) { const j = JSON.parse(r.postData() || '{}'); keys.push(j.client_request_id); console.log(ts(), 'POST key', j.client_request_id, 'rows', (j.orders || []).length) } })
  page.on('response', async (r) => { if (r.request().method() === 'POST' && /\/paper\/strategies\/1\/orders$/.test(r.url())) console.log(ts(), 'reply', r.status(), (await r.text().catch(() => '')).slice(0, 160)) })
  await page.route(/\/paper\/strategies\/1\/orders$/, async (route) => {
    if (route.request().method() !== 'POST' || mode === 'pass') return route.continue()
    await route.fetch().catch(() => {}); return route.abort('connectionreset')  // the server stores, the reply is lost
  })
  const go = async () => { await page.goto(MAIN + '/positions/current-positions?tab=paper'); await page.waitForTimeout(9000) }
  const press = async (leg, tag) => {
    await page.getByRole('checkbox', { name: 'Select ' + leg }).first().check({ timeout: 8000 })
    await page.getByTestId('exit-selected-1').click({ timeout: 4000 }); await page.waitForTimeout(2500)
    await page.getByRole('button', { name: 'Confirm' }).last().click({ timeout: 4000 }); await page.waitForTimeout(6000)
    const t = await body(page)
    console.log(ts(), tag, 'orders in DB:', orders(), '| dialog:', (await page.getByRole('dialog').first().innerText().catch(() => '<closed>')).replace(/\s+/g, ' ').slice(-230), '| page says:', (t.match(/Exit placed[^|]*/) || ['-'])[0])
  }
  await go()
  if (PH === 'ok') {
    await press('NIFTY 9 Nov 22950 PE', 'C1'); await shot(page, 'a-ok-1')
    await go(); await press('NIFTY 9 Nov 23150 PE', 'C2'); await shot(page, 'a-ok-2')
    console.log('KEYS', JSON.stringify(keys), 'distinct:', keys[0] !== keys[1])
  } else {
    mode = 'cut'; await press('NIFTY 9 Nov 23500 CE', 'CUT-after-store'); await shot(page, 'a-cut-1-dialog')
    console.log(ts(), 'body unknown line:', (await body(page)).match(/[^|]*(not known|could not confirm|Orderbook)[^|]*/i)?.[0])
    await page.waitForTimeout(140000); mode = 'pass'
    await page.reload(); await page.waitForTimeout(9000)
    const t = await body(page)
    console.log(ts(), 'after window+reload orders in DB:', orders(), '| legs left on card:', await page.getByRole('checkbox', { name: /^Select NIFTY 9 Nov (22950|23150|23500|23700)/ }).count(), '| unknown line:', (t.match(/[^|]*(not known|could not confirm|not stored|Orderbook)[^|]*/i) || ['<none>'])[0].slice(0, 200))
    await shot(page, 'a-cut-2-after-window')
    console.log('POSTs total', keys.length, 'keys', JSON.stringify(keys))
  }
  await browser.close()
})()
