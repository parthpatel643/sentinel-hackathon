import { useEffect, useState, type ReactNode } from 'react'
import { ThemeContext, type Theme } from './useTheme'

const STORAGE_KEY = 'sentinel-theme'

function readStoredTheme(): Theme {
  const stored = localStorage.getItem(STORAGE_KEY)
  return stored === 'light' ? 'light' : 'dark'
}

/** Dark is the control room's deliberate default (docs/03-UX-DESIGN.md
 * section 2) — this only switches on an explicit operator choice, never on
 * `prefers-color-scheme`, and remembers that choice per device. */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(readStoredTheme)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem(STORAGE_KEY, theme)
  }, [theme])

  function setTheme(next: Theme) {
    setThemeState(next)
  }

  function toggleTheme() {
    setThemeState((prev) => (prev === 'dark' ? 'light' : 'dark'))
  }

  return (
    <ThemeContext.Provider value={{ theme, setTheme, toggleTheme }}>{children}</ThemeContext.Provider>
  )
}
