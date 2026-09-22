import { Bell, Camera as CameraIcon, LayoutGrid, Search, ShieldCheck } from 'lucide-react'
import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { cn } from '../../lib/cn'

const NAV_ITEMS = [
  { to: '/', label: 'Home', icon: LayoutGrid, end: true },
  { to: '/cameras', label: 'Cameras', icon: CameraIcon, end: false },
  { to: '/find-a-vehicle', label: 'Find a Vehicle', icon: Search, end: false },
  { to: '/alerts', label: 'Alerts', icon: Bell, end: false },
]

export function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-bg-base text-text-primary">
      <nav className="flex w-[76px] flex-shrink-0 flex-col items-center gap-1 border-r border-border-subtle bg-bg-raised py-4">
        <div className="mb-4 flex h-9 w-9 items-center justify-center rounded-lg bg-accent/15 text-accent">
          <ShieldCheck size={20} strokeWidth={2.25} />
        </div>
        {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cn(
                'flex w-16 flex-col items-center gap-1 rounded-md py-2.5 text-[11px] font-medium transition-colors duration-fast',
                isActive
                  ? 'bg-accent/15 text-accent'
                  : 'text-text-tertiary hover:bg-bg-overlay hover:text-text-secondary',
              )
            }
          >
            <Icon size={19} strokeWidth={2.1} />
            <span className="leading-tight text-center">{label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="flex min-w-0 flex-1 flex-col">{children}</div>
    </div>
  )
}
