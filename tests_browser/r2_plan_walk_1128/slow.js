// Lane TG item 1b: delay named routes by DELAY ms; read the page at 3,7,10,14,22 s; flag the error blocks
const { launch, shot, body, MAIN } = require('./common')
const [,, name, url, pattern, delay] = process.argv
;(async () => {
  const { browser, page } = await launch()
  const t0 = Date.now(); const log = []
  await page.route(new RegExp(pattern), async (route) => {
    const s = Date.now(); const d = +delay
    await new Promise((r) => setTimeout(r, d))
    try { const resp = await route.fetch(); log.push(`${route.request().method()} ${route.request().url().replace(/^https?:\/\/[^/]+/, '')} delayed ${d}ms, server answered ${Date.now() - s - d}ms, status ${resp.status()}`); await route.fulfill({ response: resp }) } catch (e) { log.push('route err ' + e.message.slice(0, 60)) }
  })
  await page.goto(MAIN + url)
  for (const sec of [3, 7, 10, 14, 22]) {
    await page.waitForTimeout(Math.max(0, t0 + sec * 1000 - Date.now()))
    const t = await body(page)
    const hits = ['Still loading. The server is taking longer than usual to answer.', 'The page could not get an answer from the server.', 'The plan watch is not available right now.', 'Updating the numbers', 'Loading the rule check', 'No plan: nothing is watched', 'Plan watch'].filter((h) => t.includes(h))
    console.log(`${name} t=${sec}s hits:`, JSON.stringify(hits))
    if (sec === 7 || sec === 22) await shot(page, `slow-${name}-t${sec}`)
  }
  console.log(log.slice(0, 6).join('\n'))
  await browser.close()
})()
