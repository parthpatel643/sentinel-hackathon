import { Bell, Camera, CloudUpload, MapPin, Search, ShieldCheck } from 'lucide-react'
import { useEffect, type ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { cn } from '../lib/cn'
import { useAuth } from '../lib/AuthContext'
import { useLowBandwidthMode } from './useLowBandwidthMode'
import { useOutboxSync } from './sync'
import { ThemeToggle } from '../components/ui/ThemeToggle'
import { LanguageSwitcher } from '../components/ui/LanguageSwitcher'
import './field-workspace.css'

const TABS = [
  { to: '/field/lookup', labelKey: 'field.nav.lookup', icon: Search },
  { to: '/field/alerts', labelKey: 'field.nav.alerts', icon: Bell },
  { to: '/field/report', labelKey: 'field.nav.report', icon: Camera },
  { to: '/field/nearby', labelKey: 'field.nav.nearby', icon: MapPin },
] as const

function timeAgo(iso: string | null, t: TFunction): string {
  if (!iso) return t('common.never')
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return t('common.justNow')
  if (seconds < 3600) return t('common.minutesAgo', { count: Math.floor(seconds / 60) })
  return t('common.hoursAgo', { count: Math.floor(seconds / 3600) })
}

/** Radically reduced layout for the Field PWA (docs/03-UX-DESIGN.md §5) —
 * a full-screen mobile shell with a bottom tab bar, not the Operator
 * Console's nav rail. Same design tokens (colours, type) as the console
 * for visual consistency, but a completely different information
 * architecture: four things, large touch targets, one-handed. */
export function FieldShell({ children }: { children: ReactNode }) {
  const { logout } = useAuth()
  const { enabled: lowBandwidth, toggle: toggleLowBandwidth } = useLowBandwidthMode()
  const { pendingCount, syncing, lastSyncedAt, refreshPendingCount } = useOutboxSync()
  const { t } = useTranslation()
  const syncLabel = syncing ? t('field.shell.syncing') : t('field.shell.lastSynced', { time: timeAgo(lastSyncedAt, t) })

  useEffect(() => {
    const refresh = () => { void refreshPendingCount() }
    window.addEventListener('sentinel:outbox-changed', refresh)
    return () => window.removeEventListener('sentinel:outbox-changed', refresh)
  }, [refreshPendingCount])

  return (
    <div className="field-workspace">
      <header className="field-header">
        <div className="field-brand-row">
            <div className="field-brand">
              <ShieldCheck size={26} aria-hidden="true" />
              <div><strong>{t('field.shell.appName')}</strong><span>{t('management:fieldWork')}</span></div>
            </div>
            <button onClick={logout} className="field-signout">{t('common.signOut')}</button>
        </div>
        <div className="field-preferences">
          <div className="flex items-center gap-1"><LanguageSwitcher /><ThemeToggle /></div>
            <button
              onClick={toggleLowBandwidth}
              aria-pressed={lowBandwidth}
              className={cn(
                'field-bandwidth rounded-md px-2 text-xs font-medium focus-visible:outline-2 focus-visible:outline-accent',
                lowBandwidth ? 'bg-accent/10 text-accent' : 'bg-bg-inset text-text-secondary hover:bg-bg-hover',
              )}
            >
              {lowBandwidth ? t('field.shell.lowBandwidthOn') : t('field.shell.lowBandwidthOff')}
            </button>
        </div>
        <div className="field-sync-strip" role="status">
          <CloudUpload size={16} aria-hidden="true" />
          <span>{syncLabel}</span>
          {pendingCount > 0 && <strong>{t('field.shell.queued', { count: pendingCount })}</strong>}
        </div>
      </header>

      <main className="field-main">{children}</main>

      <nav aria-label={t('field.shell.appName')} className="field-navigation">
        <div>
        {TABS.map(({ to, labelKey, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                'field-nav-link',
                isActive ? 'bg-accent/10 text-accent' : 'text-text-secondary hover:bg-bg-hover',
              )
            }
          >
            <Icon size={20} strokeWidth={2} aria-hidden="true" />
            {t(labelKey)}
          </NavLink>
        ))}
        </div>
      </nav>
    </div>
  )
}
