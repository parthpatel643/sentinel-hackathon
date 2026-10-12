import { useEffect, useRef, useState } from 'react'
import { Camera, MoveDiagonal } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { cameraEventsApi, camerasApi } from '../lib/api'
import { cameraLabel } from '../lib/cameraStatusColor'
import { formatIst } from '../lib/time'
import { useLiveEvents } from '../lib/liveEvents'
import { usePolling } from '../lib/usePolling'
import type { CameraEvent, ZoneEventStatus } from '../lib/types'
import { Button } from './ui/Button'
import { SeverityBadge } from './ui/SeverityBadge'
import './camera-view-queue.css'

/** One evidence frame, fetched with the operator's token (an <img> cannot
 * send it) and shown through an object URL. */
function ViewFrame({ eventId, which, label }: { eventId: string; which: 'before' | 'after'; label: string }) {
  const [url, setUrl] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    let objectUrl: string | null = null
    let cancelled = false
    cameraEventsApi
      .snapshotBlob(eventId, which)
      .then(({ blob }) => {
        if (cancelled) return
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
      })
      .catch(() => !cancelled && setFailed(true))
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [eventId, which])
  return (
    <figure className="camera-view-frame">
      {url && !failed ? <img src={url} alt={label} /> : <div className="camera-view-frame-empty"><Camera size={20} aria-hidden="true" /></div>}
      <figcaption>{label}</figcaption>
    </figure>
  )
}

/** Cameras whose view changed, as alerts: the remembered view beside the
 * view now, how far it moved, and one-click triage (audited server-side).
 * A `camera_event` query parameter is the event a notifier deep link
 * pointed at. */
export function CameraViewQueue() {
  const { t } = useTranslation('readiness')
  const { t: tc, i18n } = useTranslation()
  const [searchParams] = useSearchParams()
  const highlightId = searchParams.get('camera_event')
  const { data: newEvents, refetch: refetchNew } = usePolling(() => cameraEventsApi.byStatus('new'), 20000)
  const { data: acknowledged, refetch: refetchAck } = usePolling(() => cameraEventsApi.byStatus('acknowledged', 20), 20000)
  const { data: cameras } = usePolling(() => camerasApi.list(), 60000)
  const [busy, setBusy] = useState<string | null>(null)

  function refetch() {
    refetchNew()
    refetchAck()
  }
  useLiveEvents((kind) => { if (kind === 'camera_event') refetch() })

  async function triage(event: CameraEvent, status: Exclude<ZoneEventStatus, 'new'>) {
    setBusy(event.id)
    try {
      await cameraEventsApi.update(event.id, status)
      refetch()
    } finally {
      setBusy(null)
    }
  }

  const events = [...(newEvents ?? []), ...(acknowledged ?? [])]
  const highlightRef = useRef<HTMLLIElement>(null)
  const highlightShown = events.some((event) => event.id === highlightId)
  useEffect(() => {
    if (highlightShown) highlightRef.current?.scrollIntoView({ block: 'center' })
  }, [highlightShown])

  const cameraName = (cameraId: string) => {
    const camera = cameras?.find((c) => c.camera_id === cameraId)
    return camera ? cameraLabel(camera) : cameraId
  }

  return (
    <section className="zone-queue camera-view-queue" aria-label={t('cameraQueue')}>
      <div className="iw-section-heading">
        <h2><MoveDiagonal size={16} aria-hidden="true" /> {t('cameraQueue')}</h2>
        <span>{newEvents ? newEvents.length : '—'}</span>
      </div>
      <p className="monitoring-help">{t('cameraQueueHelp')}</p>
      {events.length === 0 ? (
        <p className="text-sm text-text-tertiary">{t('cameraQueueEmpty')}</p>
      ) : (
        <ol className="camera-view-list">
          {events.map((event) => {
            const moved = event.kind === 'view_shifted'
            const measures = [
              event.shift_pct != null && event.shift_pct >= 1 ? t('cameraShift', { value: Math.round(event.shift_pct) }) : null,
              event.rotation_deg != null && Math.abs(event.rotation_deg) >= 1 ? t('cameraRotation', { value: Math.round(Math.abs(event.rotation_deg)) }) : null,
              event.scale != null && Math.abs(event.scale - 1) >= 0.05 ? t('cameraZoom', { value: event.scale.toFixed(2) }) : null,
            ].filter(Boolean)
            return (
              <li
                key={event.id}
                ref={event.id === highlightId ? highlightRef : undefined}
                className={event.id === highlightId ? 'is-highlighted' : undefined}
              >
                <div className="camera-view-head">
                  <SeverityBadge severity={moved ? 'high' : 'medium'} label={t(moved ? 'cameraMoved' : 'cameraLost')} />
                  <div className="min-w-0 flex-1">
                    <strong>{cameraName(event.camera_id)}</strong>
                    <small>
                      {measures.length > 0 ? `${measures.join(' · ')} · ` : ''}
                      {event.camera_time ? formatIst(event.camera_time, i18n.language) : tc('common.timeUnknownShort')}
                      {' · '}{tc(`investigation:status_${event.status}`)}
                    </small>
                    {!moved && <small>{t('cameraLostHint')}</small>}
                  </div>
                </div>
                {event.has_snapshots ? (
                  <div className="camera-view-frames">
                    <ViewFrame eventId={event.event_id} which="before" label={t('cameraBefore')} />
                    <ViewFrame eventId={event.event_id} which="after" label={t('cameraAfter')} />
                  </div>
                ) : (
                  <p className="text-xs text-text-tertiary">{t('cameraNoFrames')}</p>
                )}
                <div className="zone-queue-actions">
                  {event.status === 'new' && (
                    <Button size="sm" variant="secondary" disabled={busy === event.id} onClick={() => triage(event, 'acknowledged')}>{t('zoneAcknowledge')}</Button>
                  )}
                  <Button size="sm" variant="secondary" disabled={busy === event.id} onClick={() => triage(event, 'resolved')}>{t('zoneResolve')}</Button>
                  <Button size="sm" variant="ghost" disabled={busy === event.id} onClick={() => triage(event, 'false_positive')}>{t('zoneFalsePositive')}</Button>
                </div>
              </li>
            )
          })}
        </ol>
      )}
    </section>
  )
}
