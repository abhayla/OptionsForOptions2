// Copied/adapted from abhayla/algochanakya@bf9faf7:frontend/src/composables/useToast.js (ADR-047)
/**
 * Toast notification composable
 *
 * Simple toast notification system using browser alert() for now.
 * TODO: Replace with proper toast UI component library in future.
 */

export function useToast() {
  /**
   * Show a toast notification
   * @param {string} message - The message to display
   * @param {string} type - The type of toast (success, error, warning, info)
   */
  const showToast = (message, type = 'info') => {
    const prefix =
      {
        success: '✓',
        error: '✗',
        warning: '⚠',
        info: 'ℹ',
      }[type] || 'ℹ'

    alert(`${prefix} ${message}`)
  }

  return {
    showToast,
  }
}
