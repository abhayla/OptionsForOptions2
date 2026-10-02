// Page object for the app shell. Selectors use the data-testid convention; labels are asserted by the specs against the
// spec text, never read back from the app's own route table.
import type { Page, Locator } from '@playwright/test'

export class NavPage {
  constructor(readonly page: Page) {}

  get primaryNav(): Locator {
    return this.page.getByTestId('primary-nav')
  }
  get navLinks(): Locator {
    return this.primaryNav.getByRole('link')
  }
  get avatar(): Locator {
    return this.page.getByTestId('avatar-menu')
  }
  get accountMenuItems(): Locator {
    return this.page.getByTestId('account-menu-item')
  }
  get subItems(): Locator {
    return this.page.getByTestId('subitem-link')
  }
  get title(): Locator {
    return this.page.getByTestId('page-title')
  }

  navLink(label: string): Locator {
    return this.primaryNav.getByRole('link', { name: label, exact: true })
  }

  async openSection(label: string): Promise<void> {
    await this.navLink(label).click()
    await this.title.waitFor()
  }

  async openAccountMenu(): Promise<void> {
    await this.avatar.click()
    await this.page.getByTestId('account-menu').waitFor()
  }
}
