// Lane TG item 3 R1: an exit whose answer never arrives (the request reaches the server, the reply is cut)
const { launch, shot, body, MAIN } = require('./common')
;(async () => {
  const { browser, page } = await launch()
  let posts = 0
  await page.route(/\/paper\/strategies\/\d+\/orders$/, async (route) => {
    if (route.request().method() !== 'POST') return route.continue()
    posts++; cut = true; await route.fetch().catch(() => {}); await route.abort('connectionreset')
  })
  let cut = false
  await page.route(/\/paper\/strategies\/\d+(\/triggers|\/exit-risk|\/armed-exits)?(\?.*)?$/, async (route) => { if (cut && route.request().method() === 'GET') return route.abort('connectionreset'); return route.continue() })
  await page.goto(MAIN + '/strategy/builder?strategy=' + (process.env.SID || 1)); await page.waitForTimeout(8000)
  console.log('buttons:', (await page.getByRole('button').allInnerTexts()).filter(x => /^Exit/.test(x)).join(' | '))
  await page.getByRole('button', { name: /^Exit$/ }).first().click(); await page.waitForTimeout(3000)
  const d = await page.getByRole('dialog').first().innerText().catch(() => '<none>')
  console.log('dialog:', d.replace(/\s+/g, ' ').slice(0, 500))
  await shot(page, 'r1b-1-dialog')
  await page.getByRole('button', { name: 'Confirm' }).last().click(); await page.waitForTimeout(15000)
  const t = await body(page)
  console.log('POSTs after first Confirm:', posts)
  console.log('says not stored:', /not stored/i.test(t), '| unknown-line:', (t.match(/[^|]*(outcome|not known|being checked)[^|]*/gi) || ['<none>']).slice(0, 3).join(' ;; '))
  await shot(page, 'r1b-2-after-cut')
  for (let s = 20; s <= 60; s += 20) { await page.waitForTimeout(20000); const tt = await body(page); console.log(`t+${s}s unlocked?`, await page.getByRole('button', { name: /^Exit$/ }).first().isDisabled().then(x => !x).catch(() => 'n/a'), 'not stored:', /not stored/i.test(tt)) }
  const ex = page.getByRole('button', { name: /^Exit$/ }).first()
  if (!(await ex.isDisabled().catch(() => true))) { await ex.click().catch(() => {}); await page.waitForTimeout(2500); await page.getByRole('button', { name: 'Confirm' }).last().click().catch(() => {}); await page.waitForTimeout(3000) }
  console.log('POSTs after second try:', posts)
  await shot(page, 'r1b-3-second-try')
  await browser.close()
})()
