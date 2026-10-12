import { useMemo, useState } from 'react'
import { ChevronDown, ChevronUp, RefreshCw, Search } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { alertsApi } from '../lib/api'
import { usePolling } from '../lib/usePolling'
import { useLiveEvents } from '../lib/liveEvents'
import { useJurisdiction } from '../lib/jurisdiction'
import { CLOSED_STATUSES, WORKING_STATUSES, groupAlertsByVehicle, severityForAlert, type VehicleGroup } from '../lib/vehicles'
import { formatIst } from '../lib/time'
import { TopBar } from '../components/layout/TopBar'
import { SealedClipModal } from '../components/SealedClipModal'
import { RequestError } from '../components/ui/RequestError'
import { ZoneEventQueue } from '../components/ZoneEventQueue'
import { CameraViewQueue } from '../components/CameraViewQueue'
import { VehicleBoardHead, VehicleBoardRows } from '../components/gate/VehicleBoard'
import { SightingPass } from '../components/gate/SightingPass'
import type { Alert, AlertStatus, EvidenceClip } from '../lib/types'
import './investigation-workspace.css'

type Board = 'new' | 'working' | 'closed' | 'all'
const BOARDS: { key: Board; statuses?: AlertStatus[]; labelKey: string }[] = [
  { key: 'new', statuses: ['new'], labelKey: 'gate:unacknowledged' },
  { key: 'working', statuses: WORKING_STATUSES, labelKey: 'gate:working' },
  { key: 'closed', statuses: CLOSED_STATUSES, labelKey: 'gate:closedToday' },
  { key: 'all', labelKey: 'alerts.filters.all' },
]
const HISTORY_LIMIT = 60

function cameraClock(iso: string | null, language: string, unknown: string) {
  return iso ? formatIst(iso, language, { second: '2-digit' }) : unknown
}

/** Every hit folded into the selected vehicle. Repeat reads of one pass are
 * one event for the operator, so they show as one line until expanded. */
function HitHistory({ group }: { group: VehicleGroup }) {
  const { t, i18n } = useTranslation()
  const [open, setOpen] = useState(false)
  const first = group.alerts.reduce((a, b) => (Date.parse(a.first_seen_at) <= Date.parse(b.first_seen_at) ? a : b))
  const unknown = t('common.timeUnknown')
  const span = `${cameraClock(first.first_seen_camera_time, i18n.language, unknown)} → ${cameraClock(group.lastCameraTime, i18n.language, unknown)}`
  const sorted = [...group.alerts].sort((a, b) => Date.parse(b.last_seen_at) - Date.parse(a.last_seen_at))
  return (
    <div className="gb-history">
      <div className="gb-history-head">
        <div className="gb-lbl">{t('gate:hitHistory')}</div>
        {group.hits > 1 && (
          <button type="button" className="gb-btn gb-sm gb-ghost" aria-expanded={open} onClick={() => setOpen(!open)}>
            {open ? <ChevronUp className="gb-ico gb-s" aria-hidden="true" /> : <ChevronDown className="gb-ico gb-s" aria-hidden="true" />}
            {open ? t('gate:hideHits') : t('gate:showAllHits', { count: group.hits })}
          </button>
        )}
      </div>
      <p className="gb-history-line">{t('gate:hitHistorySummary', { count: group.hits, camera: group.cameraIds.join(', '), span })}</p>
      <dl className="gb-history-times">
        <div><dt>{t('investigation:firstSeen')}</dt><dd>{cameraClock(first.first_seen_camera_time, i18n.language, unknown)}</dd></div>
        <div><dt>{t('investigation:lastSeen')}</dt><dd>{cameraClock(group.lastCameraTime, i18n.language, unknown)}</dd></div>
      </dl>
      {group.hits > 1 && group.cameraIds.length === 1 && <p className="gb-history-note">{t('gate:repeatPass')}</p>}
      {open && (
        <ol className="gb-history-list">
          {sorted.slice(0, HISTORY_LIMIT).map((alert) => (
            <li key={alert.id}>
              <span className="gb-data">{cameraClock(alert.last_seen_camera_time, i18n.language, t('common.timeUnknownShort'))}</span>
              <span className="gb-data">{alert.camera_id}</span>
              <span>{t(`investigation:status_${alert.status}`)}</span>
              <span className="gb-data">{Math.round(alert.match_confidence * 100)}%</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

function inBoard(alert: Alert, board: Board) {
  const statuses = BOARDS.find((b) => b.key === board)?.statuses
  return !statuses || statuses.includes(alert.status)
}

export function Alerts() {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedId = searchParams.get('alert')
  const { cameras, inScope } = useJurisdiction()
  const [board, setBoard] = useState<Board>('new')
  const [viewingClip, setViewingClip] = useState<EvidenceClip | null>(null)
  const [query, setQuery] = useState('')
  const [severity, setSeverity] = useState('all')
  const [sort, setSort] = useState('priority')
  // One request for every state, so each board tab shows its real count.
  const { data: alerts, error, refetch } = usePolling(() => alertsApi.list(), 20000)
  useLiveEvents((kind) => { if (kind === 'alert') refetch() })
  const zoneHighlight = searchParams.get('zone')

  const scoped = useMemo(() => (alerts ?? []).filter((a) => inScope(a.camera_id)), [alerts, inScope])
  const boardAlerts = useMemo(() => scoped.filter((a) => inBoard(a, board)), [scoped, board])
  const loadedGroups = useMemo(() => groupAlertsByVehicle(boardAlerts), [boardAlerts])
  const groups = useMemo(() => {
    const q = query.trim().toLowerCase()
    const list = loadedGroups.filter((g) =>
      (!q || `${g.plate} ${g.cameraIds.join(' ')}`.toLowerCase().includes(q)) &&
      (severity === 'all' || severityForAlert({ priority_score: g.priorityScore }) === severity))
    return sort === 'latest' ? [...list].sort((a, b) => Date.parse(b.lead.last_seen_at) - Date.parse(a.lead.last_seen_at)) : list
  }, [loadedGroups, query, severity, sort])
  const selected = groups.find((g) => g.alerts.some((a) => a.id === selectedId)) ?? groups[0]
  const counts = Object.fromEntries(BOARDS.map((b) => [b.key, new Set(scoped.filter((a) => inBoard(a, b.key)).map((a) => a.plate_text)).size]))

  function select(plate: string) {
    const group = groups.find((g) => g.plate === plate)
    if (!group) return
    setSearchParams((params) => {
      const next = new URLSearchParams(params)
      next.set('alert', group.lead.id)
      return next
    }, { replace: true })
  }

  return (
    <div className="gb-alerts">
      <TopBar title={t('nav.alerts')} titleKey="nav.alerts" subtitle={t('gate:pageNote')} actions={
        <button type="button" className="gb-btn" onClick={refetch} aria-label={t('investigation:refreshQueue')}><RefreshCw className="gb-ico" aria-hidden="true" />{t('investigation:refreshQueue')}</button>
      } />
      <div className="gb-page">
        {Boolean(error) && <RequestError onRetry={refetch} />}
        <div className="gb-split">
          <section className="gb-board" aria-label={t('investigation:alertQueue')}>
            <div className="gb-board-top">
              <h2 className="gb-board-title">{t('gate:watchlistBoard')}</h2>
              <span className="gb-tally"><b>{boardAlerts.length}</b>{t('gate:hitNoun', { count: boardAlerts.length })}<span className="gb-sep">·</span><b>{loadedGroups.length}</b>{t('gate:vehicleNoun', { count: loadedGroups.length })}</span>
              <span className="gb-spacer" />
              <span className="gb-key-new">{t('gate:litKey')}</span>
            </div>
            <div className="gb-board-tools">
              <div className="gb-seg" role="group" aria-label={t('investigation:statusFilter')}>
                {BOARDS.map((b) => (
                  <button key={b.key} type="button" aria-pressed={board === b.key} onClick={() => setBoard(b.key)}>
                    {t(b.labelKey)}{alerts && <span className="gb-n">{counts[b.key]}</span>}
                  </button>
                ))}
              </div>
              <label className="gb-field gb-sm gb-grow">
                <Search className="gb-ico" aria-hidden="true" />
                <input aria-label={t('investigation:filterQuery')} placeholder={t('investigation:filterQuery')} value={query} onChange={(e) => setQuery(e.target.value)} />
              </label>
              <label className="gb-inline-select"><span>{t('investigation:severity')}</span>
                <select value={severity} onChange={(e) => setSeverity(e.target.value)}>
                  <option value="all">{t('investigation:allSeverities')}</option>
                  {(['critical', 'high', 'medium', 'low'] as const).map((value) => <option key={value} value={value}>{t(`severity.${value}`)}</option>)}
                </select>
              </label>
              <label className="gb-inline-select"><span>{t('investigation:sort')}</span>
                <select value={sort} onChange={(e) => setSort(e.target.value)}>
                  <option value="priority">{t('investigation:highestPriority')}</option>
                  <option value="latest">{t('investigation:latestFirst')}</option>
                </select>
              </label>
            </div>
            {!alerts && !error && <p className="gb-board-foot" role="status">{t('common.loading')}</p>}
            {alerts && !error && groups.length === 0 && (
              <div className="gb-empty">
                <b>{t(loadedGroups.length ? 'investigation:noFilterMatches' : board === 'new' ? 'alerts.noAlerts' : board === 'working' ? 'gate:workingEmpty' : 'gate:closedEmpty')}</b>
                <span>{t(loadedGroups.length ? 'investigation:adjustFilters' : board === 'working' ? 'gate:workingEmptyHelp' : board === 'closed' ? 'gate:closedEmptyHelp' : 'gate:nothingWaitingHelp')}</span>
                {(query || severity !== 'all') && <button type="button" className="gb-btn gb-sm" onClick={() => { setQuery(''); setSeverity('all') }}>{t('investigation:clearFilters')}</button>}
              </div>
            )}
            {groups.length > 0 && <>
              <VehicleBoardHead />
              <VehicleBoardRows groups={groups} cameras={cameras} selectedPlate={selected?.plate} onSelect={select} onChanged={refetch} />
            </>}
            <div className="gb-board-foot">
              <span>{alerts ? t('investigation:loadedAlerts', { visible: groups.length, total: loadedGroups.length }) : t('common.loading')}</span>
              <span>{t('gate:onePerVehicle')}</span>
            </div>
          </section>

          <div className="gb-stack gb-sticky">
            {selected
              ? <SightingPass key={selected.plate} group={selected} cameras={cameras} onChanged={refetch} onViewClip={setViewingClip} detailed>
                  <HitHistory group={selected} />
                </SightingPass>
              : alerts && !error && <section className="gb-empty gb-pass-empty" aria-label={t('investigation:selectedAlert')}><b>{t('investigation:selectAlert')}</b><span>{t('investigation:selectAlertDescription')}</span></section>}
          </div>
        </div>
        <div className="gb-row-2 gb-side-queues">
          <ZoneEventQueue highlightId={zoneHighlight} />
          <CameraViewQueue />
        </div>
      </div>
      <SealedClipModal clip={viewingClip} onClose={() => setViewingClip(null)} />
    </div>
  )
}
