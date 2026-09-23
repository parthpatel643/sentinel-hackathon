import { Bell, Camera, MapPin, Search } from 'lucide-react'
import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { cn } from '../lib/cn'
import { useAuth } from '../lib/AuthContext'
import { useLowBandwidthMode } from './useLowBandwidthMode'
import { useOutboxSync } from './sync'

const TABS = [
  { to: '/field/alerts', label: 'Alerts', icon: Bell },
  { to: '/field/lookup', label: 'Look up', icon: Search },
  { to: '/field/report', label: 'Report', icon: Camera },
  { to: '/field/nearby', label: 'Nearby', icon: MapPin },
]

function timeAgo(iso: string | null): string {
  if (!iso) return 'never'
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  return `${Math.floor(seconds / 3600)}h ago`
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

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-bg-base text-text-primary">
      <header className="flex flex-shrink-0 items-center justify-between border-b border-border-subtle bg-bg-raised px-4 py-2.5 text-xs">
        <div className="flex flex-col">
          <span className="font-semibold text-text-primary">Sentinel Field</span>
          <span className="text-text-tertiary">
            {syncing ? 'Syncing…' : `Last synced ${timeAgo(lastSyncedAt)}`}
            {pendingCount > 0 && ` · ${pendingCount} queued`}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={toggleLowBandwidth}
            className={cn(
              'rounded-full px-2.5 py-1 text-[11px] font-medium',
              lowBandwidth ? 'bg-accent/15 text-accent' : 'bg-bg-inset text-text-tertiary',
            )}
          >
            {lowBandwidth ? 'Low-bandwidth on' : 'Low-bandwidth off'}
          </button>
          <button onClick={logout} className="text-[11px] text-text-tertiary underline">
            Sign out
          </button>
        </div>
      </header>

      <main className="flex-1 overflow-y-auto">{children}</main>

      <nav className="flex flex-shrink-0 border-t border-border-subtle bg-bg-raised">
        {TABS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                'flex flex-1 flex-col items-center gap-1 py-3 text-xs font-medium',
                isActive ? 'text-accent' : 'text-text-tertiary',
              )
            }
          >
            <Icon size={22} strokeWidth={2} />
            {label}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
