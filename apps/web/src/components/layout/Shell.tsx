import { Activity, Bell, Camera, LayoutGrid, LogOut, Search, ShieldCheck, Grid3x3, Settings, Menu, X, ArrowUpRight } from 'lucide-react'
import { useState, type FormEvent, type ReactNode } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { cn } from '../../lib/cn'
import { useAuth } from '../../lib/AuthContext'
import { ThemeToggle } from '../ui/ThemeToggle'
import { LanguageSwitcher } from '../ui/LanguageSwitcher'

const NAV_ITEMS = [
  { to: '/', labelKey: 'workspace.overview', icon: LayoutGrid, end: true },
  { to: '/live-wall', labelKey: 'nav.liveWall', icon: Grid3x3, end: false },
  { to: '/find-a-vehicle', labelKey: 'nav.findVehicle', icon: Search, end: false },
  { to: '/alerts', labelKey: 'nav.alerts', icon: Bell, end: false },
  { to: '/cameras', labelKey: 'nav.cameras', icon: Camera, end: false },
  { to: '/health', labelKey: 'nav.health', icon: Activity, end: false },
] as const

function WorkspaceNav({ onNavigate }: { onNavigate?: () => void }) {
  const { user, logout } = useAuth()
  const { t } = useTranslation()
  const linkClass = ({ isActive }: { isActive: boolean }) => cn('workspace-nav-link', isActive && 'is-active')

  return (
    <>
      <Link to="/" onClick={onNavigate} className="workspace-brand">
        <ShieldCheck size={30} strokeWidth={1.7} className="text-accent" />
        <span>Sentinel<span className="block text-xs font-normal tracking-normal text-text-tertiary">{t('workspace.console')}</span></span>
      </Link>
      <nav aria-label={t('workspace.navigation')} className="flex flex-col gap-1 px-3">
        {NAV_ITEMS.map(({ to, labelKey, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} onClick={onNavigate} className={linkClass}>
            <Icon size={19} strokeWidth={1.8} />
            <span>{t(labelKey)}</span>
          </NavLink>
        ))}
        {user?.role === 'admin' && (
          <NavLink to="/admin" onClick={onNavigate} className={linkClass}>
            <Settings size={19} strokeWidth={1.8} /><span>{t('nav.admin')}</span>
          </NavLink>
        )}
      </nav>
      <div className="mt-auto px-3 pb-4 pt-8">
        <Link to="/field" className="workspace-nav-link" onClick={onNavigate}>
          <ArrowUpRight size={19} /><span>{t('nav.fieldPwa')}</span>
        </Link>
        <div className="mt-4 border-t border-border-subtle px-3 pt-4">
          <p className="truncate text-sm font-medium">{user?.full_name}</p>
          <p className="mt-1 truncate text-xs text-text-tertiary" title={user?.email}>{user?.email}</p>
          <button type="button" onClick={logout} className="mt-3 flex min-h-10 items-center gap-2 text-sm text-text-secondary hover:text-text-primary">
            <LogOut size={16} />{t('common.signOut')}
          </button>
        </div>
      </div>
    </>
  )
}

export function Shell({ children }: { children: ReactNode }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [menuOpen, setMenuOpen] = useState(false)

  function search(event: FormEvent) {
    event.preventDefault()
    if (query.trim()) {
      navigate(`/find-a-vehicle?plate=${encodeURIComponent(query.trim())}`)
      setQuery('')
    }
  }

  return (
    <div className="workspace-shell">
      <a href="#workspace-content" className="skip-link">{t('workspace.skip')}</a>
      <aside className="workspace-sidebar"><WorkspaceNav /></aside>
      <div className="workspace-main">
        <header className="workspace-toolbar">
          <Dialog.Root open={menuOpen} onOpenChange={setMenuOpen}>
            <Dialog.Trigger asChild>
              <button type="button" className="mobile-nav-trigger" aria-label={t('workspace.openNavigation')}>
                <Menu size={22} />
              </button>
            </Dialog.Trigger>
            <Dialog.Portal>
              <Dialog.Overlay className="fixed inset-0 z-40 bg-black/60" />
              <Dialog.Content aria-describedby={undefined} className="mobile-sidebar">
                <Dialog.Title className="sr-only">{t('workspace.navigation')}</Dialog.Title>
                <Dialog.Close className="absolute right-2 top-3 flex h-10 w-10 items-center justify-center rounded-md" aria-label={t('common.close')}><X size={20} /></Dialog.Close>
                <WorkspaceNav onNavigate={() => setMenuOpen(false)} />
              </Dialog.Content>
            </Dialog.Portal>
          </Dialog.Root>
          <form role="search" aria-label={t('workspace.vehicleSearch')} onSubmit={search} className="workspace-search">
            <Search size={17} className="shrink-0 text-text-tertiary" />
            <input aria-label={t('workspace.plate')} placeholder={t('workspace.searchPlaceholder')} value={query} onChange={(e) => setQuery(e.target.value)} />
            <button type="submit" aria-label={t('common.search')} className="flex h-9 w-9 shrink-0 items-center justify-center rounded-sm hover:bg-bg-overlay"><ArrowUpRight size={17} /></button>
          </form>
          <div className="workspace-preferences"><LanguageSwitcher /><ThemeToggle /></div>
        </header>
        <main id="workspace-content" tabIndex={-1} className="workspace-content">{children}</main>
      </div>
    </div>
  )
}
