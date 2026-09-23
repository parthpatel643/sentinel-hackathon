import { Bell, Camera, MapPin, Search, ShieldCheck } from 'lucide-react'
import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { cn } from '../lib/cn'
import { useAuth } from '../lib/AuthContext'
import { useLowBandwidthMode } from './useLowBandwidthMode'
import { useOutboxSync } from './sync'
import { ThemeToggle } from '../components/ui/ThemeToggle'
import { LanguageSwitcher } from '../components/ui/LanguageSwitcher'

const TABS = [
  { to: '/field/alerts', labelKey: 'field.nav.alerts', icon: Bell },
  { to: '/field/lookup', labelKey: 'field.nav.lookup', icon: Search },
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
  const { pendingCount, syncing, lastSyncedAt } = useOutboxSync()
  const { t } = useTranslation()
  const syncLabel = syncing ? t('field.shell.syncing') : t('field.shell.lastSynced', { time: timeAgo(lastSyncedAt, t) })

  return (
    <div className="flex h-dvh w-full flex-col overflow-hidden bg-bg-base text-text-primary">
      <header className="flex-shrink-0 border-b border-border-subtle bg-bg-raised pt-[env(safe-area-inset-top)]">
        <div className="mx-auto flex w-full max-w-3xl flex-col px-4">
          <div className="flex flex-wrap items-start justify-between gap-3 py-3">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 text-base font-semibold">
                <ShieldCheck size={22} className="shrink-0 text-accent" aria-hidden="true" />
                <span>{t('field.shell.appName')}</span>
              </div>
              <p role="status" className="mt-1 text-xs leading-relaxed text-text-secondary">
                {syncLabel}
                {pendingCount > 0 && <span className="ml-2 font-medium text-accent">{t('field.shell.queued', { count: pendingCount })}</span>}
              </p>
            </div>
            <button
              onClick={toggleLowBandwidth}
              aria-pressed={lowBandwidth}
              className={cn(
                'min-h-10 shrink-0 rounded-md px-2 text-xs font-medium focus-visible:outline-2 focus-visible:outline-accent',
                lowBandwidth ? 'bg-accent/10 text-accent' : 'bg-bg-inset text-text-secondary hover:bg-bg-hover',
              )}
            >
              {lowBandwidth ? t('field.shell.lowBandwidthOn') : t('field.shell.lowBandwidthOff')}
            </button>
          </div>
          <div className="flex items-center justify-between gap-2 border-t border-border-subtle py-2">
            <div className="flex items-center gap-1">
              <LanguageSwitcher />
              <ThemeToggle />
            </div>
            <button
              onClick={logout}
              className="min-h-10 rounded-md px-3 text-sm text-text-secondary hover:bg-bg-hover focus-visible:outline-2 focus-visible:outline-accent"
            >
              {t('common.signOut')}
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto min-h-0 w-full max-w-3xl flex-1 overflow-y-auto overscroll-contain">{children}</main>

      <nav aria-label={t('field.shell.appName')} className="flex-shrink-0 border-t border-border-subtle bg-bg-raised pb-[env(safe-area-inset-bottom)]">
        <div className="mx-auto grid max-w-3xl grid-cols-4 gap-1 px-2 py-2">
        {TABS.map(({ to, labelKey, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                'flex min-h-16 min-w-0 flex-col items-center justify-center gap-1 rounded-md px-1 py-2 text-center text-xs font-medium focus-visible:outline-2 focus-visible:outline-accent',
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
