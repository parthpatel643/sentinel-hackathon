import { useEffect, useRef, useState } from 'react'
import { BellRing, ShieldAlert, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useLocation, useNavigate } from 'react-router-dom'
import { playAlertTone } from '../lib/alertSound'
import { alertsApi, camerasApi, zonesApi } from '../lib/api'
import { cameraLabel } from '../lib/cameraStatusColor'
import { useLiveEvents } from '../lib/liveEvents'
import { usePolling } from '../lib/usePolling'
import type { Alert, ZoneEvent } from '../lib/types'

// Live events arrive over the stream in well under a second; polling is the
// fallback for a dropped stream, so it can be slow.
const FALLBACK_POLL_MS = 15000
const MAX_VISIBLE = 3

type Notice = { kind: 'alert'; item: Alert } | { kind: 'zone'; item: ZoneEvent }

/** Announces a new watchlist hit or zone event (intrusion, loitering,
 * wrong way, stopped vehicle) on whatever screen the operator is on. Items
 * already open when the console loads are not re-announced; only those that
 * arrive while it is open are. */
export function AlertNotifier() {
  const { t } = useTranslation('readiness')
  const { t: tc } = useTranslation()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const { data: alerts } = usePolling(() => alertsApi.list('new'), FALLBACK_POLL_MS)
  const { data: zoneEvents } = usePolling(() => zonesApi.eventsByStatus('new'), FALLBACK_POLL_MS)
  const { data: cameras } = usePolling(() => camerasApi.list(), 60000)
  const seenAlerts = useRef<Set<string> | null>(null)
  const seenZones = useRef<Set<string> | null>(null)
  const [pending, setPending] = useState<Notice[]>([])

  function announce(fresh: Notice[]) {
    if (fresh.length === 0) return
    setPending((current) => [...fresh, ...current])
    playAlertTone()
  }

  function freshAlerts(items: Alert[]): Notice[] {
    if (seenAlerts.current === null) return []
    const fresh = items.filter((alert) => alert.status === 'new' && !seenAlerts.current!.has(alert.id))
    for (const alert of fresh) seenAlerts.current.add(alert.id)
    return [...fresh].sort((a, b) => b.priority_score - a.priority_score).map((item) => ({ kind: 'alert', item }))
  }

  function freshZones(items: ZoneEvent[]): Notice[] {
    if (seenZones.current === null) return []
    const fresh = items.filter((event) => (event.status ?? 'new') === 'new' && !seenZones.current!.has(event.id))
    for (const event of fresh) seenZones.current.add(event.id)
    return fresh.map((item) => ({ kind: 'zone', item }))
  }

  // The first poll establishes what was already open; later ones (and the
  // stream) announce only what is new.
  useEffect(() => {
    if (!alerts) return
    if (seenAlerts.current === null) {
      seenAlerts.current = new Set(alerts.map((alert) => alert.id))
      return
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reacting to newly polled data
    announce(freshAlerts(alerts))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [alerts])

  useEffect(() => {
    if (!zoneEvents) return
    if (seenZones.current === null) {
      seenZones.current = new Set(zoneEvents.map((event) => event.id))
      return
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reacting to newly polled data
    announce(freshZones(zoneEvents))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zoneEvents])

  useLiveEvents((kind, data) => {
    if (kind === 'alert') announce(freshAlerts([data as Alert]))
    else announce(freshZones([data as ZoneEvent]))
  })

  if (pathname === '/alerts' || pending.length === 0) return null

  const cameraName = (cameraId: string) => {
    const camera = cameras?.find((c) => c.camera_id === cameraId)
    return camera ? cameraLabel(camera) : cameraId
  }
  const dismiss = (id: string) => setPending((current) => current.filter((notice) => notice.item.id !== id))
  const visible = pending.slice(0, MAX_VISIBLE)

  return (
    <section className="alert-notifier" role="region" aria-label={t('alertRegion')} aria-live="assertive">
      {visible.map((notice) => {
        const id = notice.item.id
        const isAlert = notice.kind === 'alert'
        const Icon = isAlert ? BellRing : ShieldAlert
        const body = isAlert
          ? t('alertBody', { plate: notice.item.plate_text, camera: cameraName(notice.item.camera_id) })
          : t('zoneBody', {
              rule: tc(`cameraDetail.zoneRules.ruleTypes.${notice.item.rule_type}`, { defaultValue: notice.item.rule_type }),
              zone: notice.item.zone_name ?? '',
              camera: cameraName(notice.item.camera_id),
            })
        return (
          <div key={id} className="alert-notifier-card">
            <Icon size={18} aria-hidden="true" className="shrink-0 text-sev-critical" />
            <div className="min-w-0 flex-1">
              <p className="alert-notifier-title">{t(isAlert ? 'alertTitle' : 'zoneTitle')}</p>
              <p className="alert-notifier-body">{body}</p>
              <button
                type="button"
                className="alert-notifier-open"
                onClick={() => {
                  dismiss(id)
                  navigate(isAlert ? `/alerts?alert=${encodeURIComponent(id)}` : `/alerts?zone=${encodeURIComponent(id)}`)
                }}
              >
                {t('openAlert')}
              </button>
            </div>
            <button type="button" aria-label={t('dismiss')} title={t('dismiss')} className="alert-notifier-dismiss" onClick={() => dismiss(id)}>
              <X size={16} />
            </button>
          </div>
        )
      })}
      {pending.length > MAX_VISIBLE && (
        <p className="alert-notifier-more">{t('moreAlerts', { count: pending.length - MAX_VISIBLE })}</p>
      )}
    </section>
  )
}
