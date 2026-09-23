import { useEffect, useState } from 'react'
import { ChevronRight, List, Map, MapPin, Navigation2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
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
  const { t } = useTranslation()
  const { data: cameras, loading, error, refetch } = usePolling(() => camerasApi.list(), 15000)
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
    color: '#087665',
    label: camera.name,
    onClick: () => setSelected(camera),
  }))

  return (
    <section className="flex h-full min-h-80 flex-col" aria-labelledby="field-nearby-heading">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border-subtle px-5 py-4 sm:px-8">
        <h1 id="field-nearby-heading" className="text-2xl font-semibold tracking-tight">{t('field.nav.nearby')}</h1>
        <div role="tablist" aria-label={t('field.nav.nearby')} className="flex rounded-md bg-bg-inset p-1">
          <button
            id="field-nearby-tab-map"
            type="button"
            role="tab"
            aria-selected={view === 'map'}
            aria-controls="field-nearby-map-panel"
            onClick={() => setView('map')}
            className={`flex min-h-10 items-center justify-center gap-2 rounded-md px-3 text-sm font-medium focus-visible:outline-2 focus-visible:outline-accent ${view === 'map' ? 'bg-bg-raised text-accent' : 'text-text-secondary hover:bg-bg-hover'}`}
          >
            <Map size={16} aria-hidden="true" />
            {t('field.nearby.map')}
          </button>
          <button
            id="field-nearby-tab-list"
            type="button"
            role="tab"
            aria-selected={view === 'list'}
            aria-controls="field-nearby-list-panel"
            onClick={() => setView('list')}
            className={`flex min-h-10 items-center justify-center gap-2 rounded-md px-3 text-sm font-medium focus-visible:outline-2 focus-visible:outline-accent ${view === 'list' ? 'bg-bg-raised text-accent' : 'text-text-secondary hover:bg-bg-hover'}`}
          >
            <List size={16} aria-hidden="true" />
            {t('field.nearby.list')}
          </button>
        </div>
      </div>
      {loading && <p role="status" className="px-5 py-3 text-sm text-text-secondary">{t('common.loading')}</p>}
      {!!error && (
        <div role="alert" className="flex flex-wrap items-center gap-x-3 bg-sev-critical/10 px-5 py-3 text-sm text-sev-critical">
          <p className="flex-1">{t('workspace.refreshError')}</p>
          <button onClick={refetch} className="min-h-10 rounded-md px-2 font-medium underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-accent">{t('common.retry')}</button>
        </div>
      )}
      {!loading && !error && withDistance.length === 0 && (
        <div className="flex items-center gap-3 border-b border-border-subtle px-5 py-4">
          <MapPin size={20} className="shrink-0 text-text-tertiary" aria-hidden="true" />
          <p className="text-sm leading-relaxed text-text-secondary">{t('field.nearby.noCameras')}</p>
        </div>
      )}

      {view === 'map' ? (
        <div
          id="field-nearby-map-panel"
          role="tabpanel"
          aria-labelledby="field-nearby-tab-map"
          className="relative min-h-64 flex-1"
        >
          <MapView markers={markers} className="absolute inset-0" />
        </div>
      ) : (
        <div
          id="field-nearby-list-panel"
          role="tabpanel"
          aria-labelledby="field-nearby-tab-list"
          className="flex-1 overflow-y-auto px-5 sm:px-8"
        >
          <div className="divide-y divide-border-subtle">
            {withDistance.map(({ camera, distanceKm }) => (
              <button
                key={camera.camera_id}
                type="button"
                aria-label={camera.name}
                onClick={() => setSelected(camera)}
                className="flex min-h-20 w-full items-center justify-between gap-3 py-4 text-left hover:bg-bg-hover focus-visible:outline-2 focus-visible:outline-accent"
              >
                <div className="min-w-0">
                  <p className="break-words text-base font-medium text-text-primary">{camera.name}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <SeverityBadge severity={statusToSeverity(camera.status)} label={t(`cameraStatus.${camera.status}`)} />
                    {distanceKm != null && (
                      <span className="flex items-center gap-1 text-xs text-text-secondary">
                        <Navigation2 size={13} aria-hidden="true" />
                        {t('field.alerts.kmAway', { distance: distanceKm.toFixed(1) })}
                      </span>
                    )}
                  </div>
                </div>
                <ChevronRight size={18} className="shrink-0 text-text-tertiary" aria-hidden="true" />
              </button>
            ))}
          </div>
        </div>
      )}

      <CameraDetailModal camera={selected} onClose={() => setSelected(null)} />
    </section>
  )
}
