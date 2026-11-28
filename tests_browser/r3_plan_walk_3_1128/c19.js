// Lane W3 item 2: T1-20 step 2 / D-37, the what-if Target block with prices not live. ofo_tg #1, build a1d704225
const { chromium } = require('playwright'); const OUT = '/tmp/claude-0/sp'; const M = 'http://127.0.0.1:4173'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1366, height: 1100 } })).newPage()
  const T = async () => (await page.locator('body').innerText()).replace(/\n+/g, ' | ')
  await page.goto(M + '/strategy/builder?strategy=1'); await sleep(9000)
  console.log('inputs with aria/placeholder:', JSON.stringify(await page.locator('input').evaluateAll(x => x.map(e => e.getAttribute('aria-label') || e.placeholder || e.type).filter(s => s && /level|target|date|index/i.test(s)))))
  const box = page.locator('input[aria-label="Target index level"]').first(); console.log('level box count', await page.locator('input[aria-label="Target index level"]').count())
  await box.fill('24300').catch((e) => console.log('fill err', String(e).split('\n')[0].slice(0, 80))); await box.press('Enter').catch(() => {}); await sleep(4000)
  const t = await T(); const i = t.search(/Target/); console.log('after level typed, lines with "not live"/"not shown":', JSON.stringify((t.match(/[^|]*(not shown while|prices are not live|not live)[^|]*/gi) || []).slice(0, 6)))
  console.log('Target block text:', (t.match(/Target index level[^]{0,10}|Target[^|]*\|[^|]*not[^|]*/g) || ['<none>']).slice(0,3)); const tb = await page.locator('input[aria-label="Target index level"]').first().locator('xpath=ancestor::section[1] | ancestor::div[3]').first().innerText().catch(() => '<no block>'); console.log('block:', tb.replace(/\s+/g, ' ').slice(0, 700)); await page.screenshot({ path: `${OUT}/c19-target.jpg`, type: 'jpeg', quality: 55 })
  await browser.close() })()
