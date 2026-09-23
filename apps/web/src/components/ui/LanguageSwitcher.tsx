import { Languages } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { SUPPORTED_LANGUAGES, type SupportedLanguage } from '../../lib/i18n'
import { cn } from '../../lib/cn'

interface LanguageSwitcherProps {
  className?: string
}

/** English / Hindi / Gujarati picker — a native <select> rather than a
 * custom popover: full keyboard and screen-reader support for free, and
 * the option list is short enough that a native control loses nothing. */
export function LanguageSwitcher({ className }: LanguageSwitcherProps) {
  const { i18n, t } = useTranslation()

  return (
    <label
      className={cn(
        'flex items-center gap-1.5 rounded-md px-2 text-text-tertiary transition-colors duration-fast hover:bg-bg-overlay hover:text-text-primary',
        className,
      )}
    >
      <Languages size={16} strokeWidth={2.1} className="flex-shrink-0" />
      <span className="sr-only">{t('language.label')}</span>
      <select
        value={i18n.language}
        onChange={(e) => i18n.changeLanguage(e.target.value as SupportedLanguage)}
        aria-label={t('language.label')}
        className="h-11 min-w-0 cursor-pointer bg-transparent pr-1 text-sm font-medium text-text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
      >
        {SUPPORTED_LANGUAGES.map((lng) => (
          <option key={lng} value={lng} className="bg-bg-raised text-text-primary">
            {t(`language.${lng}`)}
          </option>
        ))}
      </select>
    </label>
  )
}
