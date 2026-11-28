// I-66: two Chromium tabs. Change the trade in tab A (rename, then add a stop), read the summary cards in tab B without reload.
const { launch, shot, text, MAIN } = require('./common')
const cards = async (p) => ({ name: await text(p, '[data-testid=paper-group-name]'), tag: await text(p, '[data-testid=paper-tag]'), status: await text(p, '[data-testid=paper-status-word]'), count: await text(p, '[data-testid=paper-count]'), summary: (await text(p, '[data-testid=paper-summary]')).slice(0, 200) })
;(async () => {
  const { browser, ctx } = await launch(); const B = await ctx.newPage(); const A = await ctx.newPage()
  await B.goto(MAIN + '/positions/current-positions'); await B.waitForTimeout(4000)
  console.log('B before :', JSON.stringify(await cards(B))); await shot(B, 'i66-01-tabB-before')
  await A.goto(MAIN + '/strategy/builder?strategy=1'); await A.waitForTimeout(4500)
  await A.click('[data-testid=more-menu]'); await A.click('[data-testid=rename-open]'); await A.waitForTimeout(500)
  const inp = A.locator('[role=dialog] input').first(); await inp.fill('Renamed in A'); await A.getByRole('button', { name: 'Save' }).last().click(); await A.waitForTimeout(2500)
  console.log('A name now:', await text(A, '[data-testid=strategy-card-name]'))
  for (const s of [5, 20, 40]) { await B.waitForTimeout(s === 5 ? 5000 : 15000 + (s === 40 ? 5000 : 0)); console.log(`B after ${s}s, no reload:`, JSON.stringify(await cards(B))) }
  await B.bringToFront(); await shot(B, 'i66-02-tabB-after-no-reload')
  await B.reload(); await B.waitForTimeout(4000); console.log('B after reload :', JSON.stringify(await cards(B))); await shot(B, 'i66-03-tabB-after-reload')
  // put the name back
  await A.click('[data-testid=more-menu]'); await A.click('[data-testid=rename-open]'); await A.waitForTimeout(400); await A.locator('[role=dialog] input').first().fill('Scenario ADJ-02'); await A.getByRole('button', { name: 'Save' }).last().click(); await A.waitForTimeout(1500)
  await browser.close()
})()
