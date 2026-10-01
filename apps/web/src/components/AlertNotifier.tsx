import { useEffect, useRef, useState } from 'react'
import { BellRing, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useLocation, useNavigate } from 'react-router-dom'
import { alertsApi, camerasApi } from '../lib/api'
import { cameraLabel } from '../lib/cameraStatusColor'
import { usePolling } from '../lib/usePolling'
import type { Alert } from '../lib/types'

const POLL_MS = 4000
const MAX_VISIBLE = 3

/** Announces a new watchlist hit on whatever screen the operator is on —
 * the live wall, a vehicle trace, the registry — rather than only on the
 * Alerts screen. Alerts already open when the console loads are not
 * re-announced; only ones that arrive while it is open are. */
export function AlertNotifier() {
  const { t } = useTranslation('readiness')
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const { data: alerts } = usePolling(() => alertsApi.list('new'), POLL_MS)
  const { data: cameras } = usePolling(() => camerasApi.list(), 60000)
  const seen = useRef<Set<string> | null>(null)
  const [pending, setPending] = useState<Alert[]>([])

  useEffect(() => {
    if (!alerts) return
    if (seen.current === null) {
      seen.current = new Set(alerts.map((alert) => alert.id))
      return
    }
    const fresh = alerts.filter((alert) => !seen.current!.has(alert.id))
    if (fresh.length === 0) return
    for (const alert of fresh) seen.current.add(alert.id)
    const byPriority = [...fresh].sort((a, b) => b.priority_score - a.priority_score)
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reacting to newly polled data
    setPending((current) => [...byPriority, ...current])
  }, [alerts])

  if (pathname === '/alerts' || pending.length === 0) return null

  const cameraName = (cameraId: string) => {
    const camera = cameras?.find((c) => c.camera_id === cameraId)
    return camera ? cameraLabel(camera) : cameraId
  }
  const dismiss = (id: string) => setPending((current) => current.filter((alert) => alert.id !== id))
  const visible = pending.slice(0, MAX_VISIBLE)

  return (
    <section className="alert-notifier" role="region" aria-label={t('alertRegion')} aria-live="assertive">
      {visible.map((alert) => (
        <div key={alert.id} className="alert-notifier-card">
          <BellRing size={18} aria-hidden="true" className="shrink-0 text-sev-critical" />
          <div className="min-w-0 flex-1">
            <p className="alert-notifier-title">{t('alertTitle')}</p>
            <p className="alert-notifier-body">
              {t('alertBody', { plate: alert.plate_text, camera: cameraName(alert.camera_id) })}
            </p>
            <button
              type="button"
              className="alert-notifier-open"
              onClick={() => {
                dismiss(alert.id)
                navigate(`/alerts?alert=${encodeURIComponent(alert.id)}`)
              }}
            >
              {t('openAlert')}
            </button>
          </div>
          <button type="button" aria-label={t('dismiss')} title={t('dismiss')} className="alert-notifier-dismiss" onClick={() => dismiss(alert.id)}>
            <X size={16} />
          </button>
        </div>
      ))}
      {pending.length > MAX_VISIBLE && (
        <p className="alert-notifier-more">{t('moreAlerts', { count: pending.length - MAX_VISIBLE })}</p>
      )}
    </section>
  )
}
