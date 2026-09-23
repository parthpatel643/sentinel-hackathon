import { useEffect, useState } from 'react'
import { ArrowRight, Bell, Film, RefreshCw, Search, ShieldCheck } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { alertsApi } from '../lib/api'
import { usePolling } from '../lib/usePolling'
import { TopBar } from '../components/layout/TopBar'
import { Button } from '../components/ui/Button'
import { SeverityBadge, type Severity } from '../components/ui/SeverityBadge'
import { SealedClipModal } from '../components/SealedClipModal'
import type { Alert, AlertStatus, EvidenceClip } from '../lib/types'
import { RequestError } from '../components/ui/RequestError'
import { Input } from '../components/ui/Input'
import './investigation-workspace.css'

const FILTERS: { key: string; status?: AlertStatus }[] = [
  { key: 'unacknowledged', status: 'new' },
  { key: 'acknowledged', status: 'acknowledged' },
  { key: 'resolved', status: 'resolved' },
  { key: 'assigned', status: 'assigned' },
  { key: 'in_progress', status: 'in_progress' },
  { key: 'false_positive', status: 'false_positive' },
  { key: 'all', status: undefined },
]

function formatTime(iso: string, language: string): string {
  return new Date(iso).toLocaleString(language, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function severityForAlert(alert: Alert): Severity {
  // priority isn't on Alert directly — priority_score already folds it in,
  // so a simple threshold stands in for it here; see watchlist/service.py.
  if (alert.priority_score >= 0.75) return 'critical'
  if (alert.priority_score >= 0.5) return 'high'
  if (alert.priority_score >= 0.25) return 'medium'
  return 'low'
}

function ClipAction({ alert, onView }: { alert: Alert; onView: (clip: EvidenceClip) => void }) {
  const { t } = useTranslation()
  const [clip, setClip] = useState<EvidenceClip | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false
    alertsApi
      .getClip(alert.id)
      .then((c) => !cancelled && setClip(c))
      // A 404 just means no clip has been requested yet, which is already
      // this component's initial state — nothing to do either way, so any
      // other fetch error just leaves the "Seal clip" action available for
      // the operator to retry rather than getting stuck.
      .catch(() => {})
      .finally(() => !cancelled && setLoaded(true))
    return () => {
      cancelled = true
    }
  }, [alert.id])

  // While a seal is in flight, poll until it resolves — sealing runs a real
  // ~10s recording window in the background (evidence/service.py), so this
  // can't just be a one-shot fetch.
  useEffect(() => {
    if (clip?.status !== 'pending') return
    let cancelled = false
    const id = setInterval(() => {
      alertsApi.getClip(alert.id).then((result) => { if (!cancelled) setClip(result) }).catch(() => {})
    }, 2000)
    return () => { cancelled = true; clearInterval(id) }
  }, [alert.id, clip?.status])

  async function requestSeal() {
    setBusy(true)
    setError(false)
    try {
      setClip(await alertsApi.sealClip(alert.id))
    } catch {
      setError(true)
    } finally {
      setBusy(false)
    }
  }

  if (!loaded) return null

  if (!clip || clip.status === 'failed') {
    return (
      <div className="flex flex-col items-end gap-1">
        <Button size="sm" variant="secondary" onClick={requestSeal} disabled={busy}>
          <Film size={14} />
          {t(busy ? 'alerts.sealingClip' : 'alerts.sealClip')}
        </Button>
        {clip?.status === 'failed' && <p className="text-[11px] text-sev-critical">{t('alerts.sealingFailed')}</p>}
        {error && <p role="alert" className="text-xs text-sev-critical">{t('alerts.sealingFailed')}</p>}
      </div>
    )
  }

  if (clip.status === 'pending') {
    return (
      <Button size="sm" variant="ghost" disabled>
        <Film size={14} />
        {t('alerts.sealingClip')}
      </Button>
    )
  }

  return (
    <Button size="sm" variant="ghost" onClick={() => onView(clip)}>
      <Film size={14} />
      {t('alerts.watchSealedClip')}
    </Button>
  )
}

function AlertDetail({
  alert,
  onUpdated,
  onViewClip,
}: {
  alert: Alert
  onUpdated: () => void
  onViewClip: (clip: EvidenceClip) => void
}) {
  const { t, i18n } = useTranslation()
  const [busy, setBusy] = useState<AlertStatus | null>(null)
  const [error, setError] = useState(false)

  async function act(status: AlertStatus) {
    setBusy(status)
    setError(false)
    try {
      await alertsApi.update(alert.id, { status })
      onUpdated()
    } catch {
      setError(true)
    } finally {
      setBusy(null)
    }
  }

  const isOpen = !['resolved', 'false_positive'].includes(alert.status)

  return (
    <section className="iw-alert-detail" aria-label={t('investigation:selectedAlert')}>
      <div className="iw-section-heading"><h2>{t('investigation:selectedAlert')}</h2><span>{t(`investigation:status_${alert.status}`)}</span></div>
      <div className="iw-alert-identity">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <SeverityBadge severity={severityForAlert(alert)} />
            <span className="text-xs text-text-secondary">{t(alert.match_rung === 'exact' ? 'alerts.exactMatch' : 'alerts.probableMatch')}</span>
          </div>
          <h3 className="plate-mono">{alert.plate_text}</h3>
          <p className="mt-2 text-sm text-text-secondary">
            {t('alerts.onWatchlistLine', {
              match: alert.match_rung === 'exact' ? t('alerts.exactMatch') : t('alerts.probableMatch'),
              camera: alert.camera_id,
            })}
            {alert.sighting_count > 1 && ` · ${t('alerts.sighting', { count: alert.sighting_count })}`}
          </p>
          <Link className="iw-investigate-link" to={`/find-a-vehicle?plate=${encodeURIComponent(alert.plate_text)}`}>{t('investigation:investigateVehicle')}<ArrowRight size={16} /></Link>
      </div>
      <dl className="iw-facts iw-alert-facts">
        <div><dt>{t('investigation:camera')}</dt><dd>{alert.camera_id}</dd></div>
        <div><dt>{t('investigation:confidence')}</dt><dd>{Math.round(alert.match_confidence * 100)}%</dd></div>
        <div><dt>{t('investigation:firstSeen')}</dt><dd>{formatTime(alert.first_seen_at, i18n.language)}</dd></div>
        <div><dt>{t('investigation:lastSeen')}</dt><dd>{formatTime(alert.last_seen_at, i18n.language)}</dd></div>
        <div><dt>{t('investigation:watchlistReference')}</dt><dd>{alert.watchlist_entry_id}</dd></div>
        {alert.resolution_note && <div><dt>{t('investigation:resolutionNote')}</dt><dd>{alert.resolution_note}</dd></div>}
      </dl>
      <div className="iw-alert-evidence">
        <div><h3><Film size={17} />{t('investigation:sealedEvidence')}</h3><p>{t('investigation:sealDescription')}</p></div>
        <ClipAction alert={alert} onView={onViewClip} />
      </div>
      <div className="iw-alert-actions">
        <h3>{t('investigation:reviewDecision')}</h3>
        <p>{t('investigation:decisionHelp')}</p>
        {isOpen && (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="secondary" disabled={busy !== null || alert.status !== 'new'} onClick={() => act('acknowledged')}>
              {busy === 'acknowledged' ? t('alerts.acknowledging') : t('alerts.acknowledge')}
            </Button>
            <Button size="sm" variant="ghost" disabled={busy !== null} onClick={() => act('false_positive')}>
              {t('alerts.notThisVehicle')}
            </Button>
            <Button size="sm" disabled={busy !== null} onClick={() => act('resolved')}>
              {busy === 'resolved' ? t('alerts.resolving') : t('alerts.resolve')}
            </Button>
          </div>
        )}
        {!isOpen && (
          <SeverityBadge
            severity={alert.status === 'false_positive' ? 'low' : 'ok'}
            label={alert.status === 'false_positive' ? t('alerts.notThisVehicle') : t('alerts.resolved')}
          />
        )}
        {error && <p role="alert" className="text-sm text-sev-critical">{t('investigation:updateFailed')}</p>}
      </div>
    </section>
  )
}

export function Alerts() {
  const { t, i18n } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedId = searchParams.get('alert')
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>(FILTERS[0])
  const [viewingClip, setViewingClip] = useState<EvidenceClip | null>(null)
  const [query, setQuery] = useState('')
  const [severity, setSeverity] = useState('all')
  const [sort, setSort] = useState('priority')
  function selectAlert(id: string) {
    setSearchParams((params) => {
      const next = new URLSearchParams(params)
      next.set('alert', id)
      return next
    }, { replace: true })
  }
  const { data: alerts, error, refetch } = usePolling(() => alertsApi.list(filter.status), 6000, [filter.status])
  const loadedAlerts = alerts?.filter((alert) => !filter.status || alert.status === filter.status)
  const filteredAlerts = loadedAlerts?.filter((alert) =>
    `${alert.plate_text} ${alert.camera_id}`.toLowerCase().includes(query.trim().toLowerCase()) &&
    (severity === 'all' || severityForAlert(alert) === severity),
  ).sort((a, b) => sort === 'priority' ? b.priority_score - a.priority_score : Date.parse(b.last_seen_at) - Date.parse(a.last_seen_at)) ?? []
  const selected = filteredAlerts.find((alert) => alert.id === selectedId) ?? filteredAlerts[0]

  return (
    <div className="investigation-workspace">
      <TopBar title={t('nav.alerts')} subtitle={t('investigation:triageDescription')} />
      <div className="iw-triage-toolbar">
        <div className="iw-status-filters" aria-label={t('investigation:statusFilter')}>
        {FILTERS.map((f) => (
          <Button
            key={f.key}
            size="sm"
            variant={filter.key === f.key ? 'primary' : 'secondary'}
            onClick={() => setFilter(f)}
            aria-pressed={filter.key === f.key}
          >
            {t(['assigned', 'in_progress', 'false_positive'].includes(f.key) ? `investigation:status_${f.key}` : `alerts.filters.${f.key}`)}
          </Button>
        ))}
        </div>
        <Button size="sm" variant="ghost" onClick={refetch} aria-label={t('investigation:refreshQueue')}><RefreshCw size={16} />{t('investigation:refreshQueue')}</Button>
      </div>
      <div className="iw-triage-content">
        {Boolean(error) && <RequestError onRetry={refetch} />}
        <div className="iw-triage-grid">
          <section className="iw-alert-queue" aria-label={t('investigation:alertQueue')}>
            <div className="iw-section-heading"><h2>{t('investigation:alertQueue')}</h2><span>{alerts ? t('investigation:loadedAlerts', { visible: filteredAlerts.length, total: loadedAlerts?.length ?? 0 }) : t('common.loading')}</span></div>
            <div className="iw-queue-controls">
              <label className="iw-filter-search"><Search size={16} /><Input aria-label={t('investigation:filterQuery')} placeholder={t('investigation:filterQuery')} value={query} onChange={(event) => setQuery(event.target.value)} /></label>
              <div>
                <label><span>{t('investigation:severity')}</span><select value={severity} onChange={(event) => setSeverity(event.target.value)}>
                  <option value="all">{t('investigation:allSeverities')}</option>
                  {(['critical', 'high', 'medium', 'low'] as const).map((value) => <option key={value} value={value}>{t(`severity.${value}`)}</option>)}
                </select></label>
                <label><span>{t('investigation:sort')}</span><select value={sort} onChange={(event) => setSort(event.target.value)}><option value="priority">{t('investigation:highestPriority')}</option><option value="latest">{t('investigation:latestFirst')}</option></select></label>
              </div>
            </div>
            {!alerts && !error && <div className="iw-loading" role="status"><p>{t('common.loading')}</p><div /><div /><div /></div>}
            {alerts && !error && !filteredAlerts.length && <div className="iw-queue-empty"><ShieldCheck size={28} /><h3>{t(loadedAlerts?.length ? 'investigation:noFilterMatches' : 'alerts.noAlerts')}</h3><p>{t(loadedAlerts?.length ? 'investigation:adjustFilters' : 'workspace.queueDescription')}</p>{(query || severity !== 'all') && <Button variant="secondary" onClick={() => { setQuery(''); setSeverity('all') }}>{t('investigation:clearFilters')}</Button>}</div>}
            <ol className="iw-queue-list">
              {filteredAlerts.map((alert) => <li key={alert.id}><button className={`iw-queue-row ${selected?.id === alert.id ? 'is-selected' : ''}`} aria-pressed={selected?.id === alert.id} onClick={() => selectAlert(alert.id)}>
                <span className="iw-queue-row-top"><SeverityBadge severity={severityForAlert(alert)} /><time dateTime={alert.last_seen_at}>{formatTime(alert.last_seen_at, i18n.language)}</time></span>
                <span className="iw-queue-plate plate-mono">{alert.plate_text}<ArrowRight size={16} /></span>
                <span className="iw-queue-camera">{alert.camera_id} · {t('alerts.sighting', { count: alert.sighting_count })}</span>
                <span className="iw-queue-status">{t(`investigation:status_${alert.status}`)} · {t(alert.match_rung === 'exact' ? 'alerts.exactMatch' : 'findVehicle.probableMatch')}</span>
              </button></li>)}
            </ol>
          </section>
          {selected ? <AlertDetail key={selected.id} alert={selected} onUpdated={refetch} onViewClip={setViewingClip} />
            : <section className="iw-detail-empty"><Bell size={36} strokeWidth={1.4} /><h2>{t('investigation:selectAlert')}</h2><p>{t('investigation:selectAlertDescription')}</p></section>}
        </div>
      </div>
      <SealedClipModal clip={viewingClip} onClose={() => setViewingClip(null)} />
    </div>
  )
}
