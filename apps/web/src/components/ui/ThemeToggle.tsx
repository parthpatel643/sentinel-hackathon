import { Moon, Sun } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useTheme } from '../../lib/useTheme'
import { cn } from '../../lib/cn'

interface ThemeToggleProps {
  className?: string
}

/** A single icon control that flips `dark` \u2194 `light` (docs/03-UX-DESIGN.md
 * section 2 — dark is the control-room default, light is the daytime
 * office/admin option). Shows the icon for the mode it switches *to*, the
 * common convention for a two-state toggle. */
export function ThemeToggle({ className }: ThemeToggleProps) {
  const { theme, toggleTheme } = useTheme()
  const { t } = useTranslation()
  const nextTheme = theme === 'dark' ? 'light' : 'dark'

  return (
    <button
      type="button"
      onClick={toggleTheme}
      title={t('theme.toggle', { theme: t(`theme.${nextTheme}`) })}
      aria-label={t('theme.toggle', { theme: t(`theme.${nextTheme}`) })}
      className={cn(
        'flex h-11 w-11 shrink-0 items-center justify-center rounded-md text-text-secondary transition-colors duration-fast hover:bg-bg-overlay hover:text-text-primary',
        className,
      )}
    >
      {theme === 'dark' ? <Sun size={17} strokeWidth={2.1} /> : <Moon size={17} strokeWidth={2.1} />}
    </button>
  )
}
