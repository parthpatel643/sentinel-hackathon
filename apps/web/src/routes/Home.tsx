import { useMemo, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'
import { Activity, ArrowRight, Bell, Camera as CameraIcon, CheckCircle2, ChevronRight, List, Map, Radio, RefreshCw, ScanLine, Search } from 'lucide-react'
import { alertsApi, camerasApi, detectionsApi } from '../lib/api'
import { cameraStatusColor } from '../lib/cameraStatusColor'
import { usePolling } from '../lib/usePolling'
import { navigateTabs } from '../lib/tabs'
import { MapView, type MapMarker } from '../components/MapView'
import { TopBar } from '../components/layout/TopBar'
import { SeverityBadge, statusToSeverity } from '../components/ui/SeverityBadge'
import { CameraDetailModal } from '../components/CameraDetailModal'
import { RequestError } from '../components/ui/RequestError'
import { Button } from '../components/ui/Button'
import type { Alert, Camera, CameraStatus, Detection } from '../lib/types'
import './command-overview.css'

const STATUSES: CameraStatus[] = ['live', 'degraded', 'down', 'connecting', 'unknown']

function ActivityEntry({ item, cameraName }: { item: Alert | Detection; cameraName?: string }) {
  const { t, i18n } = useTranslation()
  const isAlert = 'last_seen_at' in item
  const timestamp = isAlert ? item.last_seen_at : item.observed_at
  const date = new Date(timestamp)
  const time = Number.isNaN(date.getTime()) ? t('common.notAvailable') : date.toLocaleTimeString(i18n.language, { hour: '2-digit', minute: '2-digit' })
  return (
    <Link className="command-event" to={isAlert ? `/alerts?alert=${encodeURIComponent(item.id)}` : `/find-a-vehicle?plate=${encodeURIComponent(item.plate_text)}`}>
      <span className={`command-event-icon ${isAlert ? 'is-alert' : ''}`} aria-hidden="true">{isAlert ? <Bell size={18} /> : <ScanLine size={18} />}</span>
      <div className="command-event-body">
        <div className="command-event-title"><strong className="plate-mono">{item.plate_text}</strong><time dateTime={timestamp} title={date.toLocaleString(i18n.language)}>{time}</time></div>
        <p>{cameraName ?? item.camera_id}</p>
        <div className="command-event-meta">
          <span>{isAlert ? t('home.watchlistHit') : t('command:recentDetections')}</span>
          <span>{isAlert ? t('home.sighting', { count: item.sighting_count }) : `${Math.round(item.plate_confidence * 100)}%`}</span>
        </div>
      </div>
      <ChevronRight size={14} className="shrink-0 text-text-tertiary" aria-hidden="true" />
    </Link>
  )
}

export function Home() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { data: cameras, error: camerasError, refetch: refreshCameras } = usePolling(() => camerasApi.list(), 8000)
  const { data: alerts, error: alertsError, refetch: refreshAlerts } = usePolling(() => alertsApi.list('new'), 6000)
  const { data: detections, error: detectionsError, refetch: refreshDetections } = usePolling(() => detectionsApi.search({ limit: 12 }), 8000)
  const [selected, setSelected] = useState<Camera | null>(null)
  const [fleetView, setFleetView] = useState<'map' | 'list'>('map')
  const [activityView, setActivityView] = useState<'alerts' | 'detections'>('alerts')
  const [status, setStatus] = useState<CameraStatus | 'all'>('all')
  const [cameraQuery, setCameraQuery] = useState('')
  const [plate, setPlate] = useState('')
  const filteredCameras = useMemo(() => {
    const query = cameraQuery.trim().toLowerCase()
    return (cameras ?? []).filter(camera =>
      (status === 'all' || camera.status === status) &&
      (!query || `${camera.name} ${camera.camera_id}`.toLowerCase().includes(query)),
    )
  }, [cameras, cameraQuery, status])
  const markers = useMemo<MapMarker[]>(() => filteredCameras.flatMap(camera => camera.location ? [{
    id: camera.camera_id, lat: camera.location.lat, lon: camera.location.lon,
    color: cameraStatusColor(camera.status), label: `${camera.name} · ${t(`cameraStatus.${camera.status}`)}`,
    onClick: () => setSelected(camera),
  }] : []), [filteredCameras, t])
  const counts = Object.fromEntries(STATUSES.map(state => [state, cameras?.filter(camera => camera.status === state).length]))
  const metrics = [
    { key: 'registeredCameras', value: cameras?.length, error: camerasError, icon: CameraIcon, to: '/cameras', detail: 'registeredDetail' },
    { key: 'liveCameras', value: counts.live, error: camerasError, icon: Radio, to: '/live-wall', detail: 'liveDetail' },
    { key: 'interruptedCameras', value: cameras ? (counts.down ?? 0) + (counts.degraded ?? 0) : undefined, error: camerasError, icon: Activity, to: '/cameras', detail: 'interruptedDetail' },
    { key: 'queuedAlerts', value: alerts?.length, error: alertsError, icon: Bell, to: '/alerts', detail: 'queueDetail' },
  ]

  function investigate(event: FormEvent) {
    event.preventDefault()
    if (plate.trim()) navigate(`/find-a-vehicle?plate=${encodeURIComponent(plate.trim())}`)
  }

  return (
    <div className="command-overview">
      <TopBar title={t('workspace.overviewTitle')} subtitle={t('workspace.overviewDescription')} actions={
        <Button variant="secondary" aria-label={t('workspace.refreshOverview')} onClick={() => { refreshCameras(); refreshAlerts(); refreshDetections() }}>
          <RefreshCw size={15} aria-hidden="true" />{t('workspace.refresh')}
        </Button>
      } />
      <div className="command-overview-body">
        <section aria-label={t('workspace.summary')} className="command-summary">
          {metrics.map(({ key, value, error, icon: Icon, to, detail }) => (
            <Link key={key} to={to} aria-label={t(`workspace.${key}`)} aria-describedby={`metric-${key}`}>
              <Icon size={20} aria-hidden="true" />
              <div><span>{t(`workspace.${key}`)}</span><strong id={`metric-${key}`} className={value === undefined || error ? 'is-unavailable' : ''}>
                {error ? t('common.notAvailable') : value === undefined ? t('common.loading') : value}
              </strong></div>
              <span className="summary-detail">{t(`workspace.${detail}`)}</span>
              <ArrowRight size={14} aria-hidden="true" />
            </Link>
          ))}
        </section>

        <form className="command-investigate" onSubmit={investigate} aria-label={t('command:quickInvestigation')}>
          <div><Search size={21} aria-hidden="true" /><div><h2>{t('workspace.startInvestigation')}</h2><p>{t('command:searchHint')}</p></div></div>
          <label className="sr-only" htmlFor="overview-plate">{t('workspace.plate')}</label>
          <input id="overview-plate" value={plate} onChange={event => setPlate(event.target.value)} placeholder="GJ 01 AB 1234" className="plate-mono" autoComplete="off" />
          <Button type="submit" disabled={!plate.trim()}>{t('command:traceVehicle')}<ArrowRight size={16} /></Button>
        </form>

        {Boolean(camerasError) && <RequestError onRetry={refreshCameras} />}
        <div className="command-workbench">
          <section className="command-network" aria-labelledby="network-heading">
            <header className="command-panel-header">
              <div><h2 id="network-heading"><CameraIcon size={17} aria-hidden="true" />{t('workspace.cameraNetwork')}</h2><p>{t('command:fleetDescription')}</p></div>
              <div className="command-segments" role="tablist" aria-label={t('workspace.cameraNetwork')} onKeyDown={navigateTabs}>
                <button id="fleet-map-tab" type="button" role="tab" tabIndex={fleetView === 'map' ? 0 : -1} aria-selected={fleetView === 'map'} aria-controls="fleet-panel" onClick={() => setFleetView('map')}><Map size={15} />{t('command:mapView')}</button>
                <button id="fleet-list-tab" type="button" role="tab" tabIndex={fleetView === 'list' ? 0 : -1} aria-selected={fleetView === 'list'} aria-controls="fleet-panel" onClick={() => setFleetView('list')}><List size={15} />{t('command:cameraList')}</button>
              </div>
            </header>
            <div className="network-search-row">
              <div className="network-search"><Search size={15} aria-hidden="true" /><input type="search" aria-label={t('command:networkSearch')} placeholder={t('command:networkSearch')} value={cameraQuery} onChange={event => setCameraQuery(event.target.value)} /></div>
              <Link to="/cameras" className="text-link">{t('workspace.manageCameras')}<ArrowRight size={14} /></Link>
            </div>
            <div id="fleet-panel" role="tabpanel" aria-labelledby={fleetView === 'map' ? 'fleet-map-tab' : 'fleet-list-tab'} className={`command-fleet-panel ${fleetView === 'list' ? 'is-list' : ''}`}>
              {fleetView === 'map' ? <MapView markers={markers} className="absolute inset-0" fitToMarkers={Boolean(cameraQuery.trim()) || status !== 'all'} /> : (
                <div className="command-camera-list">
                  {filteredCameras.map(camera => (
                    <button type="button" key={camera.camera_id} onClick={() => setSelected(camera)}>
                      <span className="camera-list-icon"><CameraIcon size={20} aria-hidden="true" /></span>
                      <span className="camera-list-name"><strong>{camera.name}</strong><span>{camera.department_name ?? camera.camera_id}{!camera.location && ` · ${t('command:noLocation')}`}</span></span>
                      <SeverityBadge severity={statusToSeverity(camera.status)} label={t(`cameraStatus.${camera.status}`)} />
                      <ChevronRight size={16} aria-hidden="true" />
                    </button>
                  ))}
                </div>
              )}
              {cameras?.length === 0 && !camerasError ? <div className="network-message"><CameraIcon size={24} /><p>{t('workspace.noCameras')}</p><Link to="/cameras" className="text-link">{t('cameras.addCamera')}<ArrowRight size={14} /></Link></div> :
                cameras && filteredCameras.length === 0 && <div className="network-message"><p>{t('workspace.noMatchingCameras')}</p><button type="button" className="text-link" onClick={() => { setStatus('all'); setCameraQuery('') }}>{t('command:resetFilters')}</button></div>}
              {!cameras && !camerasError && <div className="network-message"><p>{t('common.loading')}</p></div>}
            </div>
            <div className="command-network-footer">
              <span>{camerasError ? t('workspace.statusUnavailable') : cameras ? t('command:showingCameras', { shown: filteredCameras.length, total: cameras.length }) : t('common.loading')}</span>
              {cameras && !camerasError && <span>{t('command:mapLocations', { count: markers.length })}</span>}
            </div>
          </section>

          <section className="command-activity" aria-labelledby="activity-heading">
            <header className="command-panel-header"><h2 id="activity-heading"><Activity size={17} />{t('command:activity')}</h2></header>
            <div className="command-activity-tabs" role="tablist" aria-label={t('command:activity')} onKeyDown={navigateTabs}>
              <button id="activity-alerts-tab" type="button" role="tab" tabIndex={activityView === 'alerts' ? 0 : -1} aria-selected={activityView === 'alerts'} aria-controls="activity-panel" onClick={() => setActivityView('alerts')}>{t('command:watchlistMatches')}{alerts && !alertsError && <span>{alerts.length}</span>}</button>
              <button id="activity-detections-tab" type="button" role="tab" tabIndex={activityView === 'detections' ? 0 : -1} aria-selected={activityView === 'detections'} aria-controls="activity-panel" onClick={() => setActivityView('detections')}>{t('command:recentDetections')}</button>
            </div>
            <div id="activity-panel" role="tabpanel" aria-labelledby={activityView === 'alerts' ? 'activity-alerts-tab' : 'activity-detections-tab'} className="command-activity-content">
              {activityView === 'alerts' ? <>
                {Boolean(alertsError) && <RequestError onRetry={refreshAlerts} />}
                {!alerts && !alertsError && <p className="command-activity-empty">{t('common.loading')}</p>}
                {alerts?.length === 0 && !alertsError && <div className="command-activity-empty"><CheckCircle2 size={30} /><h3>{t('home.nothingNeedsYou')}</h3><p>{t('workspace.queueDescription')}</p></div>}
                {alerts?.slice(0, 8).map(alert => <ActivityEntry key={alert.id} item={alert} cameraName={cameras?.find(camera => camera.camera_id === alert.camera_id)?.name} />)}
              </> : <>
                {Boolean(detectionsError) && <RequestError onRetry={refreshDetections} />}
                {!detections && !detectionsError && <p className="command-activity-empty">{t('common.loading')}</p>}
                {detections?.length === 0 && !detectionsError && <div className="command-activity-empty"><ScanLine size={30} /><p>{t('command:noDetections')}</p></div>}
                {detections?.map(detection => <ActivityEntry key={detection.event_id} item={detection} cameraName={cameras?.find(camera => camera.camera_id === detection.camera_id)?.name} />)}
              </>}
            </div>
            <footer>{activityView === 'alerts' ? <Link to="/alerts" className="text-link">{t('command:reviewAlerts')}<ArrowRight size={15} /></Link> : <span>{t('command:recentDescription')}</span>}</footer>
          </section>
        </div>

        <section className="command-health" aria-labelledby="fleet-health-heading">
          <div><h2 id="fleet-health-heading"><Activity size={17} />{t('workspace.cameraHealth')}</h2><p>{t('workspace.cameraRefresh')}</p></div>
          <div className="command-health-filters">
            <button type="button" aria-pressed={status === 'all'} onClick={() => setStatus('all')}>{t('command:allCameras')}<strong>{cameras && !camerasError ? cameras.length : '—'}</strong></button>
            {STATUSES.map(state => (
              <button key={state} type="button" aria-label={t(`command:${state}Filter`)} aria-pressed={status === state} onClick={() => setStatus(state)}>
                <span className={`status-dot status-${state}`} aria-hidden="true" />{t(`cameraStatus.${state}`)}<strong>{cameras && !camerasError ? counts[state] : '—'}</strong>
              </button>
            ))}
          </div>
        </section>
      </div>
      <CameraDetailModal camera={selected} onClose={() => setSelected(null)} />
    </div>
  )
}
