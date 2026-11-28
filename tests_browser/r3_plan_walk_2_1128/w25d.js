const { chromium } = require('playwright'); const { execSync } = require('child_process'); const fs = require('fs'); const OUT = process.env.OUT || '/tmp/claude-0/sp'; const M = 'http://127.0.0.1:4173'
const ST = '/home/user/OptionsForOptions2/tests_browser/r3_plan_walk_2_1128'
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage()
  const sh = (n) => page.screenshot({ path: `${OUT}/${n}.jpg`, type: 'jpeg', quality: 55 })
  const dlg = async () => (await page.getByRole('dialog').first().innerText({ timeout: 2500 }).catch(() => '<no dialog>')).replace(/\s+/g, ' ')
  await page.goto(M + '/strategy/builder?strategy=1'); await page.waitForTimeout(10000)
  process.kill(Number(fs.readFileSync('/tmp/claude-0/api-tg.pid', 'utf8').trim())); await page.waitForTimeout(4000)
  const ex = page.getByRole('button', { name: /^Exit$/ })
  console.log('API down 4 s, builder per-leg Exit buttons:', await ex.evaluateAll(x => x.map(e => (e.disabled ? 'disabled' : 'enabled') + '/title=' + (e.title || '') + '/class=' + (e.className.match(/disabled|opacity-\d+|cursor-not-allowed/g) || []).join(','))))
  await sh('w25d3-builder-api-down')
  await ex.first().click({ timeout: 4000 }).catch((e) => console.log('click failed:', String(e).split('\n')[0].slice(0, 140))); await page.waitForTimeout(3000); console.log('dialog:', (await dlg()).slice(0, 500)); await sh('w25d3-dialog')
  const cf = page.getByRole('button', { name: /^Confirm$/ }); console.log('Confirm count/enabled:', await cf.count(), await cf.first().isEnabled().catch(() => 'n/a'))
  execSync(`bash ${ST}/api_start.sh tg`); await page.waitForTimeout(20000)
  await browser.close() })()
