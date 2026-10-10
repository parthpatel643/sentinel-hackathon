import { useEffect, useRef, useState } from 'react'
import { ShieldAlert } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { zonesApi } from '../lib/api'
import { formatIst } from '../lib/time'
import { useLiveEvents } from '../lib/liveEvents'
import { usePolling } from '../lib/usePolling'
import type { ZoneEvent, ZoneEventStatus } from '../lib/types'
import { Button } from './ui/Button'
import { SeverityBadge } from './ui/SeverityBadge'

const RULE_SEVERITY = { intrusion: 'critical', wrong_way: 'high', stopped_vehicle: 'high', loitering: 'medium' } as const

/** Zone-rule hits as alerts: open events, newest first, each triaged with
 * one click (audited server-side). `highlightId` is the event a notifier
 * deep link pointed at. */
export function ZoneEventQueue({ highlightId }: { highlightId?: string | null }) {
  const { t } = useTranslation('readiness')
  const { t: tc, i18n } = useTranslation()
  const { data: newEvents, refetch: refetchNew } = usePolling(() => zonesApi.eventsByStatus('new'), 20000)
  const { data: acknowledged, refetch: refetchAck } = usePolling(() => zonesApi.eventsByStatus('acknowledged', 20), 20000)
  const [busy, setBusy] = useState<string | null>(null)

  function refetch() {
    refetchNew()
    refetchAck()
  }
  useLiveEvents((kind) => { if (kind === 'zone_event') refetch() })

  async function triage(event: ZoneEvent, status: Exclude<ZoneEventStatus, 'new'>) {
    setBusy(event.id)
    try {
      await zonesApi.updateEvent(event.id, status)
      refetch()
    } finally {
      setBusy(null)
    }
  }

  const events = [...(newEvents ?? []), ...(acknowledged ?? [])]
  const highlightRef = useRef<HTMLLIElement>(null)
  const highlightShown = events.some((event) => event.id === highlightId)
  // A notifier deep link lands here; the queue sits below the alert list.
  useEffect(() => {
    if (highlightShown) highlightRef.current?.scrollIntoView({ block: 'center' })
  }, [highlightShown])

  return (
    <section className="zone-queue" aria-label={t('zoneQueue')}>
      <div className="iw-section-heading">
        <h2><ShieldAlert size={16} aria-hidden="true" /> {t('zoneQueue')}</h2>
        <span>{newEvents ? newEvents.length : '—'}</span>
      </div>
      <p className="monitoring-help">{t('zoneQueueHelp')}</p>
      {events.length === 0 ? (
        <p className="text-sm text-text-tertiary">{t('zoneQueueEmpty')}</p>
      ) : (
        <ol className="zone-queue-list">
          {events.map((event) => (
            <li
              key={event.id}
              ref={event.id === highlightId ? highlightRef : undefined}
              className={event.id === highlightId ? 'is-highlighted' : undefined}
            >
              <SeverityBadge
                severity={RULE_SEVERITY[event.rule_type as keyof typeof RULE_SEVERITY] ?? 'medium'}
                label={tc(`cameraDetail.zoneRules.ruleTypes.${event.rule_type}`, { defaultValue: event.rule_type })}
              />
              <div className="min-w-0 flex-1">
                <strong>
                  {event.zone_name ?? event.zone_id}
                  {event.object_class === 'person' && <span className="font-normal text-text-secondary"> · {t('zonePerson')}</span>}
                </strong>
                <small>
                  {event.camera_id} · {event.camera_time ? formatIst(event.camera_time, i18n.language) : tc('common.timeUnknownShort')}
                  {event.dwell_time_s != null && ` · ${t('zoneDwell', { seconds: Math.round(event.dwell_time_s) })}`}
                  {' · '}{tc(`investigation:status_${event.status ?? 'new'}`)}
                </small>
              </div>
              <div className="zone-queue-actions">
                {(event.status ?? 'new') === 'new' && (
                  <Button size="sm" variant="secondary" disabled={busy === event.id} onClick={() => triage(event, 'acknowledged')}>{t('zoneAcknowledge')}</Button>
                )}
                <Button size="sm" variant="secondary" disabled={busy === event.id} onClick={() => triage(event, 'resolved')}>{t('zoneResolve')}</Button>
                <Button size="sm" variant="ghost" disabled={busy === event.id} onClick={() => triage(event, 'false_positive')}>{t('zoneFalsePositive')}</Button>
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
