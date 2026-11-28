// Lane W3 item 3: D-TG-3 raw 409 on Positions, D-TG-5 paused sentence count, D-TG2-2 T-09 title. ofo_tg 4173, build a1d704225
const { chromium } = require('playwright'); const OUT = '/tmp/claude-0/sp'; const M = 'http://127.0.0.1:4173'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage()
  const T = async () => (await page.locator('body').innerText()).replace(/\n+/g, ' | ')
  const resp = []; page.on('response', async (r) => { if (/real|positions/.test(r.url()) && r.status() >= 400) resp.push(`${r.status()} ${r.url().replace(M, '')}`) })
  await page.goto(M + '/positions/current-positions'); await sleep(10000)
  for (const tab of ['All', 'Real', 'Paper']) { await page.getByRole('button', { name: new RegExp(`^${tab}$`) }).first().click().catch(() => {}); await sleep(3000); const t = await T()
    console.log(`D-TG-3 tab ${tab}: raw JSON markers:`, JSON.stringify(t.match(/error_class|BROKER_AUTHENTICATION|what_happened|\{ *"|\[object|undefined|NaN/g) || []), '| paused sentence count:', (t.match(/Paper P&L paused/g) || []).length, '| Real P&L text:', JSON.stringify((t.match(/Real[^|]{0,40}\|[^|]{0,160}/) || ['<none>'])[0]).slice(0, 250))
    await page.screenshot({ path: `${OUT}/c11-positions-${tab}.jpg`, type: 'jpeg', quality: 55 }) }
  console.log('responses >= 400 seen:', JSON.stringify(resp.slice(0, 6)))
  await page.goto(M + '/strategies/adjustments'); await sleep(6000); let t = await T(); console.log('D-TG2-2 Adjustments page T-09 lines:', JSON.stringify((t.match(/[^|]*close for pennies[^|]*/g) || ['<none>']).slice(0, 3)))
  await page.goto(M + '/alerts/active'); await sleep(5000); t = await T(); console.log('   Alerts Active T-09:', JSON.stringify((t.match(/[^|]*pennies[^|]*/g) || ['<none>']).slice(0, 2)))
  await page.goto(M + '/strategies/adjustments?trade=1'); await sleep(6000); await page.getByText(/When to look/).first().click().catch(() => {}); await sleep(1500); t = await T(); console.log('   When to look T-09:', JSON.stringify((t.match(/[^|]*(pennies|falls to)[^|]*/g) || ['<none>']).slice(0, 3)))
  await browser.close() })()
