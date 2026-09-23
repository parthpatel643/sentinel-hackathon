import { Command } from 'cmdk'
import { Bell, Camera as CameraIcon, LayoutGrid, LogOut, Search, Video, Activity, Grid3x3, Settings, Smartphone } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../lib/AuthContext'
import { camerasApi } from '../lib/api'
import { usePolling } from '../lib/usePolling'
import { SeverityBadge, statusToSeverity } from './ui/SeverityBadge'

export const OPEN_COMMAND_PALETTE = 'sentinel:open-command-palette'

const NAV_ITEMS = [
  { to: '/', labelKey: 'nav.home', icon: LayoutGrid, keywords: ['situational awareness', 'map'] },
  { to: '/live-wall', labelKey: 'nav.liveWall', icon: Grid3x3, keywords: ['grid', 'streams', 'wall'] },
  { to: '/cameras', labelKey: 'nav.cameras', icon: CameraIcon, keywords: ['registry', 'feeds'] },
  { to: '/find-a-vehicle', labelKey: 'nav.findVehicle', icon: Search, keywords: ['plate', 'route', 'search'] },
  { to: '/alerts', labelKey: 'nav.alerts', icon: Bell, keywords: ['watchlist', 'hits'] },
  { to: '/health', labelKey: 'nav.health', icon: Activity, keywords: ['compliance', 'integrator', 'status'] },
  { to: '/field/alerts', labelKey: 'nav.fieldPwa', icon: Smartphone, keywords: ['mobile', 'officer', 'lookup', 'report'] },
] as const

const ADMIN_NAV_ITEM = {
  to: '/admin',
  labelKey: 'nav.admin',
  icon: Settings,
  keywords: ['users', 'roles', 'watchlist', 'retention', 'audit'],
} as const

/** Global ⌘K / Ctrl+K launcher, mounted once at the app shell. Every
 * destination and action here is also reachable by mouse (docs/03-UX-DESIGN.md
 * §7) — this is a shortcut for power users, never the only path. */
export function CommandPalette() {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const { t } = useTranslation()
  // intervalMs=0 → fetched once when the palette first mounts, no background
  // polling; the camera list doesn't need to be live inside a search box.
  const { data: cameras } = usePolling(() => camerasApi.list(), 0)

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'k' && (event.metaKey || event.ctrlKey)) {
        event.preventDefault()
        setOpen((prev) => !prev)
      }
    }
    function openPalette() { setOpen(true) }
    document.addEventListener('keydown', onKeyDown)
    document.addEventListener(OPEN_COMMAND_PALETTE, openPalette)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.removeEventListener(OPEN_COMMAND_PALETTE, openPalette)
    }
  }, [])

  function go(path: string) {
    navigate(path)
    setOpen(false)
    setSearch('')
  }

  const matchingCameras = useMemo(() => {
    if (!cameras) return []
    const query = search.trim().toLowerCase()
    const pool = query
      ? cameras.filter((c) => c.name.toLowerCase().includes(query) || c.camera_id.toLowerCase().includes(query))
      : cameras
    return pool.slice(0, 8)
  }, [cameras, search])

  const trimmedSearch = search.trim()

  return (
    <Command.Dialog
      open={open}
      onOpenChange={setOpen}
      shouldFilter={false}
      label={t('commandPalette.label')}
      overlayClassName="fixed inset-0 z-50 bg-black/40 backdrop-blur-[2px]"
      contentClassName="fixed left-1/2 top-[18vh] z-50 w-full max-w-lg -translate-x-1/2 overflow-hidden rounded-xl border border-border-subtle bg-bg-raised shadow-2xl"
    >
      <div className="flex items-center gap-2.5 border-b border-border-subtle px-4">
        <Search size={16} className="text-text-tertiary" />
        <Command.Input
          autoFocus
          value={search}
          onValueChange={setSearch}
          placeholder={t('commandPalette.placeholder')}
          className="h-12 flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-tertiary focus:outline-none"
        />
        <kbd className="rounded border border-border-subtle px-1.5 py-0.5 text-[10px] text-text-tertiary">Esc</kbd>
      </div>

      <Command.List className="max-h-[50vh] overflow-y-auto p-2">
        <Command.Empty className="px-3 py-6 text-center text-sm text-text-tertiary">
          {t('commandPalette.noMatches')}
        </Command.Empty>

        {trimmedSearch.length > 0 && (
          <Command.Group heading={t('commandPalette.findVehicleGroup')} className="cmdk-group">
            <Command.Item
              value={`plate-${trimmedSearch}`}
              onSelect={() => go(`/find-a-vehicle?plate=${encodeURIComponent(trimmedSearch)}`)}
              className="cmdk-item"
            >
              <Search size={16} className="text-text-tertiary" />
              <span>
                {t('commandPalette.searchPlate')}{' '}
                <span className="plate-mono font-semibold">{trimmedSearch.toUpperCase()}</span>
              </span>
            </Command.Item>
          </Command.Group>
        )}

        <Command.Group heading={t('commandPalette.goTo')} className="cmdk-group">
          {[...NAV_ITEMS, ...(user?.role === 'admin' ? [ADMIN_NAV_ITEM] : [])]
            .filter(
              (item) =>
                !trimmedSearch ||
                t(item.labelKey).toLowerCase().includes(trimmedSearch.toLowerCase()) ||
                item.keywords.some((k) => k.includes(trimmedSearch.toLowerCase())),
            )
            .map(({ to, labelKey, icon: Icon }) => (
              <Command.Item key={to} value={t(labelKey)} onSelect={() => go(to)} className="cmdk-item">
                <Icon size={16} className="text-text-tertiary" />
                <span>{t(labelKey)}</span>
              </Command.Item>
            ))}
        </Command.Group>

        {matchingCameras.length > 0 && (
          <Command.Group heading={t('commandPalette.camerasGroup')} className="cmdk-group">
            {matchingCameras.map((camera) => (
              <Command.Item
                key={camera.camera_id}
                value={`${camera.name}-${camera.camera_id}`}
                onSelect={() => go(`/cameras?camera=${encodeURIComponent(camera.camera_id)}`)}
                className="cmdk-item"
              >
                <Video size={16} className="text-text-tertiary" />
                <span className="flex-1 truncate">{camera.name}</span>
                <SeverityBadge severity={statusToSeverity(camera.status)} label={t(`cameraStatus.${camera.status}`)} />
              </Command.Item>
            ))}
          </Command.Group>
        )}

        <Command.Group heading={t('commandPalette.accountGroup')} className="cmdk-group">
          <Command.Item
            value={`sign-out-${user?.email ?? ''}`}
            onSelect={() => {
              logout()
              setOpen(false)
            }}
            className="cmdk-item"
          >
            <LogOut size={16} className="text-text-tertiary" />
            <span>{user ? t('common.signOutWithEmail', { email: user.email }) : t('common.signOut')}</span>
          </Command.Item>
        </Command.Group>
      </Command.List>
    </Command.Dialog>
  )
}
