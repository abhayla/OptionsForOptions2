const { chromium } = require('playwright'); const OUT = '/tmp/claude-0/sp'; const M = 'http://127.0.0.1:4173'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage()
  const T = async () => (await page.locator('body').innerText()).replace(/\n+/g, ' | ')
  for (const u of ['/home/overview', '/home/active-strategies']) { await page.goto(M + u); await sleep(10000); const t = await T(); console.log(u, 'banner:', (t.match(/Market closed\.[^|]*/) || ['<none>'])[0]); console.log('   P&L/Total lines:', JSON.stringify((t.match(/(Total P&L|Paper P&L|P&L)[^|]*\|?[^|]*\|?[^|]*/g) || []).slice(0, 8)).slice(0, 900)); console.log('   Includes/left out:', JSON.stringify(t.match(/(Includes \d+ closed[^|]*|\d+ strateg[^|]*left out[^|]*)/g)), '| paused count', (t.match(/Paper P&L paused/g) || []).length); await page.screenshot({ path: `${OUT}/c14-${u.split('/').pop()}.jpg`, type: 'jpeg', quality: 55, fullPage: true }) }
  await browser.close() })()
