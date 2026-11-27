// I-86: with the API stopped every list shows its message; start the API, press Retry; screenshots. Same flag protocol as i20.
const fs = require('fs'); const { launch, shot, text, MAIN } = require('./common')
const wait = async (n) => { fs.writeFileSync(`/tmp/ofo-td/ready-${n}`, ''); while (!fs.existsSync(`/tmp/ofo-td/go-${n}`)) await new Promise(r => setTimeout(r, 500)) }
const LISTS = [['my-strategies', '/strategies/my-strategies'], ['live-strategies', '/strategies/live-strategies'], ['completed-strategies', '/strategies/completed-strategies'], ['alerts-active', '/alerts/active'], ['alerts-history', '/alerts/history'], ['current-positions', '/positions/current-positions'], ['adjustment-opportunities', '/positions/adjustment-opportunities'], ['adjustments', '/strategies/adjustments'], ['option-chain', '/market/option-chain'], ['home-overview', '/home/overview']]
;(async () => {
  const { browser, ctx } = await launch(); const pages = {}
  await wait(10)  // shell: API already stopped before go-10
  for (const [k, u] of LISTS) { const p = await ctx.newPage(); pages[k] = p; await p.goto(MAIN + u); }
  await new Promise(r => setTimeout(r, 9000))
  for (const [k] of LISTS) {
    const p = pages[k]; const body = (await text(p, '[data-testid=app-content]')).slice(0, 360)
    const retry = await p.locator('button:has-text("Retry"), button:has-text("Try again")').evaluateAll(e => e.map(x => x.textContent.trim()))
    console.log(`DOWN ${k}: retry buttons=${JSON.stringify(retry)} | ${body}`); await shot(p, `i86-down-${k}`)
  }
  await wait(11)  // shell: start API
  await new Promise(r => setTimeout(r, 2000))
  for (const [k] of LISTS) {
    const p = pages[k]; const b = p.locator('button:has-text("Retry"), button:has-text("Try again")').first()
    const had = await b.count(); if (had) await b.click().catch(e => console.log('retry click fail', k, e.message.slice(0, 60)))
    await p.waitForTimeout(3500)
    const body = (await text(p, '[data-testid=app-content]')).slice(0, 260); const still = await p.locator('button:has-text("Retry")').count()
    console.log(`RETRY ${k}: hadRetry=${had} retryAfter=${still} | ${body}`); await shot(p, `i86-retry-${k}`)
  }
  await browser.close()
})()
