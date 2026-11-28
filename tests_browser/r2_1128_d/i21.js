// I-21 part 1: an exit blocked by a contract with no price (ADJ-02a: 23500 CE has ltp null).
const { launch, shot, text, MAIN } = require('./common')
;(async () => {
  const { browser, ctx } = await launch(); const page = await ctx.newPage()
  await page.goto(MAIN + '/positions/current-positions'); await page.waitForTimeout(5000)
  const st = async (tag) => { const b = page.locator('[data-testid=exit-selected-2]'); console.log(tag, JSON.stringify({ label: (await b.innerText()).trim(), disabled: await b.isDisabled(), reason: await text(page, '[data-testid=paper-exit-reason]') })) }
  await st('untouched'); await page.check('[data-testid=select-leg-2-57]'); await page.waitForTimeout(600); await st('unpriced leg ticked'); await shot(page, 'i21-01-unpriced-leg-ticked')
  const b = page.locator('[data-testid=exit-selected-2]'); if (!(await b.isDisabled())) { await b.click(); await page.waitForTimeout(2500); console.log('dialog:', (await page.locator('[role=dialog]').allInnerTexts()).join(' || ').replace(/\s+/g, ' ').slice(0, 700)); await shot(page, 'i21-02-exit-dialog-unpriced') }
  await page.keyboard.press('Escape'); await page.waitForTimeout(500)
  await page.check('[data-testid=select-leg-2-18]'); await page.waitForTimeout(600); await st('unpriced + priced ticked'); await shot(page, 'i21-03-both-ticked')
  await page.uncheck('[data-testid=select-leg-2-57]'); await page.waitForTimeout(600); await st('priced only'); 
  console.log('=== builder per-leg Exit on the unpriced row'); const p2 = await ctx.newPage(); await p2.goto(MAIN + '/strategy/builder?strategy=2'); await p2.waitForTimeout(5000)
  const rows = p2.locator('[data-testid=net-row]'); console.log('net rows:', (await rows.allInnerTexts()).map(s => s.replace(/\s+/g, ' ')))
  const ex = rows.nth(2).locator('[data-testid=net-exit]'); console.log('exit on 23500 CE row: disabled', await ex.isDisabled(), '| title', await ex.getAttribute('title'), '| text', (await ex.innerText()).trim())
  await shot(p2, 'i21-04-builder-net-table'); await ex.click({ timeout: 4000 }).catch(e => console.log('click:', e.message.slice(0, 80))); await p2.waitForTimeout(2500)
  console.log('builder after click:', (await p2.locator('[role=dialog]').allInnerTexts()).join(' || ').replace(/\s+/g, ' ').slice(0, 600), '| pending:', await text(p2, '[data-testid=paper-pending]')); await shot(p2, 'i21-05-builder-exit-unpriced')
  await browser.close()
})()
