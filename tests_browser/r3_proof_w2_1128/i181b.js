// Lane W2 I-181 part 2: the same orders after an unknown outcome and the window carry the SAME key; different orders carry a new one
const { launch, shot, body, MAIN } = require('./common')
const T0 = Date.now(); const ts = () => Math.round((Date.now() - T0) / 1000) + 's'
const posts = []
;(async () => {
  const { browser, page } = await launch()
  let mode = 'abort_before'
  page.on('request', (r) => { if (r.method() === 'POST' && /\/paper\/strategies\/\d+\/orders$/.test(r.url())) { const j = JSON.parse(r.postData() || '{}'); posts.push(j.client_request_id); console.log(ts(), 'POST key', j.client_request_id, 'rows', (j.orders || []).length) } })
  await page.route(/\/paper\/strategies\/\d+\/orders$/, (route) => route.request().method() === 'POST' && mode === 'abort_before' ? route.abort('connectionreset') : route.continue())
  const go = async () => { await page.goto(MAIN + '/positions/current-positions?tab=paper&strategy=2'); await page.waitForTimeout(8000) }
  const press = async (leg) => {
    await page.getByRole('checkbox', { name: 'Select ' + leg }).first().check({ timeout: 8000 })
    await page.getByRole('button', { name: /^Exit \(\d+\)$/ }).first().click({ timeout: 4000 }); await page.waitForTimeout(2000)
    await page.getByRole('button', { name: 'Confirm' }).last().click({ timeout: 4000 }); await page.waitForTimeout(5000)
  }
  await go(); await press('NIFTY 9 Nov 23600 CE')
  console.log(ts(), 'after cut:', (await body(page)).match(/We could not confirm[^|]*/)?.[0])
  await shot(page, 'i181-6-cut-single-leg')
  await page.waitForTimeout(135000)
  await go()                                   // reload past the window; the lock is read from storage, the book is unchanged
  mode = 'pass'
  await press('NIFTY 9 Nov 23600 CE')          // the SAME order again
  console.log(ts(), 'resend dialog after:', (await body(page)).match(/(Exit placed|Scenario mode: no orders|We could not confirm)[^|]*/)?.[0])
  await shot(page, 'i181-7-resend-same')
  console.log('KEYS', JSON.stringify(posts), 'same key on resend:', posts[0] === posts[1])
  await page.getByRole('button', { name: 'Cancel' }).last().click({ timeout: 2000 }).catch(() => {})
  await page.waitForTimeout(500)
  await go(); await press('NIFTY 9 Nov 22800 PE')   // a different order = a new Confirm
  console.log('KEYS', JSON.stringify(posts), 'new key for a different order:', posts[2] !== posts[1])
  await browser.close()
})()
