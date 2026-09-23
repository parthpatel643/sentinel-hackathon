import { useMemo, useState } from 'react'
import { LayoutGrid } from 'lucide-react'
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

  const visibleCameras = useMemo(() => {
    const sorted = [...(cameras ?? [])].sort(
      (a, b) => (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9),
    )
    return sorted.slice(0, layout.count)
  }, [cameras, layout])

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <TopBar
        title={t('nav.liveWall')}
        subtitle={cameras ? t('liveWall.registered', { count: cameras.length }) : undefined}
      />
      <div className="page-toolbar" role="group" aria-label={t('workspace.layout')}>
        <LayoutGrid size={15} className="text-text-tertiary" />
        <span className="mr-2 text-sm text-text-secondary">{t('workspace.layout')}</span>
        {LAYOUTS.map((option) => (
          <Button
            key={option.label}
            size="sm"
            variant={layout.label === option.label ? 'primary' : 'secondary'}
            onClick={() => setLayout(option)}
            aria-pressed={layout.label === option.label}
          >
            {option.label}
          </Button>
        ))}
        {cameras && cameras.length > layout.count && (
          <span className="ml-2 text-xs text-text-tertiary">
            {t('liveWall.showingOf', { shown: layout.count, total: cameras.length })}
          </span>
        )}
      </div>

      <div className="page-body">
        {Boolean(error) && <RequestError onRetry={refetch} />}
        {!cameras && !error && <p className="py-6 text-text-secondary">{t('common.loading')}</p>}
        {cameras && cameras.length === 0 && (
          <div className="empty-state"><p>{t('workspace.noCameras')}</p><Link className="text-link" to="/cameras">{t('cameras.addCamera')}</Link></div>
        )}
        <div
          className="live-wall-grid grid gap-4"
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

      <CameraDetailModal camera={selected} onClose={() => setSelected(null)} />
    </div>
  )
}
