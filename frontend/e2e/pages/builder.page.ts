// W-192 (ADR-193 PR-2a): the Builder's left column moved several controls into containers. These helpers open the
// container first; the assertions stay in the specs, unchanged. A helper that finds its container already open leaves it.
import type { Locator, Page } from '@playwright/test'

/** W-195: the leg picker is the left slide-in drawer behind Add/Edit (shut by default; Done or a form Add closes it). */
export async function openAddEdit(page: Page): Promise<void> {
  const toggle = page.getByTestId('add-edit')
  if ((await toggle.getAttribute('aria-expanded')) !== 'true') await toggle.click()
}

/** A leg row's Set price and Reset live in the menu beside its price field. */
export async function openPriceMenu(row: Locator): Promise<void> {
  const panel = row.getByTestId('price-menu-panel')
  if (!(await panel.isVisible())) await row.getByTestId('price-menu').click()
}

/** Save As, Rename and History live in the action row's "..." menu. */
export async function openMoreMenu(page: Page): Promise<void> {
  const panel = page.getByTestId('more-menu-panel')
  if (!(await panel.isVisible())) await page.getByTestId('more-menu').click()
}

/** W-194 (ADR-194): the full REQ-035 strategy table (and its Bid/Ask Details) sits on the chart card's P&L Table tab
 *  behind the Full table switch; the tab opens compact. */
export async function openFullTable(page: Page): Promise<void> {
  await page.getByTestId('tab-pnl').click()
  const toggle = page.getByTestId('full-table-switch')
  if (!(await toggle.isChecked())) await toggle.check()
}

/** The saved list (rows and their Open buttons) lives in the bottom card's Saved tab. */
export async function openSavedTab(page: Page): Promise<void> {
  await page.getByTestId('tab-saved').click()
}
