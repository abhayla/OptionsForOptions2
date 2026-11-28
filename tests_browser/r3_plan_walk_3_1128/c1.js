// Lane W3 item 2: T1-20 steps 1-3, T2-06 (Greeks tab) on ofo_tg (4173), build a1d704225
const { chromium } = require('playwright'); const OUT = '/tmp/claude-0/sp'; const M = 'http://127.0.0.1:4173'
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage()
  const T = async () => (await page.locator('body').innerText()).replace(/\n+/g, ' | ')
  const sh = (n, f) => page.screenshot({ path: `${OUT}/${n}.jpg`, type: 'jpeg', quality: 55, fullPage: !!f })
  await page.goto(M + '/'); await page.waitForTimeout(9000); let t = await T()
  console.log('T1-20 step1 Home:', JSON.stringify((t.match(/Paper P&L paused[^|]*/g) || ['<none>']).slice(0, 2)), '| last price time in banner:', (t.match(/Prices are from[^|]*/) || ['<none>'])[0])
  await page.goto(M + '/strategy/builder?strategy=1'); await page.waitForTimeout(9000); t = await T()
  console.log('T1-20 step2 what-if lines:', JSON.stringify((t.match(/[^|]*(not shown while prices are not live|what-if|What-if|What if)[^|]*/gi) || ['<none>']).slice(0, 8)))
  const tabs = await page.getByRole('tab').allInnerTexts().catch(() => []); const btns = await page.getByRole('button').allInnerTexts(); console.log('tabs:', tabs.slice(0, 12), '| buttons with Greeks/Payoff:', btns.filter(b => /Greeks|Payoff|P&L Table|Full/.test(b)))
  await page.getByText('Greeks', { exact: true }).first().click({ timeout: 5000 }).catch(() => page.getByRole('button', { name: /Greeks/ }).first().click({ timeout: 5000 }).catch(() => console.log('no Greeks tab click'))); await page.waitForTimeout(3000); t = await T()
  const i = t.indexOf('Greeks'); console.log('T2-06 Greeks tab text:', t.slice(t.lastIndexOf('Payoff Graph') > 0 ? t.lastIndexOf('Payoff Graph') : 0).slice(0, 900)); await sh('c1-greeks', true)
  // T1-20 step 3: Add to Paper on a new unsaved shape, cancel
  await page.goto(M + '/strategy/builder'); await page.waitForTimeout(5000); await page.getByRole('button', { name: 'Ready-made' }).click().catch(() => {}); await page.waitForTimeout(1000)
  await page.getByRole('button', { name: 'Bull Put Spread' }).first().click().catch(() => console.log('no BPS')); await page.waitForTimeout(6000)
  await page.getByRole('button', { name: /Add to Paper/ }).first().click({ timeout: 6000 }).catch((e) => console.log('Add to Paper click:', String(e).split('\n')[0].slice(0, 90))); await page.waitForTimeout(3000)
  const d = (await page.getByRole('dialog').first().innerText().catch(() => '<no dialog>')).replace(/\s+/g, ' '); console.log('T1-20 step3 Add to Paper dialog:', d.slice(0, 700)); console.log('   tick box present:', /tick|captured price/i.test(d), '| checkboxes in dialog:', await page.getByRole('dialog').getByRole('checkbox').count()); await sh('c1-add-to-paper')
  await browser.close() })()
