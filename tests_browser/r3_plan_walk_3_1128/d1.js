// Lane W3 item 1: the stored-close P&L and where its date is printed, on 8425feead (ofo_tg 4173)
const { chromium } = require('playwright'); const OUT = '/tmp/claude-0/sp2'; const M = 'http://127.0.0.1:4173'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage()
  const T = async () => (await page.locator('body').innerText()).replace(/\n+/g, ' | ')
  for (const [n, u] of [['Home /home/overview', '/home/overview'], ['Positions', '/positions/current-positions'], ['Live Strategies', '/strategies/live-strategies'], ['My Strategies', '/strategies/my-strategies'], ['Builder #1', '/strategy/builder?strategy=1']]) {
    await page.goto(M + u); await sleep(10000); const t = await T()
    console.log(`== ${n}: P&L figures:`, JSON.stringify((t.match(/(Total P&L|Paper P&L|P&L)[^|]{0,60}[+−-]?[\d,]+\.\d\d[^|]{0,40}/g) || []).slice(0, 5)), '| dates/times near them:', JSON.stringify((t.match(/[^|]*(as of|As of|Checked at|Prices as of|last close|stored close|15:29:58|27 Nov)[^|]*/g) || []).map(s => s.trim()).filter((v, i, a) => a.indexOf(v) === i).slice(0, 8)))
    await page.screenshot({ path: `${OUT}/d1-${n.split(' ')[0].toLowerCase()}.jpg`, type: 'jpeg', quality: 50, fullPage: true }) }
  await browser.close() })()
