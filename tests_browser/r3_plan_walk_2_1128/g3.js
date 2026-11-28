const { chromium } = require('playwright'); const OUT = process.env.OUT || '/tmp/claude-0/sp'
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage()
  const T = async () => (await page.locator('body').innerText()).replace(/\n+/g, ' | ')
  const sh = (n, full) => page.screenshot({ path: `${OUT}/${n}.jpg`, type: 'jpeg', quality: 55, fullPage: !!full })
  // TC-3
  await page.goto('http://127.0.0.1:4173/alerts/notification-settings'); await page.waitForTimeout(5000); let t = await T(); console.log('TC-3:', t.slice(60, 700)); await sh('tc3-notification-settings')
  // W-29 (54) Positions Plan buttons
  await page.goto('http://127.0.0.1:4173/positions/current-positions'); await page.waitForTimeout(3000)
  const f = page.getByRole('button', { name: /^Paper$/ }).first(); if (await f.count()) { await f.click().catch(() => {}); await page.waitForTimeout(6000) }
  t = await T(); console.log('POSITIONS paper heads:', (t.match(/TC [A-Za-z0-9 ]+|Wide Iron Condor 20x/g) || []).slice(0, 8)); const pb = page.getByRole('button', { name: /^Plan$/ }); console.log('Plan buttons:', await pb.count())
  console.log('paused sentence count:', (t.match(/Paper P&L paused - prices not live/g) || []).length, '| "Could not open the plan":', /Could not open the plan/.test(t))
  await sh('w29-1-positions', true)
  const t0 = Date.now(); await pb.first().click(); await page.getByRole('dialog').first().waitFor({ timeout: 70000 }); console.log('Plan sheet opened in ms:', Date.now() - t0); let d = (await page.getByRole('dialog').first().innerText()).replace(/\s+/g, ' '); console.log('SHEET(1st):', d.slice(0, 260)); await sh('w29-2-plan-sheet')
  await page.getByRole('button', { name: 'Close' }).first().click(); await page.waitForTimeout(800)
  console.log('Plan buttons on page:', await pb.count())
  // no-plan trade #3 builder (Positions' Plan for unplanned)
  await page.goto('http://127.0.0.1:4173/strategy/builder?strategy=3'); await page.waitForTimeout(7000); const ep = page.getByRole('button', { name: /Edit plan|Set plan|Plan/ }).first(); console.log('trade #3 plan control:', (await page.getByRole('button').allInnerTexts()).filter(s => /plan/i.test(s)))
  // closed trade #4 builder
  await page.goto('http://127.0.0.1:4173/strategy/builder?strategy=4'); await page.waitForTimeout(7000); t = await T(); console.log('CLOSED #4:', (t.match(/This trade is closed[^|]*|Plan:[^|]*|Closed[^|]*|No plan[^|]*/g) || []).slice(0, 5), '| Plan watch heading?', /Plan watch/.test(t), '| Add/Edit?', (await page.getByRole('button', { name: 'Add/Edit' }).count()), '| Add a leg to start one?', /Add a leg to start one/.test(t)); await sh('w29-3-closed')
  // W-05 step 1 Settings Most lots
  await page.goto('http://127.0.0.1:4173/settings'); await page.waitForTimeout(5000); t = await T(); console.log('SETTINGS lots:', (t.match(/[^|]*[Mm]ost lots[^|]*\|[^|]*\|?[^|]*/g) || []).slice(0, 3)); await sh('w05-1-settings')
  await browser.close() })()
