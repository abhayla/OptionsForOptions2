const { chromium } = require('playwright'); const OUT = '/tmp/claude-0/sp'; const M = 'http://127.0.0.1:4173'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage()
  const T = async () => (await page.locator('body').innerText()).replace(/\n+/g, ' | ')
  await page.goto(M + '/'); await sleep(9000); let t = await T(); const i = t.indexOf('Total P&L'); console.log('AF-05 Home:', t.slice(Math.max(0, i - 60), i + 420)); console.log('   Home all P&L lines:', JSON.stringify((t.match(/(Total P&L|P&L)[^|]*\|?[^|]*/g) || []).slice(0, 8)))
  await page.goto(M + '/strategies/my-strategies'); await sleep(8000); t = await T(); console.log('   My Strategies rows:', JSON.stringify((t.match(/TC [A-Za-z ]+\(#\d, 8 Dec\)[^|]*\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|[^|]*/g) || []).slice(0, 5)).slice(0, 900))
  await page.goto(M + '/strategy/builder?strategy=1'); await sleep(9000); t = await T(); console.log('AF-06 builder #1: "No price for:" line present:', /No price for:/.test(t), '| legs with a price:', (t.match(/NIFTY 24\d00 [PC]E 2026-12-08\t[^|]*/g) || []).slice(0, 4).map(s => s.replace(/\s+/g, ' ')), '| banner:', (t.match(/Market closed\.[^|]*/) || ['<none>'])[0])
  await browser.close() })()
