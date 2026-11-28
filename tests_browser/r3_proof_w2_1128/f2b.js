const { launch, shot, body, MAIN } = require('./common')
;(async () => { const { browser, page } = await launch()
 for (const sid of [1, 3, 5]) { await page.goto(MAIN + '/strategy/builder?strategy=' + sid); await page.waitForTimeout(9000); const t = await body(page); const i = t.search(/Plan\b.{0,40}(Edit plan|Iron|Short|No plan)/); const k = t.indexOf('Edit plan'); console.log(`#${sid} plan block:`, t.slice(Math.max(0, k - 500), k + 700)); await shot(page, `f2-i197-b${sid}`) }
 await browser.close() })()
