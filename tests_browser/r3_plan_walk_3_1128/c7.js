// Lane W3 item 2: T4-04 stops form and list side by side at 1536 px, Save-scroll. ofo_tg 4173, build a1d704225
const { chromium } = require('playwright'); const OUT = '/tmp/claude-0/sp'; const M = 'http://127.0.0.1:4173'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1536, height: 864 } })).newPage()
  const T = async () => (await page.locator('body').innerText()).replace(/\n+/g, ' | ')
  await page.goto(M + '/positions/current-positions'); await sleep(9000); await page.getByRole('button', { name: /^Paper$/ }).first().click().catch(() => {}); await sleep(3000)
  console.log('buttons:', (await page.getByRole('button').allInnerTexts()).filter(x => x).slice(0, 40).join(' / '))
  const st = page.getByRole('button', { name: /^Stops/ }); console.log('Stops buttons', await st.count()); await st.first().click().catch((e) => console.log('Stops click err', String(e).slice(0, 80))); await sleep(3000)
  let t = await T(); const i = t.indexOf('Stops'); console.log('stops area:', t.slice(t.indexOf('Stops panel') > 0 ? t.indexOf('Stops panel') : i, (t.indexOf('Stops panel') > 0 ? t.indexOf('Stops panel') : i) + 900))
  await page.screenshot({ path: `${OUT}/c7-stops-1536.jpg`, type: 'jpeg', quality: 55 })
  await browser.close() })()
