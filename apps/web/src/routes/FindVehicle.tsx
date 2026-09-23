import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ArrowRight, Download, Pause, Play, Search } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { detectionsApi, watchlistApi } from '../lib/api'
import { ApiError } from '../lib/http'
import { MapView, type MapMarker } from '../components/MapView'
import { Card } from '../components/ui/Card'
import { Input } from '../components/ui/Input'
import { Button } from '../components/ui/Button'
import { SeverityBadge } from '../components/ui/SeverityBadge'
import { cn } from '../lib/cn'
import type { RoutePoint, VehicleRoute } from '../lib/types'
import { TopBar } from '../components/layout/TopBar'
import i18n from '../lib/i18n'

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString(i18n.language, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function ConfidenceBar({ point }: { point: RoutePoint }) {
  const { t } = useTranslation()
  const pct = Math.round(point.plate_confidence * 100)
  const tooltip = point.match_rung === 'exact' ? t('findVehicle.readClearly') : t('findVehicle.matchedByAmbiguity')
  return (
    <div title={tooltip} className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-bg-inset">
        <div
          className={point.match_rung === 'exact' ? 'h-full bg-ok' : 'h-full bg-sev-high'}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-text-tertiary">{pct}%</span>
    </div>
  )
}

function ArmBoloPanel({ plate, onArmed }: { plate: string; onArmed: () => void }) {
  const { t } = useTranslation()
  const [busy, setBusy] = useState(false)
  const [armed, setArmed] = useState<{ retro_alerts_created: number; retro_sightings_found: number } | null>(
    null,
  )
  const [error, setError] = useState<string | null>(null)

  async function arm() {
    setBusy(true)
    setError(null)
    try {
      const result = await watchlistApi.bolo({ plate, entry_type: 'bolo', priority: 'high' })
      setArmed(result)
      onArmed()
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : t('findVehicle.armError'))
    } finally {
      setBusy(false)
    }
  }

  if (armed) {
    return (
      <Card className="p-6 text-center">
        <p className="text-sm font-medium text-ok">{t('findVehicle.watchArmed', { plate })}</p>
        <p className="mt-1 text-sm text-text-secondary">
          {armed.retro_sightings_found > 0
            ? t('findVehicle.foundPastSightings', { count: armed.retro_sightings_found })
            : t('findVehicle.noPastSightings')}
        </p>
      </Card>
    )
  }

  return (
    <Card className="flex flex-col items-center gap-3 p-8 text-center">
      <p className="plate-mono text-2xl font-semibold text-text-primary">{plate}</p>
      <p className="max-w-sm text-sm text-text-secondary">{t('findVehicle.noSightingsIn24h')}</p>
      <Button onClick={arm} disabled={busy}>
        {busy ? t('findVehicle.arming') : t('findVehicle.watchForVehicle')}
      </Button>
      {error && <p className="text-xs text-sev-critical">{error}</p>}
    </Card>
  )
}

function ExportReportButton({ plate }: { plate: string }) {
  const { t } = useTranslation()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function download() {
    setBusy(true)
    setError(null)
    try {
      const { blob, filename } = await detectionsApi.movementReport(plate)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
    } catch {
      setError(t('findVehicle.exportFailed'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <Button size="sm" variant="secondary" onClick={download} disabled={busy}>
        <Download size={14} />
        {busy ? t('findVehicle.preparingReport') : t('findVehicle.exportReport')}
      </Button>
      {error && <p className="text-xs text-sev-critical">{error}</p>}
    </div>
  )
}

export function FindVehicle() {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()
  const plateParam = searchParams.get('plate') ?? ''
  const [input, setInput] = useState(plateParam)
  const [route, setRoute] = useState<VehicleRoute | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  // Replay route (docs/03-UX-DESIGN.md \u00a74.4 — "the single most demo-able
  // interaction in the product"): animates a marker along the polyline,
  // pausing briefly at each hop, and highlights that hop in the timeline in
  // sync. Position updates run on requestAnimationFrame directly (not
  // through the point-search state above) so the 60fps tween doesn't
  // re-render the timeline list on every frame — only activeHopIndex does,
  // and only once per hop.
  const [activeHopIndex, setActiveHopIndex] = useState<number | null>(null)
  const [replaying, setReplaying] = useState(false)
  const [vehiclePosition, setVehiclePosition] = useState<[number, number] | null>(null)
  const replayTokenRef = useRef(0)

  useEffect(() => {
    let cancelled = false
    setInput(plateParam)
    setRoute(null)
    setError(null)
    if (!plateParam) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    detectionsApi
      .vehicleRoute(plateParam)
      .then((result) => { if (!cancelled) setRoute(result) })
      .catch((err) => { if (!cancelled) setError(err instanceof ApiError ? String(err.detail) : t('findVehicle.searchFailed')) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plateParam, refreshKey, t])

  // Cancel any in-flight replay if the operator starts a new search.
  useEffect(() => {
    replayTokenRef.current += 1
    setReplaying(false)
    setActiveHopIndex(null)
    setVehiclePosition(null)
    return () => { replayTokenRef.current += 1 }
  }, [plateParam])

  function handleSearch() {
    const trimmed = input.trim()
    if (!trimmed) return
    setSearchParams({ plate: trimmed })
  }

  const locatedPoints =
    route?.points
      .map((p, i) => ({ ...p, index: i }))
      .filter((p): p is typeof p & { location: NonNullable<RoutePoint['location']> } => p.location !== null) ?? []

  const unmappedCount = (route?.points.length ?? 0) - locatedPoints.length

  function playReplay() {
    if (locatedPoints.length < 2) return
    const token = ++replayTokenRef.current
    setReplaying(true)

    const DWELL_MS = 550
    const TRAVEL_MS = 1100
    const easeInOutQuad = (t: number) => (t < 0.5 ? 2 * t * t : 1 - ((-2 * t + 2) ** 2) / 2)

    function dwellThenTravel(hop: number) {
      if (replayTokenRef.current !== token) return
      setActiveHopIndex(locatedPoints[hop].index)
      setVehiclePosition([locatedPoints[hop].location.lon, locatedPoints[hop].location.lat])
      if (hop >= locatedPoints.length - 1) {
        setTimeout(() => {
          if (replayTokenRef.current === token) setReplaying(false)
        }, DWELL_MS)
        return
      }
      setTimeout(() => {
        if (replayTokenRef.current !== token) return
        const from = locatedPoints[hop].location
        const to = locatedPoints[hop + 1].location
        const start = performance.now()
        function step(now: number) {
          if (replayTokenRef.current !== token) return
          const t = Math.min(1, (now - start) / TRAVEL_MS)
          const eased = easeInOutQuad(t)
          setVehiclePosition([from.lon + (to.lon - from.lon) * eased, from.lat + (to.lat - from.lat) * eased])
          if (t < 1) requestAnimationFrame(step)
          else dwellThenTravel(hop + 1)
        }
        requestAnimationFrame(step)
      }, DWELL_MS)
    }

    dwellThenTravel(0)
  }

  function stopReplay() {
    replayTokenRef.current += 1
    setReplaying(false)
    setActiveHopIndex(null)
    setVehiclePosition(null)
  }

  const markers: MapMarker[] = locatedPoints.map((p) => ({
    id: `${p.camera_id}-${p.index}`,
    lat: p.location.lat,
    lon: p.location.lon,
    color: '#087665',
    label: `${p.index + 1}. ${p.camera_name} · ${formatTime(p.observed_at)}`,
    number: p.index + 1,
    pulse: activeHopIndex === p.index,
  }))

  const routeSegments = locatedPoints.slice(0, -1).map((p, i) => ({
    from: [p.location.lon, p.location.lat] as [number, number],
    to: [locatedPoints[i + 1].location.lon, locatedPoints[i + 1].location.lat] as [number, number],
    confirmed: locatedPoints[i + 1].match_rung !== 'ambiguity_class',
  }))

  if (!plateParam) {
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        <TopBar title={t('findVehicle.title')} subtitle={t('workspace.investigationDescription')} />
        <div className="page-body">
          <div className="investigation-start">
            <form className="investigation-form" onSubmit={(e) => { e.preventDefault(); handleSearch() }}>
              <Search size={32} strokeWidth={1.5} className="mb-8 text-accent" />
              <h2 className="mb-3 text-2xl font-semibold tracking-tight">{t('workspace.startWithPlate')}</h2>
              <p className="mb-8 max-w-lg text-sm leading-relaxed text-text-secondary">{t('findVehicle.searchesLast24h')}</p>
              <label htmlFor="investigation-plate" className="mb-2 block text-sm font-medium">{t('workspace.plate')}</label>
              <Input
                id="investigation-plate"
                required
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={t('findVehicle.platePlaceholder')}
                className="plate-mono h-14 w-full text-lg uppercase"
              />
              <Button type="submit" className="mt-4" disabled={!input.trim()}>{t('findVehicle.search')}<ArrowRight size={17} /></Button>
            </form>
            <aside className="investigation-guide">
              <ul>
                <li><h3>{t('workspace.traceTitle')}</h3><p>{t('workspace.traceDescription')}</p></li>
                <li><h3>{t('findVehicle.replayRoute')}</h3><p>{t('workspace.replayDescription')}</p></li>
                <li><h3>{t('findVehicle.watchForVehicle')}</h3><p>{t('workspace.watchDescription')}</p></li>
              </ul>
            </aside>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <TopBar title={t('findVehicle.title')} subtitle={t('findVehicle.searchesLast24h')} />
      <form onSubmit={(e) => { e.preventDefault(); handleSearch() }} className="page-toolbar">
        <button
          type="button"
          onClick={() => setSearchParams({})}
          className="min-h-11 text-sm text-text-secondary hover:text-text-primary"
        >
          {t('findVehicle.newSearch')}
        </button>
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <Input
            aria-label={t('workspace.plate')}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            className="plate-mono w-full max-w-xs"
          />
          <Button type="submit" size="sm" variant="secondary">
            {t('findVehicle.search')}
          </Button>
        </div>
      </form>

      {loading && <p className="p-6 text-sm text-text-tertiary">{t('findVehicle.searching')}</p>}
      {error && <div role="alert" className="page-body"><p className="mb-3 text-sev-critical">{error}</p><Button variant="secondary" onClick={() => setRefreshKey((k) => k + 1)}>{t('common.retry')}</Button></div>}

      {route && route.total_sightings === 0 && !loading && (
        <div className="flex flex-1 items-center justify-center p-8">
          <ArmBoloPanel plate={route.plate_normalised} onArmed={() => setRefreshKey((k) => k + 1)} />
        </div>
      )}

      {route && route.total_sightings > 0 && (
        <>
          <div className="page-toolbar justify-between">
            <div>
              <p className="plate-mono text-xl font-semibold text-text-primary">{route.plate_normalised}</p>
              <p className="text-sm text-text-secondary">
                {t('findVehicle.summary', {
                  sightings: t('findVehicle.sighting', { count: route.total_sightings }),
                  cameras: t('findVehicle.camera', { count: new Set(route.points.map((p) => p.camera_id)).size }),
                })}{' '}
                ·{' '}
                {route.first_seen_at && formatTime(route.first_seen_at)} →{' '}
                {route.last_seen_at && formatTime(route.last_seen_at)}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="secondary"
                onClick={replaying ? stopReplay : playReplay}
                disabled={locatedPoints.length < 2}
                title={
                  locatedPoints.length < 2
                    ? t('findVehicle.replayUnavailable', {
                        located: locatedPoints.length,
                        total: route.points.length,
                      })
                    : undefined
                }
              >
                {replaying ? <Pause size={14} /> : <Play size={14} />}
                {replaying ? t('findVehicle.stop') : t('findVehicle.replayRoute')}
              </Button>
              <ExportReportButton plate={route.plate_normalised} />
            </div>
          </div>
          {unmappedCount > 0 && (
            // Say why the map shows fewer pins than the timeline does. Some
            // government cameras have no resolvable location (their catalogue
            // entry carries only a name), and silently dropping them from the
            // map makes the platform look like it lost a sighting.
            <p className="-mt-2 mb-4 text-sm text-text-tertiary">
              {t('findVehicle.unmappedSightings', {
                count: unmappedCount,
                total: route.points.length,
              })}
            </p>
          )}
          <div className="investigation-results">
            <div className="investigation-map">
              <MapView
                markers={markers}
                routeSegments={routeSegments}
                vehiclePosition={vehiclePosition}
                fitToMarkers
                className="absolute inset-0"
              />
            </div>
            <aside className="investigation-timeline">
              <h2 className="mb-6 text-base font-semibold text-text-primary">
                {t('findVehicle.timeline')}
              </h2>
              <ol className="flex flex-col gap-3">
                {route.points.map((point, i) => (
                  <li
                    key={`${point.camera_id}-${i}`}
                    className={cn(
                      'flex gap-3 rounded-md transition-colors duration-fast',
                      activeHopIndex === i && '-mx-2 bg-accent/10 px-2 py-1',
                    )}
                  >
                    <div className="flex flex-col items-center pt-1">
                      <span
                        className={
                          point.confirmed
                            ? 'h-2.5 w-2.5 rounded-full bg-accent'
                            : 'h-2.5 w-2.5 rounded-full border-2 border-accent bg-transparent'
                        }
                      />
                      {i < route.points.length - 1 && <span className="mt-1 h-full w-px flex-1 bg-border-subtle" />}
                    </div>
                    <div className="min-w-0 flex-1 pb-2">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-medium text-text-primary">{formatTime(point.observed_at)}</span>
                        <ConfidenceBar point={point} />
                      </div>
                      <p className="truncate text-sm text-text-secondary">{point.camera_name}</p>
                      {point.match_rung === 'ambiguity_class' && (
                        <SeverityBadge severity="medium" label={t('findVehicle.probableMatch')} className="mt-1" />
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            </aside>
          </div>
        </>
      )}
    </div>
  )
}
