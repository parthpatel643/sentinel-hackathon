import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { camerasApi } from '../lib/api'
import { usePolling } from '../lib/usePolling'
import { TopBar } from '../components/layout/TopBar'
import { Card } from '../components/ui/Card'
import { SeverityBadge, statusToSeverity, tamperToSeverity } from '../components/ui/SeverityBadge'
import { MapView, type MapMarker } from '../components/MapView'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import { RequestError } from '../components/ui/RequestError'
import { CameraDetailModal } from '../components/CameraDetailModal'
import { OnboardingWizard } from '../components/OnboardingWizard'
import type { Camera } from '../lib/types'

const STATUS_COLOR: Record<string, string> = {
  live: 'oklch(0.72 0.16 155)',
  connecting: 'oklch(0.72 0.13 230)',
  degraded: 'oklch(0.75 0.17 65)',
  down: 'oklch(0.62 0.21 25)',
  unknown: 'oklch(0.66 0.02 250)',
}

function fpsLabel(camera: Camera): string {
  if (camera.measured_fps == null) return '—'
  const declared = camera.declared_fps != null ? `/${camera.declared_fps.toFixed(0)}` : ''
  return `${camera.measured_fps.toFixed(1)}${declared} fps`
}

export function Cameras() {
  const { t } = useTranslation()
  const { data: cameras, loading, error, refetch } = usePolling(() => camerasApi.list(), 10000)
  const [view, setView] = useState<'table' | 'map'>('table')
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('all')
  const [selected, setSelected] = useState<Camera | null>(null)
  const [wizardOpen, setWizardOpen] = useState(false)
  const [searchParams, setSearchParams] = useSearchParams()

  // Lets the ⌘K palette (and any other deep link) jump straight to a
  // camera's detail modal via /cameras?camera=<id> without duplicating
  // the lookup logic anywhere else.
  useEffect(() => {
    const cameraId = searchParams.get('camera')
    if (!cameraId || !cameras) return
    const match = cameras.find((c) => c.camera_id === cameraId)
    if (match) setSelected(match)
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.delete('camera')
      return next
    }, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cameras, searchParams])

  const filteredCameras = cameras?.filter((camera) =>
    (status === 'all' || camera.status === status) &&
    `${camera.name} ${camera.camera_id}`.toLowerCase().includes(query.trim().toLowerCase()),
  )
  const markers: MapMarker[] =
    filteredCameras
      ?.filter((c): c is Camera & { location: NonNullable<Camera['location']> } => c.location !== null)
      .map((c) => ({
        id: c.camera_id,
        lat: c.location.lat,
        lon: c.location.lon,
        color: STATUS_COLOR[c.status] ?? STATUS_COLOR.unknown,
        label: c.name,
        onClick: () => setSelected(c),
      })) ?? []

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <TopBar
        title={t('nav.cameras')}
        subtitle={cameras ? t('cameras.registered', { count: cameras.length }) : undefined}
      />
      <div className="page-toolbar">
        <Input className="w-full sm:w-64" aria-label={t('workspace.filterCameras')} placeholder={t('workspace.filterCameras')} value={query} onChange={(e) => setQuery(e.target.value)} />
        <select aria-label={t('workspace.allStatuses')} value={status} onChange={(e) => setStatus(e.target.value)} className="h-11 rounded-md border border-border-strong bg-bg-inset px-3 text-sm">
          <option value="all">{t('workspace.allStatuses')}</option>
          {['live', 'connecting', 'degraded', 'down', 'unknown'].map((value) => <option key={value} value={value}>{t(`cameraStatus.${value}`)}</option>)}
        </select>
        <Button aria-pressed={view === 'table'} size="sm" variant={view === 'table' ? 'primary' : 'secondary'} onClick={() => setView('table')}>
          {t('cameras.table')}
        </Button>
        <Button aria-pressed={view === 'map'} size="sm" variant={view === 'map' ? 'primary' : 'secondary'} onClick={() => setView('map')}>
          {t('cameras.map')}
        </Button>
        <Button size="sm" variant="secondary" className="ml-auto" onClick={() => setWizardOpen(true)}>
          <Plus size={14} />
          {t('cameras.addCamera')}
        </Button>
      </div>
      {Boolean(error) && <div className="px-5 md:px-8"><RequestError onRetry={refetch} /></div>}

      {view === 'map' ? (
        <div className="relative mx-5 mb-6 min-h-80 flex-1 overflow-hidden rounded-lg border border-border-subtle md:mx-8">
          <MapView markers={markers} className="absolute inset-0" />
        </div>
      ) : (
        <div className="page-body">
          {loading && !cameras && <p className="text-sm text-text-tertiary">{t('cameras.loading')}</p>}
          {cameras?.length === 0 && (
            <div className="empty-state"><p>{t('workspace.noCameras')}</p><Button onClick={() => setWizardOpen(true)}><Plus size={16} />{t('cameras.addCamera')}</Button></div>
          )}
          {cameras && cameras.length > 0 && filteredCameras?.length === 0 && <div className="empty-state"><p>{t('workspace.noMatchingCameras')}</p></div>}
          {filteredCameras && filteredCameras.length > 0 && (
            <Card className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className="border-b border-border-subtle text-xs uppercase tracking-wide text-text-tertiary">
                  <tr>
                    <th className="px-4 py-2.5 font-medium">{t('cameras.columns.name')}</th>
                    <th className="px-4 py-2.5 font-medium">{t('cameras.columns.department')}</th>
                    <th className="px-4 py-2.5 font-medium">{t('cameras.columns.tier')}</th>
                    <th className="px-4 py-2.5 font-medium">{t('cameras.columns.status')}</th>
                    <th className="px-4 py-2.5 font-medium">{t('cameras.columns.fps')}</th>
                    <th className="px-4 py-2.5 font-medium">{t('cameras.columns.reconnects')}</th>
                    <th className="px-4 py-2.5 font-medium">{t('cameras.columns.tamper')}</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredCameras.map((camera) => (
                    <tr
                      key={camera.camera_id}
                      onClick={() => setSelected(camera)}
                      className="cursor-pointer border-b border-border-subtle/60 last:border-0 hover:bg-bg-overlay"
                    >
                      <td className="px-4 py-2.5">
                        <button type="button" onClick={() => setSelected(camera)} className="min-h-10 text-left font-medium text-text-primary hover:text-accent">{camera.name}</button>
                        <div className="text-xs text-text-tertiary">{camera.camera_id}</div>
                      </td>
                      <td className="px-4 py-2.5 text-text-secondary">{camera.department_name ?? t('common.unknown')}</td>
                      <td className="px-4 py-2.5 text-text-secondary">{camera.tier}</td>
                      <td className="px-4 py-2.5">
                        <SeverityBadge severity={statusToSeverity(camera.status)} label={t(`cameraStatus.${camera.status}`)} />
                      </td>
                      <td className="px-4 py-2.5 plate-mono text-text-secondary">{fpsLabel(camera)}</td>
                      <td className="px-4 py-2.5 text-text-secondary">{camera.reconnects}</td>
                      <td className="px-4 py-2.5">
                        {camera.tamper_status ? (
                          <SeverityBadge
                            severity={tamperToSeverity(camera.tamper_status)}
                            label={t(`tamperStatus.${camera.tamper_status}`)}
                          />
                        ) : (
                          <span className="text-xs text-text-tertiary">{t('cameras.notMonitored')}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </div>
      )}
      <CameraDetailModal camera={selected} onClose={() => setSelected(null)} />
      <OnboardingWizard open={wizardOpen} onClose={() => setWizardOpen(false)} onOnboarded={refetch} />
    </div>
  )
}
