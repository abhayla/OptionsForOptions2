// I-20 (T1-21 steps 1,2,4,6 + dialog during outage + builder empty state). Shell stops/starts the API between waits:
// this script writes /tmp/ofo-td/ready-N and waits for /tmp/ofo-td/go-N.
const fs = require('fs'); const { launch, shot, text, MAIN } = require('./common')
const wait = async (n) => { fs.writeFileSync(`/tmp/ofo-td/ready-${n}`, ''); while (!fs.existsSync(`/tmp/ofo-td/go-${n}`)) await new Promise(r => setTimeout(r, 500)) }
const exitState = async (page) => { const b = page.locator('[data-testid=exit-selected-1]'); return { label: (await b.innerText()).trim(), disabled: await b.isDisabled(), ariaDisabled: await b.getAttribute('aria-disabled'), cursor: await b.evaluate(e => getComputedStyle(e).cursor), opacity: await b.evaluate(e => getComputedStyle(e).opacity), reason: await text(page, '[data-testid=paper-exit-reason]') } }
;(async () => {
  const { browser, ctx } = await launch(); const page = await ctx.newPage()
  await page.goto(MAIN + '/positions/current-positions'); await page.waitForTimeout(4500)
  console.log('A0 untouched', JSON.stringify(await exitState(page)))
  await page.check('[data-testid=select-leg-1-18]'); await page.waitForTimeout(500)
  console.log('A1 leg ticked, API up', JSON.stringify(await exitState(page))); await shot(page, 'i20-01-ticked-api-up')
  await wait(1)  // shell: stop API
  await page.waitForTimeout(12000)
  console.log('B1 API down', JSON.stringify(await exitState(page))); await shot(page, 'i20-02-api-down-exit-grey')
  console.log('B1 paper rows:', (await page.locator('[data-testid=paper-leg]').allInnerTexts()).map(s => s.replace(/\s+/g, ' ')).join(' || ').slice(0, 400))
  console.log('B1 totals:', await text(page, '[data-testid=paper-totals]'))
  await wait(2)  // shell: start API
  await page.waitForTimeout(15000)
  console.log('C1 API back', JSON.stringify(await exitState(page))); await shot(page, 'i20-03-api-back')
  console.log('C1 tick kept:', await page.isChecked('[data-testid=select-leg-1-18]'))
  const btn = page.locator('[data-testid=exit-selected-1]')
  if (!(await btn.isDisabled())) {
    await btn.click(); await page.waitForTimeout(2500)
    console.log('D1 dialog:', (await page.locator('[role=dialog]').allInnerTexts()).join(' || ').replace(/\s+/g, ' ').slice(0, 600)); await shot(page, 'i20-04-exit-dialog-open')
    await wait(3)  // shell: stop API while the dialog is open
    await page.waitForTimeout(14000)
    console.log('E1 dialog during outage, dialogs open:', await page.locator('[role=dialog]').count(), '|', (await page.locator('[role=dialog]').allInnerTexts()).join(' || ').replace(/\s+/g, ' ').slice(0, 600)); await shot(page, 'i20-05-dialog-during-outage')
    // builder empty state with the API down, new tab
    const p2 = await ctx.newPage(); await p2.goto(MAIN + '/strategy/builder?strategy=1'); await p2.waitForTimeout(6000)
    console.log('F1 builder with API down:', (await text(p2, '[data-testid=strategy-builder]')).slice(0, 700)); await shot(p2, 'i20-06-builder-api-down'); await p2.close()
    await wait(4)  // shell: start API
    await page.waitForTimeout(15000)
    console.log('G1 after restore dialogs open:', await page.locator('[role=dialog]').count(), '| exit state', JSON.stringify(await exitState(page).catch(e => 'n/a ' + e.message.slice(0, 60)))); await shot(page, 'i20-07-after-restore')
  } else console.log('D1 Exit still disabled after restore: dialog step not run')
  await browser.close()
})()
