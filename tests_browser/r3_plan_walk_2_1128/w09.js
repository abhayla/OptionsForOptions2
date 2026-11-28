const { launch, shot, body } = require('./shot')
;(async () => { const { browser, page } = await launch(); const M = 'http://127.0.0.1:4174'
  await page.goto(M + '/'); await page.waitForTimeout(3000)
  await page.getByRole('link', { name: /^Alerts/ }).first().click(); await page.waitForTimeout(6000)
  console.log(page.url()); console.log((await body(page)).slice(0, 1200)); await shot(page, 'w09-alerts-active')
  await browser.close() })()
