import { useMemo, useState } from 'react'
import { Camera as CameraIcon, LayoutGrid, Maximize2, RefreshCw, Search } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { TopBar } from '../components/layout/TopBar'
import { CameraDetailModal } from '../components/CameraDetailModal'
import { LiveWallTile } from '../components/LiveWallTile'
import { Button } from '../components/ui/Button'
import { RequestError } from '../components/ui/RequestError'
import { Link } from 'react-router-dom'
import { camerasApi, detectionsApi } from '../lib/api'
import { usePolling } from '../lib/usePolling'
import type { Camera, Detection } from '../lib/types'
import { Input } from '../components/ui/Input'
import { SeverityBadge, statusToSeverity } from '../components/ui/SeverityBadge'
import './monitoring-workspace.css'

const LAYOUTS = [
  { label: '1', cols: 1, count: 1 },
  { label: '2×2', cols: 2, count: 4 },
  { label: '3×3', cols: 3, count: 9 },
  { label: '4×4', cols: 4, count: 16 },
] as const

const STATUS_ORDER: Record<string, number> = { live: 0, degraded: 1, connecting: 2, unknown: 3, down: 4 }

/** Multi-camera grid — docs/03-UX-DESIGN.md §4.3. Drag-to-rearrange, saved
 * per-user layouts and shareable links are documented as a deferred next
 * step (see docs/05-DELIVERY-PLAN.md M7); this ships the parts that carry
 * the actual "only visible tiles stream" performance/compliance rule, a
 * real transport/status badge per tile, and the layout density picker. */
export function LiveWall() {
  const { t } = useTranslation()
  const [layout, setLayout] = useState<(typeof LAYOUTS)[number]>(LAYOUTS[1])
  const [selected, setSelected] = useState<Camera | null>(null)
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('all')
  const [included, setIncluded] = useState<string[] | null>(null)
  const [focused, setFocused] = useState('')
  const { data: cameras, error, refetch } = usePolling(() => camerasApi.list(), 10000)
  // A single shared poll for recent detections, rather than one per tile —
  // dozens of tiles polling detections individually would multiply load for
  // no benefit; every tile just looks up its own camera_id in the result.
  const { data: recentDetections } = usePolling(() => detectionsApi.search({ limit: 50 }), 8000)

  const latestByCamera = useMemo(() => {
    const map = new Map<string, Detection>()
    for (const detection of recentDetections ?? []) {
      const existing = map.get(detection.camera_id)
      if (!existing || detection.observed_at > existing.observed_at) map.set(detection.camera_id, detection)
    }
    return map
  }, [recentDetections])

  const filteredCameras = useMemo(() =>
    [...(cameras ?? [])].filter((camera) =>
      (status === 'all' || camera.status === status) &&
      `${camera.name} ${camera.camera_id} ${camera.department_name ?? ''}`.toLowerCase().includes(query.trim().toLowerCase()),
    ).sort(
      (a, b) => (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9),
    ), [cameras, query, status])
  const chosen = filteredCameras.filter((camera) => included === null || included.includes(camera.camera_id))
  const focusCamera = chosen.find((camera) => camera.camera_id === focused) ?? chosen[0]
  const visibleCameras = layout.count === 1 ? (focusCamera ? [focusCamera] : []) : chosen.slice(0, layout.count)

  function toggleCamera(id: string) {
    setIncluded((current) => {
      const ids = current ?? (cameras ?? []).map((camera) => camera.camera_id)
      return ids.includes(id) ? ids.filter((value) => value !== id) : [...ids, id]
    })
  }

  return (
    <div className="monitoring-workspace flex min-h-0 flex-1 flex-col">
      <TopBar
        title={t('nav.liveWall')}
        subtitle={cameras ? t('liveWall.registered', { count: cameras.length }) : undefined}
      />
      <div className="monitoring-workbench">
        <section className="monitoring-selector" aria-label={t('monitoring:selection')}>
          <div className="monitoring-panel-heading">
            <CameraIcon size={18} />
            <h2>{t('monitoring:selection')}</h2>
            <span className="monitoring-count">{cameras?.length ?? '—'}</span>
          </div>
          <p className="monitoring-help">{t('monitoring:selectionHelp')}</p>
          <div className="monitoring-selector-filters">
            <div className="monitoring-search"><Search size={16} /><Input aria-label={t('workspace.filterCameras')} placeholder={t('workspace.filterCameras')} value={query} onChange={(event) => setQuery(event.target.value)} /></div>
            <select aria-label={t('workspace.allStatuses')} value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="all">{t('workspace.allStatuses')}</option>
              {Object.keys(STATUS_ORDER).map((value) => <option key={value} value={value}>{t(`cameraStatus.${value}`)}</option>)}
            </select>
          </div>
          <div className="monitoring-selection-actions">
            <button onClick={() => setIncluded(null)}>{t('monitoring:selectAll')}</button>
            <button onClick={() => setIncluded([])}>{t('monitoring:clearSelection')}</button>
          </div>
          <div className="monitoring-camera-options">
            {filteredCameras.map((camera) => (
              <label key={camera.camera_id} className="monitoring-camera-option" data-selected={included === null || included.includes(camera.camera_id)}>
                <input type="checkbox" aria-label={camera.name} checked={included === null || included.includes(camera.camera_id)} onChange={() => toggleCamera(camera.camera_id)} />
                <span className="monitoring-camera-option-copy"><strong>{camera.name}</strong><span>{camera.department_name ?? camera.camera_id}</span><SeverityBadge severity={statusToSeverity(camera.status)} label={t(`cameraStatus.${camera.status}`)} /></span>
              </label>
            ))}
            {cameras && cameras.length > 0 && filteredCameras.length === 0 && <p className="monitoring-help">{t('workspace.noMatchingCameras')}</p>}
          </div>
          <Link className="monitoring-registry-link" to="/cameras">{t('monitoring:registry')} <span aria-hidden="true">→</span></Link>
        </section>
        <section className="monitoring-stage" aria-label={t('monitoring:wall')}>
      <div className="monitoring-wall-toolbar" role="group" aria-label={t('workspace.layout')}>
        <LayoutGrid size={15} className="text-text-tertiary" />
        <span className="mr-2 text-sm text-text-secondary">{t('workspace.layout')}</span>
        {LAYOUTS.map((option) => (
          <Button
            key={option.label}
            size="sm"
            variant={layout.label === option.label ? 'primary' : 'secondary'}
            onClick={() => setLayout(option)}
            aria-pressed={layout.label === option.label}
            aria-label={option.count === 1 ? t('monitoring:focus') : option.label}
          >
            {option.count === 1 ? <><Maximize2 size={14} />{t('monitoring:focus')}</> : option.label}
          </Button>
        ))}
        <Button variant="ghost" size="sm" className="ml-auto" aria-label={t('monitoring:refresh')} onClick={refetch}><RefreshCw size={16} /></Button>
      </div>
      <div className="monitoring-wall-summary">
        <span>{t('monitoring:capacity', { shown: visibleCameras.length, total: chosen.length })}</span>
        {layout.count === 1 && chosen.length > 0 && <select aria-label={t('monitoring:focusCamera')} value={focusCamera?.camera_id ?? ''} onChange={(event) => setFocused(event.target.value)}>{chosen.map((camera) => <option value={camera.camera_id} key={camera.camera_id}>{camera.name}</option>)}</select>}
      </div>
      <div className="monitoring-wall-content">
        {Boolean(error) && <RequestError onRetry={refetch} />}
        {!cameras && !error && <p className="py-6 text-text-secondary">{t('common.loading')}</p>}
        {cameras && cameras.length === 0 && (
          <div className="empty-state"><p>{t('workspace.noCameras')}</p><Link className="text-link" to="/cameras">{t('cameras.addCamera')}</Link></div>
        )}
        {cameras && cameras.length > 0 && visibleCameras.length === 0 && <div className="empty-state"><CameraIcon size={30} /><p>{t('monitoring:noSelection')}</p></div>}
        <div
          className="live-wall-grid monitoring-feed-grid grid"
          style={{ gridTemplateColumns: `repeat(${layout.cols}, minmax(0, 1fr))` }}
        >
          {visibleCameras.map((camera) => (
            <LiveWallTile
              key={camera.camera_id}
              camera={camera}
              latestDetection={latestByCamera.get(camera.camera_id)}
              onOpen={setSelected}
            />
          ))}
        </div>
      </div>
      <p className="monitoring-wall-note">{t('monitoring:wallHelp')}</p>
      </section>
      </div>

      <CameraDetailModal camera={selected} onClose={() => setSelected(null)} />
    </div>
  )
}
