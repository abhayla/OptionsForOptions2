const { launch, shot, body, MAIN } = require('./common')
;(async () => {
  const { browser, page } = await launch()
  const tag = process.argv[2] || 'a'
  for (const [name, url] of [['live', '/strategies/live-strategies'], ['positions', '/positions/current-positions'], ['builder', '/strategy/builder?strategy=1']]) {
    await page.goto(MAIN + url); await page.waitForTimeout(9000)
    const t = (await body(page)).split(' | ')
    console.log('=== ' + name)
    t.forEach((l, i) => { if (/Monitoring paused|Not being watched|market is closed|Watched|being watched/i.test(l)) console.log('  ', i, t.slice(Math.max(0, i - 2), i + 3).join(' / ').slice(0, 220)) })
    await shot(page, `w34-${tag}-${name}`)
  }
  await browser.close()
})()
