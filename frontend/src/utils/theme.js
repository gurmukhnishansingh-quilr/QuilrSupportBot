const THEME_STORAGE_KEY = 'quillyTheme'
const DEFAULT_THEME = 'light'

export function getStoredTheme() {
  const theme = localStorage.getItem(THEME_STORAGE_KEY)
  return theme === 'dark' ? 'dark' : DEFAULT_THEME
}

export function applyTheme(theme) {
  const normalized = theme === 'dark' ? 'dark' : 'light'
  document.documentElement.setAttribute('data-theme', normalized)
  localStorage.setItem(THEME_STORAGE_KEY, normalized)
  return normalized
}

export function initTheme() {
  const theme = getStoredTheme()
  applyTheme(theme)
  return theme
}
