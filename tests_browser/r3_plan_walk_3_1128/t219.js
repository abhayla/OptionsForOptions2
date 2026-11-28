const { chromium } = require('playwright'); const OUT = process.env.OUT || '/tmp/claude-0/sp'
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage()
  const T = async () => (await page.locator('body').innerText()).replace(/\n+/g, ' | ')
  const sh = (n) => page.screenshot({ path: `${OUT}/${n}.jpg`, type: 'jpeg', quality: 55 })
  const dlg = async () => (await page.getByRole('dialog').first().innerText().catch(() => '<none>')).replace(/\s+/g, ' ')
  const vals = async () => page.getByRole('dialog').first().locator('input:not([type=date])').evaluateAll(x => x.map(e => e.value).join(' / '))
  const S = 2
  // 1. switch T-01 off for this trade (Settings > Adjustments > this trade, step 2)
  await page.goto(`http://127.0.0.1:4173/strategies/adjustments?trade=${S}`); await page.waitForTimeout(6000)
  await page.getByText(/When to look/).first().click(); await page.waitForTimeout(1500)
  const cb = page.getByRole('checkbox', { name: /Spot within this % of a short strike/ }).first(); await cb.uncheck(); await page.waitForTimeout(500)
  await page.getByRole('button', { name: 'Save changes' }).click(); await page.waitForTimeout(4000); let t = await T(); console.log('AFTER SAVE SETTINGS:', t.slice(t.search(/Save|Saved|saved/), t.search(/Save|Saved|saved/) + 200)); await sh('t219-1-switched-off')
  // 2. plan sheet: Rs 400 stop, 15:15 time exit, Save
  await page.goto(`http://127.0.0.1:4173/strategy/builder?strategy=${S}`); await page.waitForTimeout(7000)
  await page.getByRole('button', { name: 'Edit plan' }).click(); await page.waitForTimeout(2000)
  const inputs = page.getByRole('dialog').first().locator('input:not([type=time]):not([type=date])')
  await inputs.nth(3).fill('400'); await page.getByRole('dialog').first().locator('input[type=time]').fill('15:15')
  await page.getByRole('button', { name: 'Save plan' }).click(); await page.waitForTimeout(5000)
  console.log('AFTER SAVE PLAN: dialog open?', /Save plan/.test(await dlg()), '| sentences:', (await dlg()).match(/(Saved|could not|Not confirmed|not valid)[^.]*\./g))
  if (!/Save plan/.test(await dlg())) { await page.getByRole('button', { name: 'Edit plan' }).click(); await page.waitForTimeout(2000) }
  console.log('values before reset (tgt%/tgtRs/stop%/stopRs/adj/time):', await vals()); await sh('t219-2-before-reset')
  // 3. Reset to playbook
  await page.getByRole('button', { name: 'Reset to playbook' }).first().click(); await page.waitForTimeout(1500); const ask = await dlg(); console.log('CONFIRMATION:', ask.slice(ask.indexOf('Reset to playbook puts'), ask.indexOf('Reset to playbook puts') + 420)); await sh('t219-3-confirm-ask')
  await page.getByRole('button', { name: 'Reset to playbook' }).last().click(); await page.waitForTimeout(4000)
  const d = await dlg(); console.log('AFTER RESET VALUES:', await vals()); console.log('RESET TEXT:', d.slice(d.search(/Put back|Nothing differed/), d.search(/Put back|Nothing differed/) + 700)); await sh('t219-4-after-reset')
  console.log('MARKERS (changed/switched/off in sheet):', (d.match(/[^.]*(changed|switched off|Switched on|off)[^.]*\./gi) || []).slice(0, 6))
  // 4. settings step 2 for markers
  await page.goto(`http://127.0.0.1:4173/strategies/adjustments?trade=${S}`); await page.waitForTimeout(6000); await page.getByText(/When to look/).first().click(); await page.waitForTimeout(1500)
  t = await T(); console.log('SETTINGS STEP2 markers:', (t.match(/[^|]*(changed|Changed|switched off|Switched off|Off)[^|]*/g) || []).slice(0, 8)); await sh('t219-5-settings-step2')
  console.log('T-01 checkbox now:', await cb.isChecked())
  await browser.close() })()
