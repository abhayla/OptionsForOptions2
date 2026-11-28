// Lane W3 item 2: W-07 rows 49, 55, 56 on ofo_tg, build a1d704225
const { chromium } = require('playwright'); const OUT = '/tmp/claude-0/sp'; const M = 'http://127.0.0.1:4173'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage()
  const T = async () => (await page.locator('body').innerText()).replace(/\n+/g, ' | ')
  for (const [n, u] of [['Positions', '/positions/current-positions'], ['Live Strategies', '/strategies/live-strategies']]) { await page.goto(M + u); await sleep(10000); const t = await T(); console.log(`row 56 ${n}: "Prices are not live. Figures are as of" present:`, /Prices are not live\. Figures are as of/.test(t), '| banner:', (t.match(/Market closed\.[^|]*/) || ['<none>'])[0], '| repeated paused sentences:', (t.match(/Paper P&L paused/g) || []).length) }
  await page.goto(M + '/positions/current-positions'); await sleep(9000); await page.getByRole('button', { name: /^Paper$/ }).first().click().catch(() => {}); await sleep(2000)
  const cards = await page.getByRole('button', { name: /^Stops/ }).count(); await page.getByRole('button', { name: /^Stops/ }).nth(cards - 1).click(); await sleep(3000); let t = await T()
  console.log('row 55 Stops panel (leg stop on #1):', JSON.stringify((t.match(/[^|]*(left without protection|Max loss now|Max loss then)[^|]*/g) || ['<none>']).slice(0, 4)))
  await page.goto(M + '/strategy/builder?strategy=1'); await sleep(8000); await page.getByLabel('Change expiry of leg 1').selectOption({ index: 1 }); await sleep(3000)
  const ex = page.getByRole('button', { name: /^Exit$/ }); const states = await ex.evaluateAll(x => x.map(e => `${e.disabled ? 'disabled' : 'enabled'}:${e.title || ''}`)); console.log('row 49 builder Exit buttons after staging leg 1 change:', JSON.stringify(states))
  await ex.first().click({ timeout: 4000 }).catch(() => console.log('   first Exit click failed (disabled)')); await sleep(1500); t = await T(); console.log('   change-waiting sentence:', JSON.stringify((t.match(/[^|]*change waiting[^|]*/g) || ['<none>']).slice(0, 2))); await page.screenshot({ path: `${OUT}/c20-row49.jpg`, type: 'jpeg', quality: 55 })
  await browser.close() })()
