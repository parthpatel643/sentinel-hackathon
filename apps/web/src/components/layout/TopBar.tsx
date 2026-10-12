import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

interface TopBarProps {
  title: string
  subtitle?: string
  actions?: ReactNode
  /** When set, the title is also shown in the other two console languages. */
  titleKey?: string
}

const LANGUAGES = ['en', 'gu', 'hi'] as const

export function TopBar({ title, subtitle, actions, titleKey }: TopBarProps) {
  const { i18n } = useTranslation()
  const current = i18n.resolvedLanguage ?? i18n.language
  const others = titleKey ? LANGUAGES.filter((lng) => lng !== current) : []

  return (
    <header className="gb-page-head">
      <div className="min-w-0">
        <div className="gb-page-title">
          <h1>{title}</h1>
          {others.length > 0 && (
            <span className="gb-alt" aria-hidden="true">
              {others.map((lng, index) => (
                <span key={lng}>
                  {index > 0 && ' · '}
                  <span lang={lng}>{i18n.getFixedT(lng)(titleKey!)}</span>
                </span>
              ))}
            </span>
          )}
        </div>
        {subtitle && <p className="gb-page-lede">{subtitle}</p>}
      </div>
      {actions && <div className="gb-page-actions">{actions}</div>}
    </header>
  )
}
