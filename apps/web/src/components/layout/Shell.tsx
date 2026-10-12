import { Activity, Bell, Camera, LayoutGrid, LogOut, Search, Grid3x3, Settings, ArrowUpRight, ArrowRight, MoreHorizontal } from 'lucide-react'
import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../../lib/AuthContext'
import { alertsApi } from '../../lib/api'
import { ALL_JURISDICTIONS, JurisdictionProvider, useJurisdiction } from '../../lib/jurisdiction'
import { usePolling } from '../../lib/usePolling'
import { AlertNotifier } from '../AlertNotifier'
import { ThemeToggle } from '../ui/ThemeToggle'
import { LanguageSwitcher } from '../ui/LanguageSwitcher'
import { AlertSoundToggle } from '../ui/AlertSoundToggle'
import { OPEN_COMMAND_PALETTE } from '../CommandPalette'
import '../../styles/gate.css'
import './command-shell.css'
import { formatIstDate, formatIstTime } from '../../lib/time'

const NAV_ITEMS = [
  { to: '/', labelKey: 'workspace.overview', icon: LayoutGrid, end: true },
  { to: '/live-wall', labelKey: 'nav.liveWall', icon: Grid3x3, end: false },
  { to: '/find-a-vehicle', labelKey: 'nav.findVehicle', icon: Search, end: false },
  { to: '/alerts', labelKey: 'nav.alerts', icon: Bell, end: false },
  { to: '/cameras', labelKey: 'nav.cameras', icon: Camera, end: false },
  { to: '/health', labelKey: 'nav.health', icon: Activity, end: false },
] as const

/** Vehicles (not raw hits) waiting in the operator's jurisdiction. */
function useWaitingVehicles() {
  const { inScope } = useJurisdiction()
  const { data } = usePolling(() => alertsApi.list('new'), 15000)
  return useMemo(() => new Set((data ?? []).filter((a) => inScope(a.camera_id)).map((a) => a.plate_text)).size, [data, inScope])
}

function NavLinks({ waiting, onNavigate, className }: { waiting: number; onNavigate?: () => void; className?: string }) {
  const { t } = useTranslation()
  const { user } = useAuth()
  return (
    <nav aria-label={t('workspace.navigation')} className={className}>
      {NAV_ITEMS.map(({ to, labelKey, icon: Icon, end }) => (
        <NavLink key={to} to={to} end={end} onClick={onNavigate}>
          <Icon className="gb-ico" aria-hidden="true" />
          <span>{t(labelKey)}</span>
          {to === '/alerts' && waiting > 0 && <span className="gb-count" aria-label={t('shell.waitingVehicles', { count: waiting })}>{waiting}</span>}
        </NavLink>
      ))}
      {user?.role === 'admin' && (
        <NavLink to="/admin" onClick={onNavigate}>
          <Settings className="gb-ico" aria-hidden="true" /><span>{t('nav.admin')}</span>
        </NavLink>
      )}
    </nav>
  )
}

function JurisdictionSwitcher() {
  const { t } = useTranslation()
  const { scope, setScope, districts } = useJurisdiction()
  const known = scope === ALL_JURISDICTIONS || districts.some((d) => d.name === scope)
  return (
    <div className="gb-scope">
      <label htmlFor="jurisdiction"><span>{t('shell.jurisdiction')}</span></label>
      <select id="jurisdiction" value={scope} onChange={(event) => setScope(event.target.value)}>
        <option value={ALL_JURISDICTIONS}>{t('shell.allDistricts')}</option>
        {!known && <option value={scope}>{scope}</option>}
        {districts.map((d) => <option key={d.name} value={d.name}>{t('shell.districtOption', { name: d.name, count: d.cameras })}</option>)}
      </select>
    </div>
  )
}

function ShellFrame({ children }: { children: ReactNode }) {
  const { t, i18n } = useTranslation()
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const { cameras } = useJurisdiction()
  const waiting = useWaitingVehicles()
  const [query, setQuery] = useState('')
  const [moreOpen, setMoreOpen] = useState(false)
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 30000)
    return () => clearInterval(timer)
  }, [])

  function search(event: FormEvent) {
    event.preventDefault()
    if (query.trim()) {
      navigate(`/find-a-vehicle?plate=${encodeURIComponent(query.trim())}`)
      setQuery('')
    }
  }

  const bottomItems = [
    { to: '/', labelKey: 'workspace.overview', icon: LayoutGrid, end: true },
    { to: '/live-wall', labelKey: 'nav.liveWall', icon: Grid3x3, end: false },
    { to: '/find-a-vehicle', labelKey: 'shell.find', icon: Search, end: false },
    { to: '/alerts', labelKey: 'nav.alerts', icon: Bell, end: false },
  ]

  return (
    <div className="gb-shell">
      <a href="#workspace-content" className="skip-link">{t('workspace.skip')}</a>
      <header className="gb-top">
        <Link to="/" className="gb-brand" aria-label="Sentinel"><span className="gb-brand-mark" aria-hidden="true"><i /></span><span>Sentinel</span></Link>
        <JurisdictionSwitcher />
        {cameras && <span className="gb-scope-note">{t('shell.scaleNote', { count: cameras.length })}</span>}
        <span className="gb-spacer" />
        <span className="gb-clock">
          <time dateTime={now.toISOString()} aria-label={t('command:localTime')}>
            <span className="gb-z">{formatIstDate(now, i18n.language, { day: '2-digit', month: 'short' })}</span>
            <span className="gb-t">{formatIstTime(now, i18n.language)}</span>
            <span className="gb-z">IST</span>
          </time>
        </span>
        <LanguageSwitcher />
        <AlertSoundToggle />
        <ThemeToggle />
      </header>

      <div className="gb-nav">
        <NavLinks waiting={waiting} className="gb-navlinks" />
        <form role="search" aria-label={t('workspace.vehicleSearch')} onSubmit={search} className="gb-search">
          <Search className="gb-ico" aria-hidden="true" />
          <input aria-label={t('workspace.plate')} placeholder={t('workspace.searchPlaceholder')} value={query} onChange={(e) => setQuery(e.target.value)} />
          <button type="submit" aria-label={t('common.search')}><ArrowRight className="gb-ico" aria-hidden="true" /></button>
        </form>
        <button type="button" className="gb-kbd-btn" aria-label={t('workspace.openCommands')} title={t('workspace.openCommands')} onClick={() => document.dispatchEvent(new Event(OPEN_COMMAND_PALETTE))}>
          <kbd>⌘K</kbd>
        </button>
      </div>

      <main id="workspace-content" tabIndex={-1} className="gb-content">{children}</main>

      <footer className="gb-foot">
        <span className="gb-who" title={user?.email}>
          <span className="gb-av" aria-hidden="true">{user?.full_name?.trim().slice(0, 2).toUpperCase()}</span>
          <b>{user?.full_name}</b><span>{user?.email}</span>
        </span>
        <button type="button" onClick={logout} className="gb-signout"><LogOut className="gb-ico" aria-hidden="true" />{t('common.signOut')}</button>
        <span className="gb-note">{t('shell.amberNote')}</span>
        <Link to="/field">{t('nav.fieldPwa')}<ArrowUpRight className="gb-ico" aria-hidden="true" /></Link>
      </footer>

      <nav className="gb-bottom-nav" aria-label={t('shell.moreTitle')}>
        {bottomItems.map(({ to, labelKey, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end}>
            <Icon className="gb-ico" aria-hidden="true" />
            <span>{t(labelKey)}</span>
            {to === '/alerts' && waiting > 0 && <span className="gb-count" aria-hidden="true">{waiting}</span>}
          </NavLink>
        ))}
        <Dialog.Root open={moreOpen} onOpenChange={setMoreOpen}>
          <Dialog.Trigger asChild>
            <button type="button" aria-label={t('workspace.openNavigation')}>
              <MoreHorizontal className="gb-ico" aria-hidden="true" /><span>{t('shell.more')}</span>
            </button>
          </Dialog.Trigger>
          <Dialog.Portal>
            <Dialog.Overlay className="fixed inset-0 z-40 bg-black/50" />
            <Dialog.Content aria-describedby={undefined} className="gb-more">
              <Dialog.Title className="gb-sr">{t('shell.moreTitle')}</Dialog.Title>
              <NavLinks waiting={waiting} onNavigate={() => setMoreOpen(false)} className="flex flex-col gap-1" />
              <Link to="/field" onClick={() => setMoreOpen(false)}><ArrowUpRight className="gb-ico" aria-hidden="true" />{t('nav.fieldPwa')}</Link>
              <div className="gb-who"><b>{user?.full_name}</b><span>{user?.email}</span></div>
              <button type="button" className="gb-more-item" onClick={logout}><LogOut className="gb-ico" aria-hidden="true" />{t('common.signOut')}</button>
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
      </nav>
      <AlertNotifier />
    </div>
  )
}

export function Shell({ children }: { children: ReactNode }) {
  return (
    <JurisdictionProvider>
      <ShellFrame>{children}</ShellFrame>
    </JurisdictionProvider>
  )
}
