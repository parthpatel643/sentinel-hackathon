import { Activity, Bell, Camera, LayoutGrid, LogOut, Search, ShieldCheck, Grid3x3, Settings, Menu, X, ArrowUpRight, Command, ChevronRight, PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { cn } from '../../lib/cn'
import { useAuth } from '../../lib/AuthContext'
import { ThemeToggle } from '../ui/ThemeToggle'
import { LanguageSwitcher } from '../ui/LanguageSwitcher'
import { OPEN_COMMAND_PALETTE } from '../CommandPalette'
import './command-shell.css'

const NAV_ITEMS = [
  { to: '/', labelKey: 'workspace.overview', icon: LayoutGrid, end: true },
  { to: '/live-wall', labelKey: 'nav.liveWall', icon: Grid3x3, end: false },
  { to: '/find-a-vehicle', labelKey: 'nav.findVehicle', icon: Search, end: false },
  { to: '/alerts', labelKey: 'nav.alerts', icon: Bell, end: false },
  { to: '/cameras', labelKey: 'nav.cameras', icon: Camera, end: false },
  { to: '/health', labelKey: 'nav.health', icon: Activity, end: false },
] as const

function WorkspaceNav({ onNavigate, expanded, onToggle }: { onNavigate?: () => void; expanded?: boolean; onToggle?: () => void }) {
  const { user, logout } = useAuth()
  const { t } = useTranslation()
  const linkClass = ({ isActive }: { isActive: boolean }) => cn('workspace-nav-link', isActive && 'is-active')

  return (
    <>
      <Link to="/" onClick={onNavigate} className="workspace-brand">
        <span className="brand-symbol"><ShieldCheck size={25} strokeWidth={1.7} aria-hidden="true" /></span>
        <span>Sentinel<span className="brand-caption">{t('workspace.console')}</span></span>
      </Link>
      {onToggle && <button type="button" className="rail-toggle" aria-label={t(expanded ? 'command:collapseNavigation' : 'command:expandNavigation')} aria-expanded={expanded} onClick={onToggle}>
        {expanded ? <PanelLeftClose size={17} /> : <PanelLeftOpen size={17} />}
        <span>{t(expanded ? 'command:collapseNavigation' : 'command:expandNavigation')}</span>
      </button>}
      <p className="nav-group-label">{t('workspace.navigation')}</p>
      <nav aria-label={t('workspace.navigation')} className="flex flex-col gap-1 px-3">
        {NAV_ITEMS.map(({ to, labelKey, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} title={t(labelKey)} onClick={onNavigate} className={linkClass}>
            <Icon size={19} strokeWidth={1.8} />
            <span>{t(labelKey)}</span>
          </NavLink>
        ))}
        {user?.role === 'admin' && (
          <NavLink to="/admin" title={t('nav.admin')} onClick={onNavigate} className={linkClass}>
            <Settings size={19} strokeWidth={1.8} /><span>{t('nav.admin')}</span>
          </NavLink>
        )}
      </nav>
      <div className="mt-auto px-3 pb-4 pt-8">
        <Link to="/field" className="workspace-nav-link" onClick={onNavigate}>
          <ArrowUpRight size={19} /><span>{t('nav.fieldPwa')}</span>
        </Link>
        <div className="workspace-account" title={`${user?.full_name ?? ''} · ${user?.email ?? ''}`}>
          <span className="operator-avatar" aria-hidden="true">{user?.full_name?.trim().slice(0, 1).toUpperCase()}</span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{user?.full_name}</p>
            <p className="account-email" title={user?.email}>{user?.email}</p>
          </div>
        </div>
        <button type="button" onClick={logout} className="workspace-signout" aria-label={t('common.signOut')}>
          <LogOut size={16} /><span>{t('common.signOut')}</span>
        </button>
      </div>
    </>
  )
}

export function Shell({ children }: { children: ReactNode }) {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const currentLabel = NAV_ITEMS.find((item) => item.to === pathname)?.labelKey ?? 'nav.admin'
  const [query, setQuery] = useState('')
  const [menuOpen, setMenuOpen] = useState(false)
  const [expanded, setExpanded] = useState(() => localStorage.getItem('sentinel-navigation-expanded') === 'true')
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 60000)
    return () => clearInterval(timer)
  }, [])

  function toggleNavigation() {
    const next = !expanded
    setExpanded(next)
    localStorage.setItem('sentinel-navigation-expanded', String(next))
  }

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
      <aside className={cn('workspace-sidebar', expanded ? 'is-expanded' : 'is-compact')}><WorkspaceNav expanded={expanded} onToggle={toggleNavigation} /></aside>
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
          <div className="workspace-location">
            <ShieldCheck size={17} aria-hidden="true" />
            <span>Sentinel</span>
            <ChevronRight size={14} aria-hidden="true" />
            <strong>{t(currentLabel)}</strong>
          </div>
          <time className="workspace-clock" dateTime={now.toISOString()} aria-label={t('command:localTime')}>
            {now.toLocaleDateString(i18n.language, { day: '2-digit', month: 'short' })}
            <span>{now.toLocaleTimeString(i18n.language, { hour: '2-digit', minute: '2-digit' })}</span>
          </time>
          <form role="search" aria-label={t('workspace.vehicleSearch')} onSubmit={search} className="workspace-search">
            <Search size={17} className="shrink-0 text-text-tertiary" />
            <input aria-label={t('workspace.plate')} placeholder={t('workspace.searchPlaceholder')} value={query} onChange={(e) => setQuery(e.target.value)} />
            <button type="submit" aria-label={t('common.search')} className="flex h-9 w-9 shrink-0 items-center justify-center rounded-sm hover:bg-bg-overlay"><ArrowUpRight size={17} /></button>
          </form>
          <button type="button" className="command-trigger" aria-label={t('workspace.openCommands')} title={t('workspace.openCommands')} onClick={() => document.dispatchEvent(new Event(OPEN_COMMAND_PALETTE))}>
            <Command size={17} aria-hidden="true" /><kbd>K</kbd>
          </button>
          <div className="workspace-preferences"><LanguageSwitcher /><ThemeToggle /></div>
        </header>
        <main id="workspace-content" tabIndex={-1} className="workspace-content">{children}</main>
      </div>
    </div>
  )
}
