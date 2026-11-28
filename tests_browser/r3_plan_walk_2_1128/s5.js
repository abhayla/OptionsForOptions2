const { chromium } = require('playwright'); const OUT = process.env.OUT || '/tmp/claude-0/sp'; const M = 'http://127.0.0.1:4173'
;(async () => { const browser = await chromium.launch()
  const mk = async (w, h) => (await browser.newContext({ viewport: { width: w, height: h } })).newPage()
  let page = await mk(1366, 900)
  const T = async () => (await page.locator('body').innerText()).replace(/\n+/g, ' | ')
  const sh = (n, f) => page.screenshot({ path: `${OUT}/${n}.jpg`, type: 'jpeg', quality: 55, fullPage: !!f })
  const go = async (u, w = 8000) => { await page.goto(M + u); await page.waitForTimeout(w); return T() }
  // T3-01 unsaved legs line (ready-made draft)
  await go('/strategy/builder', 5000); await page.getByRole('button', { name: 'Ready-made' }).click().catch(() => {}); await page.waitForTimeout(1000)
  await page.getByRole('button', { name: 'Bull Put Spread' }).first().click(); await page.waitForTimeout(5000); let t = await T()
  console.log('T3-01 unsaved line:', (t.match(/Unsaved legs[^|]*/) || ['<none>'])[0]); await sh('t301-unsaved')
  // T3-12 dates on screens
  for (const u of ['/strategies/adjustments', '/strategies/my-strategies', '/strategies/completed-strategies', '/alerts/history', '/positions/current-positions']) { t = await go(u, 6000); console.log('T3-12', u, 'ISO dates:', (t.match(/\b20\d\d-\d\d-\d\d\b/g) || []).slice(0, 3), '| styled:', (t.match(/\b\d{1,2} [A-Z][a-z]{2} 20\d\d[^|]{0,20}/g) || []).slice(0, 2)) }
  // T2-17 closed row across screens
  t = await go('/strategies/my-strategies'); console.log('T2-17 My Strategies:', (t.match(/TC Completed Trade[^|]*\|[^|]*\|[^|]*\|[^|]*/) || ['<no row>'])[0], '| counts', (t.match(/(Completed|Running|Draft)[^|]{0,12}\d+/g) || []).slice(0, 4)); await sh('t217-my-strategies', true)
  t = await go('/strategies/completed-strategies'); console.log('T2-17 Completed:', (t.match(/TC Completed Trade[^|]*\|[^|]*\|[^|]*\|[^|]*/) || ['<no row>'])[0]); await sh('t217-completed')
  // T4-01 / T4-03 builder #1 and live card
  t = await go('/strategy/builder?strategy=1', 9000); await sh('t401-builder', true); const nm = await page.locator('text=TC Condor Running 1').first().boundingBox().catch(() => null); console.log('T4-03 builder name box width px:', nm && Math.round(nm.width))
  t = await go('/strategies/live-strategies'); await sh('t401-live', true)
  t = await go('/strategies/my-strategies'); const w2 = await page.locator('text=TC Condor Running 1').first().boundingBox().catch(() => null); console.log('T4-03 My Strategies name box width px:', w2 && Math.round(w2.width), '(9.5rem = 152 px)')
  // T3-13 D-54 playbooks page
  t = await go('/strategies/adjustments'); await page.getByRole('button', { name: 'Playbooks' }).first().click().catch(() => {}); await page.waitForTimeout(3000); t = await T(); console.log('T3-13 Playbooks:', t.slice(t.indexOf('Playbooks') + 10, t.indexOf('Playbooks') + 500), '| Test button:', await page.getByRole('button', { name: /^Test$/ }).count()); await sh('t313-playbooks')
  // T3-06 phone width drawer
  await page.close(); page = await mk(390, 844); await go('/strategy/builder?strategy=1', 8000); await page.getByRole('button', { name: /Add\/Edit/ }).first().click().catch(() => console.log('no Add/Edit at phone width')); await page.waitForTimeout(2500); t = await T()
  console.log('T3-06 Show Editor present:', /Show Editor/.test(t), '| drawer text', t.slice(t.indexOf('Add/Edit'), t.indexOf('Add/Edit') + 200)); await sh('t306-phone-drawer')
  const sc = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]); console.log('T3-06 horizontal overflow (scrollWidth, innerWidth):', sc)
  await browser.close() })()
