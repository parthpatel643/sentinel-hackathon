import { useEffect, useState } from 'react'
import { Bell, CheckCircle2, ChevronDown, Eye, Navigation } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { alertsApi, camerasApi } from '../lib/api'
import { usePolling } from '../lib/usePolling'
import { useLowBandwidthMode } from './useLowBandwidthMode'
import type { Alert, Camera } from '../lib/types'
import { ApiError } from '../lib/http'
import { SeverityBadge } from '../components/ui/SeverityBadge'

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function haversineKm(a: { lat: number; lon: number }, b: { lat: number; lon: number }): number {
  const R = 6371
  const dLat = ((b.lat - a.lat) * Math.PI) / 180
  const dLon = ((b.lon - a.lon) * Math.PI) / 180
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((a.lat * Math.PI) / 180) * Math.cos((b.lat * Math.PI) / 180) * Math.sin(dLon / 2) ** 2
  return R * 2 * Math.asin(Math.sqrt(h))
}

function AlertCard({ alert, camera, myPosition }: { alert: Alert; camera: Camera | undefined; myPosition: GeolocationCoordinates | null }) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)
  const [busy, setBusy] = useState<'ack' | 'seen' | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [completed, setCompleted] = useState<'ack' | 'seen' | null>(null)
  const { enabled: lowBandwidth } = useLowBandwidthMode()

  const distanceKm =
    myPosition && camera?.location
      ? haversineKm(
          { lat: myPosition.latitude, lon: myPosition.longitude },
          { lat: camera.location.lat, lon: camera.location.lon },
        )
      : null

  async function act(status: 'acknowledged' | 'resolved', kind: 'ack' | 'seen') {
    setBusy(kind)
    setActionError(null)
    try {
      await alertsApi.update(alert.id, { status })
      setCompleted(kind)
    } catch (err) {
      setActionError(err instanceof ApiError ? String(err.detail) : t('management:actionError'))
    } finally {
      setBusy(null)
    }
  }

  function navigate() {
    if (!camera?.location) return
    window.open(`https://www.google.com/maps?q=${camera.location.lat},${camera.location.lon}`, '_blank', 'noopener,noreferrer')
  }

  return (
    <article className="field-alert-card">
      <button
        className="flex w-full items-start gap-3 p-4 text-left hover:bg-bg-hover focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        aria-controls={`field-alert-${alert.id}-actions`}
      >
        {!lowBandwidth && <Bell size={20} className="mt-1 shrink-0 text-accent" aria-hidden="true" />}
        <div className="min-w-0 flex-1">
          <div className="mb-3">
            <SeverityBadge severity={alert.priority_score >= .75 ? 'critical' : alert.priority_score >= .5 ? 'high' : alert.priority_score >= .25 ? 'medium' : 'low'} />
          </div>
          <p className="plate-mono break-all text-xl font-semibold text-text-primary">{alert.plate_text}</p>
          <p className="mt-1 break-words text-sm text-text-secondary">{camera?.name ?? alert.camera_id}</p>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-text-secondary">
            <time dateTime={alert.last_seen_at}>{formatTime(alert.last_seen_at)}</time>
            {distanceKm != null && (
              <span className="font-medium text-accent">{t('field.alerts.kmAway', { distance: distanceKm.toFixed(1) })}</span>
            )}
          </div>
        </div>
        <ChevronDown size={18} className={`mt-1 shrink-0 text-text-secondary ${expanded ? 'rotate-180' : ''}`} aria-hidden="true" />
      </button>
      {expanded && (
        <div id={`field-alert-${alert.id}-actions`} className="grid grid-cols-3 gap-2 border-t border-border-subtle p-3">
          <button
            onClick={navigate}
            disabled={!camera?.location}
            className="flex min-h-16 min-w-0 flex-col items-center justify-center gap-1.5 rounded-md bg-bg-inset px-1 py-3 text-xs font-medium text-text-secondary hover:bg-bg-hover focus-visible:outline-2 focus-visible:outline-accent disabled:opacity-40"
          >
            <Navigation size={20} aria-hidden="true" />
            {t('field.alerts.navigate')}
          </button>
          <button
            onClick={() => act('acknowledged', 'ack')}
            disabled={busy !== null || completed !== null}
            className="flex min-h-16 min-w-0 flex-col items-center justify-center gap-1.5 rounded-md bg-bg-inset px-1 py-3 text-xs font-medium text-text-secondary hover:bg-bg-hover focus-visible:outline-2 focus-visible:outline-accent disabled:opacity-40"
          >
            <CheckCircle2 size={20} aria-hidden="true" />
            {busy === 'ack' ? '…' : t('field.alerts.acknowledge')}
          </button>
          <button
            onClick={() => act('resolved', 'seen')}
            disabled={busy !== null || completed === 'seen'}
            className="flex min-h-16 min-w-0 flex-col items-center justify-center gap-1.5 rounded-md bg-accent/10 px-1 py-3 text-xs font-medium text-accent hover:bg-accent/20 focus-visible:outline-2 focus-visible:outline-accent disabled:opacity-40"
          >
            <Eye size={20} aria-hidden="true" />
            {busy === 'seen' ? '…' : t('field.alerts.iSeeIt')}
          </button>
        </div>
      )}
      {completed && <p role="status" className="field-alert-feedback text-ok">{t(completed === 'ack' ? 'management:alertAcknowledged' : 'management:alertResolved')}</p>}
      {actionError && <p role="alert" className="field-alert-feedback text-sev-critical">{actionError}</p>}
    </article>
  )
}

export function FieldAlerts() {
  const { t } = useTranslation()
  const { data: alerts, loading, error, refetch } = usePolling(() => alertsApi.list('new'), 8000)
  const { data: cameras } = usePolling(() => camerasApi.list(), 30000)
  const [myPosition, setMyPosition] = useState<GeolocationCoordinates | null>(null)

  useEffect(() => {
    if (!navigator.geolocation) return
    const id = navigator.geolocation.watchPosition((pos) => setMyPosition(pos.coords), () => {}, {
      enableHighAccuracy: false,
    })
    return () => navigator.geolocation.clearWatch(id)
  }, [])

  const camerasById = new Map((cameras ?? []).map((c) => [c.camera_id, c]))

  return (
    <section className="field-page field-alerts" aria-labelledby="field-alerts-heading">
      <header className="field-page-heading">
      <div className="flex items-center justify-between gap-3">
        <h1 id="field-alerts-heading" className="text-2xl font-semibold tracking-tight">{t('field.nav.alerts')}</h1>
        {alerts && <span className="rounded-md bg-bg-inset px-3 py-1.5 text-sm font-medium tabular-nums text-text-secondary">{alerts.length}</span>}
      </div>
      <p>{t('management:alertIntro')}</p>
      </header>
      <section aria-label={t('management:alertQueue')} className="field-alert-queue">
      {loading && <p role="status" className="py-8 text-sm text-text-secondary">{t('common.loading')}</p>}
      {!!error && (
        <div role="alert" className="mb-4 rounded-md bg-sev-critical/10 p-4 text-sm text-sev-critical">
          <p>{t('workspace.refreshError')}</p>
          <button onClick={refetch} className="mt-2 min-h-10 rounded-md px-3 font-medium underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-accent">{t('common.retry')}</button>
        </div>
      )}
      {!error && alerts?.length === 0 && (
        <div className="flex flex-col items-center gap-3 border-y border-border-subtle py-12 text-center">
          <Bell size={28} className="text-text-tertiary" aria-hidden="true" />
          <p className="text-sm text-text-secondary">{t('field.alerts.noOpenAlerts')}</p>
        </div>
      )}
      <div className="field-alert-list">
      {alerts?.map((alert) => (
        <AlertCard key={alert.id} alert={alert} camera={camerasById.get(alert.camera_id)} myPosition={myPosition} />
      ))}
      </div>
      </section>
      <Link to="/field/lookup" className="field-alert-lookup">{t('field.nav.lookup')}<ChevronDown size={18} className="-rotate-90" aria-hidden="true" /></Link>
    </section>
  )
}
