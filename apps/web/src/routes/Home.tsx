import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { alertsApi, camerasApi } from '../lib/api'
import { usePolling } from '../lib/usePolling'
import { MapView, type MapMarker } from '../components/MapView'
import { TopBar } from '../components/layout/TopBar'
import { SeverityBadge, priorityToSeverity } from '../components/ui/SeverityBadge'
import { CameraDetailModal } from '../components/CameraDetailModal'
import type { Alert, Camera } from '../lib/types'
import { Link } from 'react-router-dom'
import { ArrowRight, Camera as CameraIcon, CheckCircle2, Search } from 'lucide-react'
import { RequestError } from '../components/ui/RequestError'

const STATUS_COLOR: Record<string, string> = {
  live: 'oklch(0.72 0.16 155)',
  connecting: 'oklch(0.72 0.13 230)',
  degraded: 'oklch(0.75 0.17 65)',
  down: 'oklch(0.62 0.21 25)',
  unknown: 'oklch(0.66 0.02 250)',
}

function useTimeAgo() {
  const { t } = useTranslation()
  return (iso: string): string => {
    const ms = Date.now() - new Date(iso).getTime()
    const minutes = Math.round(ms / 60000)
    if (minutes < 1) return t('common.justNow')
    if (minutes < 60) return t('common.minutesAgo', { count: minutes })
    const hours = Math.round(minutes / 60)
    if (hours < 24) return t('common.hoursAgo', { count: hours })
    return t('common.daysAgo', { count: Math.round(hours / 24) })
  }
}

function AttentionCard({ alert }: { alert: Alert }) {
  const { t } = useTranslation()
  const timeAgo = useTimeAgo()
  return (
    <Link to="/alerts" className="attention-entry">
        <div className="mb-1.5 flex items-center justify-between gap-2">
          <SeverityBadge severity={priorityToSeverity('critical')} label={t('home.watchlistHit')} />
          <span className="text-xs text-text-tertiary">{timeAgo(alert.last_seen_at)}</span>
        </div>
        <p className="plate-mono text-lg font-semibold text-text-primary">{alert.plate_text}</p>
        <p className="mt-1 truncate text-xs text-text-secondary">
          {alert.camera_id} · {t('home.sighting', { count: alert.sighting_count })}
        </p>
    </Link>
  )
}

export function Home() {
  const { t } = useTranslation()
  const { data: cameras, error: camerasError, refetch: refreshCameras } = usePolling(() => camerasApi.list(), 8000)
  const { data: alerts, error: alertsError, refetch: refreshAlerts } = usePolling(() => alertsApi.list('new'), 6000)
  const [selected, setSelected] = useState<Camera | null>(null)

  const markers = useMemo<MapMarker[]>(() => {
    if (!cameras) return []
    return cameras
      .filter((c): c is Camera & { location: NonNullable<Camera['location']> } => c.location !== null)
      .map((c) => ({
        id: c.camera_id,
        lat: c.location.lat,
        lon: c.location.lon,
        color: STATUS_COLOR[c.status] ?? STATUS_COLOR.unknown,
        label: `${c.name} · ${t(`cameraStatus.${c.status}`)}`,
        onClick: () => setSelected(c),
      }))
  }, [cameras, t])

  const liveCount = cameras?.filter((c) => c.status === 'live').length
  const downCount = cameras?.filter((c) => c.status === 'down').length
  const degradedCount = cameras?.filter((c) => c.status === 'degraded').length

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <TopBar title={t('workspace.overviewTitle')} subtitle={t('workspace.overviewDescription')} />
      <div className="page-body">
        {Boolean(camerasError) && <RequestError onRetry={refreshCameras} />}
        <div className="overview-layout">
          <section className="overflow-hidden rounded-lg border border-border-subtle bg-bg-raised">
            <div className="section-heading">
              <h2>{t('workspace.cameraNetwork')}</h2>
              <Link to="/cameras" className="text-link">{t('workspace.manageCameras')}<ArrowRight size={15} /></Link>
            </div>
            <div className="overview-map">
              <MapView markers={markers} className="absolute inset-0" />
              {cameras?.length === 0 && !camerasError && (
                <div className="absolute bottom-4 left-4 right-4 z-10 rounded-md bg-bg-raised p-4">
                  <p className="text-sm font-medium">{t('workspace.noCameras')}</p>
                  <Link to="/cameras" className="text-link mt-2">{t('cameras.addCamera')}<ArrowRight size={15} /></Link>
                </div>
              )}
            </div>
            <div className="network-summary">
              {camerasError ? <span>{t('workspace.statusUnavailable')}</span> : !cameras ? <span>{t('common.loading')}</span> : <>
                <span><CameraIcon size={15} />{t('cameras.registered', { count: cameras.length })}</span>
                <span className="text-ok">{t('home.live', { count: liveCount })}</span>
                <span className="text-sev-critical">{t('home.down', { count: downCount })}</span>
                <span className="text-sev-high">{t('home.degraded', { count: degradedCount })}</span>
                <span>{cameras.filter((c) => c.status === 'connecting').length} {t('cameraStatus.connecting')}</span>
                <span>{cameras.filter((c) => c.status === 'unknown').length} {t('cameraStatus.unknown')}</span>
              </>}
            </div>
          </section>
          <aside className="self-start overflow-hidden rounded-lg border border-border-subtle bg-bg-raised">
            <div className="section-heading">
              <h2>{t('home.needsAttention')}</h2>
              <Link to="/alerts" className="text-link">{t('workspace.viewQueue')}<ArrowRight size={15} /></Link>
            </div>
            {Boolean(alertsError) && <div className="p-4"><RequestError onRetry={refreshAlerts} /></div>}
            {!alerts && !alertsError && <p className="p-5 text-text-secondary">{t('common.loading')}</p>}
            {alerts?.length === 0 && !alertsError && (
              <div className="px-5 py-10">
                <CheckCircle2 size={25} className="mb-4 text-ok" />
                <p className="font-medium">{t('home.nothingNeedsYou')}</p>
                <p className="mt-2 text-sm leading-relaxed text-text-secondary">{t('workspace.queueDescription')}</p>
              </div>
            )}
            {alerts?.slice(0, 5).map((alert) => <AttentionCard key={alert.id} alert={alert} />)}
          </aside>
        </div>
        <div className="mt-6 flex flex-wrap items-center gap-5 rounded-lg border border-border-subtle bg-bg-raised p-6">
          <Search size={25} className="shrink-0 text-accent" />
          <div className="min-w-0 flex-1">
            <h2 className="text-base font-semibold">{t('workspace.startInvestigation')}</h2>
            <p className="mt-1 text-sm leading-relaxed text-text-secondary">{t('findVehicle.searchesLast24h')}</p>
          </div>
          <Link to="/find-a-vehicle" className="inline-flex min-h-11 items-center gap-3 rounded-md bg-accent px-4 py-2 font-medium text-on-accent hover:bg-accent-hover">
            {t('nav.findVehicle')}<ArrowRight size={16} />
          </Link>
          <Link to="/live-wall" className="text-link">{t('workspace.openLiveWall')}<ArrowRight size={15} /></Link>
        </div>
      </div>
      <CameraDetailModal camera={selected} onClose={() => setSelected(null)} />
    </div>
  )
}
