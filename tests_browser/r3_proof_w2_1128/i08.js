// Lane W2 I-08 (page half): the plan watch fills on the builder and on Positions; timings of the batch request on the page
const { launch, shot, body, MAIN } = require('./common')
;(async () => { const { browser, page } = await launch()
 const reqs = []; page.on('response', (r) => { if (/plan-watch/.test(r.url())) reqs.push(`${Math.round((Date.now() - T0) / 1000)}s ${r.status()} ${r.url().split('/api')[1]}`) })
 const T0 = Date.now()
 for (const [n, u] of [['builder1', '/strategy/builder?strategy=1'], ['positions', '/positions/current-positions?tab=paper']]) {
   await page.goto(MAIN + u); await page.waitForTimeout(12000)
   const t = await body(page); const i = t.indexOf('Plan watch')
   console.log(n, ':: Plan watch at', i, '|', t.slice(i, i + 420))
   await shot(page, 'i08-' + n) }
 console.log('plan-watch responses:', reqs.join(' ; ')); await browser.close() })()
