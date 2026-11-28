// Lane W2 I-10 / I-26 / I-27: the stored close on a fresh load (no broker session), banner time and index figures, per screen
const { launch, shot, body, MAIN } = require('./common')
;(async () => {
  const { browser, page } = await launch()
  for (const [n, u] of [['home', '/home/overview'], ['positions', '/positions/current-positions'], ['live', '/strategies/live-strategies'], ['mystrat', '/strategies/my-strategies'], ['builder', '/strategy/builder?strategy=1'], ['chain', '/market/option-chain'], ['alerts', '/alerts/active']]) {
    await page.goto(MAIN + u); await page.waitForTimeout(7000)
    const t = await body(page)
    console.log(n, '::', (t.match(/Market closed\. Prices are from[^|]*/) || ['<no banner>'])[0], '||', (t.match(/NIFTY 50 \| [\d.,]+ \|[^|]*/) || ['<no NIFTY index>'])[0], '||', (t.match(/Not available/gi) || []).length + ' "Not available"')
    await shot(page, 'i27-' + n)
  }
  await browser.close()
})()
