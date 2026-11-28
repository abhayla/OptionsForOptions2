// Lane TG R2-FC2 step 5 and step 4: Positions with paused prices, closed row cells; History loading
const { launch, shot, body, MAIN } = require('./common')
;(async () => {
  const { browser, page } = await launch()
  await page.goto(MAIN + '/positions/current-positions?tab=paper'); await page.waitForTimeout(10000)
  let t = (await body(page)).split(' | ')
  console.log('paused sentence count:', t.filter(l => /Paper P&L paused - prices not live/.test(l)).length, '| first at index', t.findIndex(l => /paused - prices not live/.test(l)), '| with date and time:', JSON.stringify(t.filter(l => /paused - prices not live.*as of/.test(l)).slice(0, 2)))
  await page.getByText('Show closed positions').click(); await page.waitForTimeout(2500)
  t = (await body(page)).split(' | ')
  const i = t.findIndex(l => /TC Completed Trade/.test(l)); console.log('closed row region:', JSON.stringify(t.slice(i, i + 14)).slice(0, 700))
  await shot(page, 'fc2-closed-rows')
  await browser.close()
})()
