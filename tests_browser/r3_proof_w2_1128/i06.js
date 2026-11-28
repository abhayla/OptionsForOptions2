// Lane W2 I-06 / I-118 (page half): the monitoring badge and its reason, per screen; worker up, then worker stopped (second run: W2_TAG=down)
const { launch, shot, body, MAIN } = require('./common')
const TAG = process.env.W2_TAG || 'up'
const pick = (t) => (t.match(/(Monitoring paused|Not being watched[^|]*|Health unknown|Watching[^|]*|The market is closed[^|]*|no worker[^|]*|Since \d\d:\d\d|Paper P&L paused[^|]*)/gi) || []).join(' ## ')
;(async () => {
  const { browser, page } = await launch()
  for (const [name, url] of [['live', '/strategies/live-strategies'], ['positions', '/positions/current-positions?tab=paper'], ['builder1', '/strategy/builder?strategy=1'], ['builder3', '/strategy/builder?strategy=3'], ['mystrat', '/strategies/my-strategies'], ['home', '/'], ['alerts', '/alerts/active']]) {
    await page.goto(MAIN + url); await page.waitForTimeout(8000)
    const t = await body(page)
    console.log(`[${TAG}] ${name}: ${pick(t).slice(0, 700)}`)
    await shot(page, `i06-${TAG}-${name}`)
  }
  await browser.close()
})()
