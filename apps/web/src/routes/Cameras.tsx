import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Camera as CameraIcon, FileUp, List, Map, Plus, RefreshCw, Search, Server } from 'lucide-react'
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
import { cameraStatusColor } from '../lib/cameraStatusColor'
import type { Camera } from '../lib/types'
import './monitoring-workspace.css'

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
  const [onboardingPath, setOnboardingPath] = useState<'location' | 'bulk-import' | 'discover'>('location')
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
      ?.filter((c): c is Camera & { location: NonNullable<Camera['location']> } => c.location != null)
      .map((c) => ({
        id: c.camera_id,
        lat: c.location.lat,
        lon: c.location.lon,
        color: cameraStatusColor(c.status),
        label: c.name,
        onClick: () => setSelected(c),
      })) ?? []

  function openOnboarding(path: typeof onboardingPath) {
    setOnboardingPath(path)
    setWizardOpen(true)
  }

  return (
    <div className="monitoring-workspace flex min-h-0 flex-1 flex-col">
      <TopBar
        title={t('nav.cameras')}
        subtitle={cameras ? t('cameras.registered', { count: cameras.length }) : undefined}
      />
      <div className="registry-workspace">
      <div className="registry-heading">
        <div><h2>{t('monitoring:registry')}</h2><p>{t('monitoring:registryHelp')}</p></div>
        <Button onClick={() => openOnboarding('location')}><Plus size={16} />{t('cameras.addCamera')}</Button>
      </div>
      <div className="registry-health" role="group" aria-label={t('workspace.allStatuses')}>
        {['all', 'live', 'degraded', 'down', 'connecting', 'unknown'].map((value) => (
          <button key={value} aria-label={t(`monitoring:${value === 'all' ? 'all' : value}Cameras`)} aria-pressed={status === value} onClick={() => setStatus(value)}>
            <span>{value === 'all' ? t('monitoring:allCameras') : t(`cameraStatus.${value}`)}</span>
            <strong>{cameras ? (value === 'all' ? cameras.length : cameras.filter((camera) => camera.status === value).length) : '—'}</strong>
          </button>
        ))}
      </div>
      <section className="registry-inventory" aria-label={t('monitoring:registry')}>
      <div className="registry-toolbar">
        <div className="monitoring-search"><Search size={16} /><Input aria-label={t('workspace.filterCameras')} placeholder={t('workspace.filterCameras')} value={query} onChange={(e) => setQuery(e.target.value)} /></div>
        <select aria-label={t('workspace.allStatuses')} value={status} onChange={(e) => setStatus(e.target.value)} className="h-11 rounded-md border border-border-strong bg-bg-inset px-3 text-sm">
          <option value="all">{t('workspace.allStatuses')}</option>
          {['live', 'connecting', 'degraded', 'down', 'unknown'].map((value) => <option key={value} value={value}>{t(`cameraStatus.${value}`)}</option>)}
        </select>
        <div className="registry-view-switch">
          <Button aria-pressed={view === 'table'} size="sm" variant={view === 'table' ? 'primary' : 'secondary'} onClick={() => setView('table')}><List size={15} />{t('cameras.table')}</Button>
          <Button aria-pressed={view === 'map'} size="sm" variant={view === 'map' ? 'primary' : 'secondary'} onClick={() => setView('map')}><Map size={15} />{t('cameras.map')}</Button>
          <Button size="sm" variant="ghost" aria-label={t('monitoring:refresh')} onClick={refetch}><RefreshCw size={16} /></Button>
        </div>
      </div>
      <div className="registry-results"><span>{cameras ? t('monitoring:results', { count: filteredCameras?.length ?? 0 }) : t('cameras.loading')}</span>{(query || status !== 'all') && <button onClick={() => { setQuery(''); setStatus('all') }}>{t('monitoring:resetFilters')}</button>}</div>
      {Boolean(error) && <div className="p-4"><RequestError onRetry={refetch} /></div>}

      {view === 'map' ? (
        <div className="registry-map-layout">
          <section className="registry-map-list" aria-label={t('monitoring:mapList')}>
            <h3>{t('monitoring:mapList')}</h3>
            {(filteredCameras ?? []).map((camera) => <button key={camera.camera_id} aria-label={camera.name} onClick={() => setSelected(camera)}><CameraIcon size={17} /><span><strong>{camera.name}</strong><small>{camera.location ? `${camera.location.lat.toFixed(4)}, ${camera.location.lon.toFixed(4)}` : t('monitoring:locationMissing')}</small></span><SeverityBadge severity={statusToSeverity(camera.status)} label={t(`cameraStatus.${camera.status}`)} /></button>)}
            {cameras && filteredCameras?.length === 0 && <p className="monitoring-help">{t(cameras.length === 0 ? 'workspace.noCameras' : 'workspace.noMatchingCameras')}</p>}
          </section>
          <div className="registry-map-canvas">
            <MapView markers={markers} className="absolute inset-0" />
            {Boolean(filteredCameras?.some((camera) => !camera.location)) && <p className="registry-map-notice">{t('monitoring:noLocation', { count: filteredCameras?.filter((camera) => !camera.location).length })}</p>}
          </div>
        </div>
      ) : (
        <div className="registry-table-content">
          {loading && !cameras && <p className="text-sm text-text-tertiary">{t('cameras.loading')}</p>}
          {cameras?.length === 0 && (
            <div className="empty-state"><CameraIcon size={32} /><h3>{t('monitoring:noCameras')}</h3><p>{t('monitoring:noCamerasHelp')}</p><Button onClick={() => openOnboarding('location')}><Plus size={16} />{t('cameras.addCamera')}</Button></div>
          )}
          {cameras && cameras.length > 0 && filteredCameras?.length === 0 && <div className="empty-state"><p>{t('workspace.noMatchingCameras')}</p></div>}
          {filteredCameras && filteredCameras.length > 0 && (
            <Card className="registry-table-scroll overflow-x-auto">
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
      </section>
      <div className="registry-onboarding">
        <div><h3>{t('cameras.addCamera')}</h3><p>{t('monitoring:addHelp')}</p></div>
        <Button variant="secondary" onClick={() => openOnboarding('bulk-import')}><FileUp size={16} />{t('monitoring:importCameras')}</Button>
        <Button variant="secondary" onClick={() => openOnboarding('discover')}><Server size={16} />{t('monitoring:discoverCameras')}</Button>
      </div>
      </div>
      <CameraDetailModal camera={selected} onClose={() => setSelected(null)} />
      <OnboardingWizard key={onboardingPath} initialStep={onboardingPath} open={wizardOpen} onClose={() => setWizardOpen(false)} onOnboarded={refetch} />
    </div>
  )
}
