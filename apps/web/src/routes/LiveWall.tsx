import { useMemo, useState } from 'react'
import { LayoutGrid } from 'lucide-react'
import { TopBar } from '../components/layout/TopBar'
import { CameraDetailModal } from '../components/CameraDetailModal'
import { LiveWallTile } from '../components/LiveWallTile'
import { Button } from '../components/ui/Button'
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
  const [layout, setLayout] = useState<(typeof LAYOUTS)[number]>(LAYOUTS[1])
  const [selected, setSelected] = useState<Camera | null>(null)
  const { data: cameras } = usePolling(() => camerasApi.list(), 10000)
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
      <TopBar title="Live Wall" subtitle={cameras ? `${cameras.length} registered` : undefined} />
      <div className="flex items-center gap-2 border-b border-border-subtle px-6 py-3">
        <LayoutGrid size={15} className="text-text-tertiary" />
        {LAYOUTS.map((option) => (
          <Button
            key={option.label}
            size="sm"
            variant={layout.label === option.label ? 'primary' : 'secondary'}
            onClick={() => setLayout(option)}
          >
            {option.label}
          </Button>
        ))}
        {cameras && cameras.length > layout.count && (
          <span className="ml-2 text-xs text-text-tertiary">
            Showing {layout.count} of {cameras.length} — live cameras first
          </span>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {cameras && cameras.length === 0 && (
          <p className="p-6 text-sm text-text-tertiary">
            No cameras registered yet. Run catalogue discovery or add one manually via the API.
          </p>
        )}
        <div
          className="grid gap-3"
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
