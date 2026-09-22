import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Download, Pause, Play } from 'lucide-react'
import { detectionsApi, watchlistApi } from '../lib/api'
import { ApiError } from '../lib/http'
import { MapView, type MapMarker } from '../components/MapView'
import { Card } from '../components/ui/Card'
import { Input } from '../components/ui/Input'
import { Button } from '../components/ui/Button'
import { SeverityBadge } from '../components/ui/SeverityBadge'
import { cn } from '../lib/cn'
import type { RoutePoint, VehicleRoute } from '../lib/types'

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function ConfidenceBar({ point }: { point: RoutePoint }) {
  const pct = Math.round(point.plate_confidence * 100)
  const tooltip =
    point.match_rung === 'exact'
      ? 'Read clearly at this camera'
      : 'Matched via OCR-ambiguity class — one or more characters were uncertain'
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
      setError(err instanceof ApiError ? String(err.detail) : 'Could not arm the watchlist entry.')
    } finally {
      setBusy(false)
    }
  }

  if (armed) {
    return (
      <Card className="p-6 text-center">
        <p className="text-sm font-medium text-ok">Watch armed for {plate}</p>
        <p className="mt-1 text-sm text-text-secondary">
          {armed.retro_sightings_found > 0
            ? `Found ${armed.retro_sightings_found} past sighting${armed.retro_sightings_found === 1 ? '' : 's'} already on file — check Alerts.`
            : 'No past sightings — you will be alerted the moment this plate is seen.'}
        </p>
      </Card>
    )
  }

  return (
    <Card className="flex flex-col items-center gap-3 p-8 text-center">
      <p className="plate-mono text-2xl font-semibold text-text-primary">{plate}</p>
      <p className="max-w-sm text-sm text-text-secondary">
        No sightings for this plate in the last 24 hours. Watch for it — every camera will check
        future reads against it, and every past detection on file is checked right now too.
      </p>
      <Button onClick={arm} disabled={busy}>
        {busy ? 'Arming…' : 'Watch for this vehicle'}
      </Button>
      {error && <p className="text-xs text-sev-critical">{error}</p>}
    </Card>
  )
}

function ExportReportButton({ plate }: { plate: string }) {
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
      setError('Export failed. Try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <Button size="sm" variant="secondary" onClick={download} disabled={busy}>
        <Download size={14} />
        {busy ? 'Preparing…' : 'Export report'}
      </Button>
      {error && <p className="text-xs text-sev-critical">{error}</p>}
    </div>
  )
}

export function FindVehicle() {
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
    if (!plateParam) {
      setRoute(null)
      return
    }
    setLoading(true)
    setError(null)
    detectionsApi
      .vehicleRoute(plateParam)
      .then(setRoute)
      .catch((err) => setError(err instanceof ApiError ? String(err.detail) : 'Search failed.'))
      .finally(() => setLoading(false))
  }, [plateParam, refreshKey])

  // Cancel any in-flight replay if the operator starts a new search.
  useEffect(() => {
    replayTokenRef.current += 1
    setReplaying(false)
    setActiveHopIndex(null)
    setVehiclePosition(null)
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
    color: 'oklch(0.68 0.16 245)',
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
      <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-6 p-8">
        <h1 className="text-2xl font-semibold text-text-primary">Find a vehicle</h1>
        <div className="flex w-full max-w-lg gap-2">
          <Input
            autoFocus
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="GJ 01 AB 1234"
            className="plate-mono flex-1 text-center text-lg"
          />
          <Button onClick={handleSearch}>Search</Button>
        </div>
        <p className="text-sm text-text-tertiary">Searches the last 24 hours across every camera.</p>
      </div>
    )
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="flex items-center gap-4 border-b border-border-subtle bg-bg-raised px-6 py-4">
        <button
          onClick={() => setSearchParams({})}
          className="text-sm text-text-tertiary hover:text-text-primary"
        >
          ← New search
        </button>
        <div className="flex flex-1 items-center gap-2">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            className="plate-mono max-w-xs"
          />
          <Button size="sm" variant="secondary" onClick={handleSearch}>
            Search
          </Button>
        </div>
      </header>

      {loading && <p className="p-6 text-sm text-text-tertiary">Searching…</p>}
      {error && <p className="p-6 text-sm text-sev-critical">{error}</p>}

      {route && route.total_sightings === 0 && !loading && (
        <div className="flex flex-1 items-center justify-center p-8">
          <ArmBoloPanel plate={route.plate_normalised} onArmed={() => setRefreshKey((k) => k + 1)} />
        </div>
      )}

      {route && route.total_sightings > 0 && (
        <>
          <div className="flex items-center justify-between gap-4 border-b border-border-subtle bg-bg-raised px-6 py-3">
            <div>
              <p className="plate-mono text-xl font-semibold text-text-primary">{route.plate_normalised}</p>
              <p className="text-sm text-text-secondary">
                {route.total_sightings} sighting{route.total_sightings === 1 ? '' : 's'} across{' '}
                {new Set(route.points.map((p) => p.camera_id)).size} camera
                {new Set(route.points.map((p) => p.camera_id)).size === 1 ? '' : 's'} ·{' '}
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
              >
                {replaying ? <Pause size={14} /> : <Play size={14} />}
                {replaying ? 'Stop' : 'Replay route'}
              </Button>
              <ExportReportButton plate={route.plate_normalised} />
            </div>
          </div>
          <div className="relative flex min-h-0 flex-1">
            <div className="relative flex-[1.4]">
              <MapView
                markers={markers}
                routeSegments={routeSegments}
                vehiclePosition={vehiclePosition}
                className="absolute inset-0"
              />
            </div>
            <aside className="w-[360px] flex-shrink-0 overflow-y-auto border-l border-border-subtle bg-bg-raised p-4">
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-text-tertiary">
                Timeline
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
                        <SeverityBadge severity="medium" label="Probable match" className="mt-1" />
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
