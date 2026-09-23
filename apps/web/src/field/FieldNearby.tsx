import { useEffect, useState } from 'react'
import { Navigation2 } from 'lucide-react'
import { camerasApi } from '../lib/api'
import { usePolling } from '../lib/usePolling'
import { MapView, type MapMarker } from '../components/MapView'
import { CameraDetailModal } from '../components/CameraDetailModal'
import { SeverityBadge, statusToSeverity } from '../components/ui/SeverityBadge'
import type { Camera } from '../lib/types'

function haversineKm(a: { lat: number; lon: number }, b: { lat: number; lon: number }): number {
  const R = 6371
  const dLat = ((b.lat - a.lat) * Math.PI) / 180
  const dLon = ((b.lon - a.lon) * Math.PI) / 180
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((a.lat * Math.PI) / 180) * Math.cos((b.lat * Math.PI) / 180) * Math.sin(dLon / 2) ** 2
  return R * 2 * Math.asin(Math.sqrt(h))
}

/** docs/03-UX-DESIGN.md §5.4: "map of cameras around me, tap to view (HLS,
 * low-bandwidth profile)." Reuses the same MapView/CameraDetailModal the
 * Operator Console uses (same live-preview endpoint, same honest
 * "not available outside our own relay" fallback) — a phone doesn't need
 * a different video pipeline, just a smaller screen around it. */
export function FieldNearby() {
  const { data: cameras } = usePolling(() => camerasApi.list(), 15000)
  const [myPosition, setMyPosition] = useState<{ lat: number; lon: number } | null>(null)
  const [selected, setSelected] = useState<Camera | null>(null)
  const [view, setView] = useState<'map' | 'list'>('map')

  useEffect(() => {
    if (!navigator.geolocation) return
    const id = navigator.geolocation.watchPosition(
      (pos) => setMyPosition({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
      () => {},
      { enableHighAccuracy: false },
    )
    return () => navigator.geolocation.clearWatch(id)
  }, [])

  const withDistance = (cameras ?? [])
    .filter((c): c is Camera & { location: NonNullable<Camera['location']> } => c.location !== null)
    .map((c) => ({
      camera: c,
      distanceKm: myPosition ? haversineKm(myPosition, c.location) : null,
    }))
    .sort((a, b) => (a.distanceKm ?? 0) - (b.distanceKm ?? 0))

  const markers: MapMarker[] = withDistance.map(({ camera }) => ({
    id: camera.camera_id,
    lat: camera.location.lat,
    lon: camera.location.lon,
    color: 'oklch(0.68 0.16 245)',
    label: camera.name,
    onClick: () => setSelected(camera),
  }))

  return (
    <div className="flex h-full flex-col">
      <div className="flex gap-2 border-b border-border-subtle p-3">
        <button
          onClick={() => setView('map')}
          className={view === 'map' ? 'flex-1 rounded-lg bg-accent/15 py-2 text-sm font-medium text-accent' : 'flex-1 rounded-lg bg-bg-inset py-2 text-sm text-text-secondary'}
        >
          Map
        </button>
        <button
          onClick={() => setView('list')}
          className={view === 'list' ? 'flex-1 rounded-lg bg-accent/15 py-2 text-sm font-medium text-accent' : 'flex-1 rounded-lg bg-bg-inset py-2 text-sm text-text-secondary'}
        >
          List
        </button>
      </div>

      {view === 'map' ? (
        <div className="relative flex-1">
          <MapView markers={markers} className="absolute inset-0" />
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-3">
          {withDistance.length === 0 && (
            <p className="py-12 text-center text-sm text-text-tertiary">No cameras with a known location yet.</p>
          )}
          <div className="flex flex-col gap-2">
            {withDistance.map(({ camera, distanceKm }) => (
              <button
                key={camera.camera_id}
                onClick={() => setSelected(camera)}
                className="flex items-center justify-between rounded-xl border border-border-subtle bg-bg-raised p-3 text-left"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-text-primary">{camera.name}</p>
                  <div className="mt-1 flex items-center gap-2">
                    <SeverityBadge severity={statusToSeverity(camera.status)} label={camera.status} />
                    {distanceKm != null && (
                      <span className="flex items-center gap-1 text-xs text-text-tertiary">
                        <Navigation2 size={11} />
                        {distanceKm.toFixed(1)} km
                      </span>
                    )}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      <CameraDetailModal camera={selected} onClose={() => setSelected(null)} />
    </div>
  )
}
