// Lane TG item 3 R2: the same cut reply on Positions > Paper
const { launch, shot, body, MAIN } = require('./common')
;(async () => {
  const { browser, page } = await launch()
  let posts = 0, cut = false
  await page.route(/\/paper\/strategies\/\d+\/orders$/, async (route) => {
    if (route.request().method() !== 'POST') return route.continue()
    posts++; cut = true; await route.fetch().catch(() => {}); await route.abort('connectionreset')
  })
  await page.route(/\/paper\/strategies(\/\d+)?(\?.*)?$/, async (route) => (cut && route.request().method() === 'GET') ? route.abort('connectionreset') : route.continue())
  await page.goto(MAIN + '/positions/current-positions?tab=paper&strategy=' + (process.env.SID || 3)); await page.waitForTimeout(9000)
  console.log('checkboxes:', await page.locator('input[type=checkbox]').count())
  await page.locator('input[type=checkbox]').nth(+(process.env.TICK || 2)).check().catch(e => console.log('tick err'))
  await page.waitForTimeout(1500)
  console.log('exit buttons:', (await page.getByRole('button').allInnerTexts()).filter(x => /^Exit/.test(x)).join(' | '))
  await page.getByRole('button', { name: /^Exit \(\d+\)$/ }).first().click(); await page.waitForTimeout(3000)
  await page.getByRole('button', { name: 'Confirm' }).last().click(); await page.waitForTimeout(15000)
  let t = await body(page)
  console.log('POSTs:', posts, '| not stored:', /not stored/i.test(t), '| line:', (t.match(/[^|]*outcome is not known[^|]*/) || ['<none>'])[0])
  await shot(page, 'r2pos-1-after-cut')
  for (let s = 20; s <= 40; s += 20) { await page.waitForTimeout(20000) }
  const b = page.getByRole('button', { name: /^Exit \(\d+\)$/ }).first()
  console.log('after 55s Exit enabled:', await b.isDisabled().then(x => !x).catch(() => 'n/a'))
  if (await b.isEnabled().catch(() => false)) { await b.click().catch(() => {}); await page.waitForTimeout(2500); await page.getByRole('button', { name: 'Confirm' }).last().click().catch(() => {}); await page.waitForTimeout(3000) }
  console.log('POSTs after second try:', posts); await shot(page, 'r2pos-2-second')
  await browser.close()
})()
