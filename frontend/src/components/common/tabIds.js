// Review 6 (W-194): the ids that link a tab to its panel for screen readers. Tabs.vue gives each tab
// id=tabId(prefix, key) and aria-controls=panelId(prefix, key); the panel carries id=panelId and aria-labelledby=tabId.
export const tabId = (prefix, key) => `${prefix}-tab-${key}`
export const panelId = (prefix, key) => `${prefix}-panel-${key}`
