// Lane TG TC-4 / W-20 / W-29 (55): type a stop level on a bought leg, a bought call, a sold call
const { launch, shot, body, MAIN } = require('./common')
;(async () => {
  const { browser, page } = await launch()
  await page.goto(MAIN + '/positions/current-positions?tab=paper&strategy=1'); await page.waitForTimeout(10000)
  for (const [leg, lvl] of [['NIFTY 8 Dec 24000 PE', '20'], ['NIFTY 8 Dec 24400 CE', '20'], ['NIFTY 8 Dec 24300 CE', '170']]) {
    const box = page.getByLabel('Stop price for ' + leg)
    await box.fill(lvl); await page.waitForTimeout(600)
    const early = (await body(page)).split(' | ').filter(l => /Working out max loss/.test(l)).length
    await page.waitForTimeout(6000)
    const t = (await body(page)).split(' | ')
    const lines = t.filter(l => /If this stop fires|Max loss now|Max loss then|max loss becomes|less protection|no upper limit|Sold option/i.test(l)).map(l => l.slice(0, 260))
    console.log(`${leg} @${lvl}: working-line early=${early}`, JSON.stringify(lines))
    await shot(page, 'tc4-' + leg.replace(/\W+/g, '').slice(-8))
    await box.fill('')
  }
  await browser.close()
})()
