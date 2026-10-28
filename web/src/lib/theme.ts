export type Theme = 'system' | 'light' | 'dark'
const KEY = 'di-theme'

export function getTheme(): Theme {
  try {
    const v = localStorage.getItem(KEY)
    if (v === 'light' || v === 'dark') return v
  } catch {
    /* storage unavailable: follow the system */
  }
  return 'system'
}

/** Apply a theme. data-theme is always set to a concrete value so Tailwind's dark: variant matches too. */
export function applyTheme(theme: Theme): void {
  const resolved =
    theme === 'system'
      ? window.matchMedia?.('(prefers-color-scheme: dark)').matches
        ? 'dark'
        : 'light'
      : theme
  document.documentElement.setAttribute('data-theme', resolved)
  try {
    if (theme === 'system') localStorage.removeItem(KEY)
    else localStorage.setItem(KEY, theme)
  } catch {
    /* ignore */
  }
}
