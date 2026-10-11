import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ArrowRight, Camera, Download, MapPin, Pause, Play, Search, ShieldCheck, ScanLine } from 'lucide-react'
import type { TFunction } from 'i18next'
import { useTranslation } from 'react-i18next'
import { detectionsApi, watchlistApi } from '../lib/api'
import { ApiError } from '../lib/http'
import { MapView, ROUTE_END_COLOUR, ROUTE_START_COLOUR, type MapMarker, type RouteSegment } from '../components/MapView'
import { Card } from '../components/ui/Card'
import { Input } from '../components/ui/Input'
import { Button } from '../components/ui/Button'
import { SeverityBadge } from '../components/ui/SeverityBadge'
import { cn } from '../lib/cn'
import type { RoutePoint, VehicleRoute } from '../lib/types'
import { TopBar } from '../components/layout/TopBar'
import i18n from '../lib/i18n'
import './investigation-workspace.css'
import { formatIst } from '../lib/time'

function requestMessage(error: unknown, fallback: string): string {
  if (!(error instanceof ApiError)) return fallback
  if (typeof error.detail === 'string') return error.detail
  if (error.detail && typeof error.detail === 'object' && 'detail' in error.detail && typeof error.detail.detail === 'string') return error.detail.detail
  return fallback
}

function SightingEvidence({ point }: { point: RoutePoint }) {
  const { t } = useTranslation()
  const [imageFailed, setImageFailed] = useState(false)
  const [snapshotUrl, setSnapshotUrl] = useState<string | null>(null)

  // `snapshot_uri` is an internal `snapshot://<ulid>` reference, not a URL a
  // browser can load — pointing <img src> at it produced
  // ERR_UNKNOWN_URL_SCHEME and an empty evidence panel. The real frame comes
  // from the bearer-authed snapshot endpoint, which <img> cannot call
  // directly, so it is fetched as a Blob and shown via an object URL.
  useEffect(() => {
    if (!point.event_id || !point.snapshot_uri) {
      setSnapshotUrl(null)
      return
    }
    let objectUrl: string | null = null
    let cancelled = false
    setImageFailed(false)
    detectionsApi
      .snapshotBlob(point.event_id)
      .then(({ blob }) => {
        if (cancelled) return
        objectUrl = URL.createObjectURL(blob)
        setSnapshotUrl(objectUrl)
      })
      .catch(() => !cancelled && setImageFailed(true))
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [point.event_id, point.snapshot_uri])

  return (
    <section aria-label={t('investigation:evidence')} className="iw-evidence">
      <div className="iw-section-heading"><h2>{t('investigation:evidence')}</h2><Camera size={17} /></div>
      <div className="iw-snapshot">
        {snapshotUrl && !imageFailed
          ? <img src={snapshotUrl} alt={t('investigation:snapshotAlt', { camera: point.camera_name })} onError={() => setImageFailed(true)} />
          : <><ScanLine size={32} strokeWidth={1.3} /><p>{t(imageFailed ? 'investigation:snapshotFailed' : 'investigation:noSnapshot')}</p></>}
      </div>
      <div className="iw-evidence-copy">
        <h3>{point.camera_name}</h3>
        <p>{sightingTime(point, t)}</p>
        <dl className="iw-facts">
          <div><dt>{t('investigation:observedPlate')}</dt><dd className="plate-mono">{point.plate_text}</dd></div>
          <div><dt>{t('investigation:match')}</dt><dd>{t(point.match_rung === 'exact' ? 'findVehicle.exactMatch' : 'findVehicle.probableMatch')}</dd></div>
          <div><dt>{t('investigation:confidence')}</dt><dd>{Math.round(point.plate_confidence * 100)}%</dd></div>
          <div><dt>{t('investigation:location')}</dt><dd>{point.location ? `${point.location.lat.toFixed(5)}, ${point.location.lon.toFixed(5)}` : t('investigation:noLocation')}</dd></div>
        </dl>
        {point.match_rung !== 'exact' && <p className="iw-context-note">{matchNote(point, t)}</p>}
        {point.infeasible && <p className="iw-context-note text-sev-critical">{infeasibleNote(point, t)}</p>}
      </div>
    </section>
  )
}

/** Why a non-exact hop is on the route. A one-character match may be a
 * different vehicle, so it says so and names the plate actually read. */
function matchNote(point: RoutePoint, t: TFunction): string {
  if (point.match_rung === 'edit_distance') return t('readiness:matchedByEditDistance', { plate: point.plate_text })
  if (point.match_rung === 'partial_attribute') return t('readiness:matchedByAttributes', { plate: point.plate_text })
  return t('findVehicle.matchedByAmbiguity')
}

function infeasibleNote(point: RoutePoint, t: TFunction): string {
  return point.implied_speed_kmh != null
    ? t('readiness:infeasibleAtSpeed', { speed: Math.round(point.implied_speed_kmh) })
    : t('readiness:infeasibleClock')
}

/** Hop numbers for a shared pin: "3", "3·4", "1–8", or "2+" when many and scattered. */
function hopLabel(hops: number[]): string {
  const numbers = hops.map((h) => h + 1)
  if (numbers.length === 1) return String(numbers[0])
  const consecutive = numbers.every((n, i) => i === 0 || n === numbers[i - 1] + 1)
  if (consecutive && numbers.length > 2) return `${numbers[0]}–${numbers[numbers.length - 1]}`
  if (numbers.length <= 3) return numbers.join('·')
  return `${numbers[0]}+`
}

/** A colour `t` of the way from hex `a` to hex `b`. */
function mixColour(a: string, b: string, t: number): string {
  const channel = (hex: string, i: number) => parseInt(hex.slice(1 + i * 2, 3 + i * 2), 16)
  const mixed = [0, 1, 2].map((i) => Math.round(channel(a, i) + (channel(b, i) - channel(a, i)) * t))
  return `#${mixed.map((v) => v.toString(16).padStart(2, '0')).join('')}`
}

function formatTime(iso: string): string {
  return formatIst(iso, i18n.language)
}

/** The camera's burned-in clock on the sighting's evidence frame — the only
 * time a sighting is shown with. Nothing stands in for it when unreadable. */
function sightingTime(point: RoutePoint, t: TFunction): string {
  return point.camera_time ? formatTime(point.camera_time) : t('common.timeUnknown')
}

function ConfidenceBar({ point }: { point: RoutePoint }) {
  const { t } = useTranslation()
  const pct = Math.round(point.plate_confidence * 100)
  const tooltip = point.match_rung === 'exact' ? t('findVehicle.readClearly') : matchNote(point, t)
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

/** Search windows offered to the operator; the finale spans two days, so a
 * vehicle seen yesterday must still be reachable. Mirrors the API's cap. */
const SEARCH_WINDOWS = [24, 48, 168] as const
type SearchWindow = (typeof SEARCH_WINDOWS)[number]

function parseWindow(value: string | null): SearchWindow {
  const hours = Number(value)
  return (SEARCH_WINDOWS as readonly number[]).includes(hours) ? (hours as SearchWindow) : 24
}

function ArmBoloPanel({ plate, windowHours, onArmed }: { plate: string; windowHours: SearchWindow; onArmed: () => void }) {
  const { t } = useTranslation()
  const [busy, setBusy] = useState(false)
  const [armed, setArmed] = useState<{ retro_alerts_created: number; retro_sightings_found: number; already_armed?: boolean } | null>(
    null,
  )
  const [error, setError] = useState<string | null>(null)

  async function arm() {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      const result = await watchlistApi.bolo({ plate, entry_type: 'bolo', priority: 'high' })
      setArmed(result)
      onArmed()
    } catch (err) {
      setError(requestMessage(err, t('findVehicle.armError')))
    } finally {
      setBusy(false)
    }
  }

  if (armed) {
    return (
      <Card className="p-6 text-center">
        <p className="text-sm font-medium text-ok">{t(armed.already_armed ? 'findVehicle.watchAlreadyArmed' : 'findVehicle.watchArmed', { plate })}</p>
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
      <p className="max-w-sm text-sm text-text-secondary">
        {windowHours === 24
          ? t('findVehicle.noSightingsIn24h')
          : t('readiness:noSightingsInWindow', { window: t(`readiness:window${windowHours}`) })}
      </p>
      <Button onClick={arm} disabled={busy}>
        {busy ? t('findVehicle.arming') : t('findVehicle.watchForVehicle')}
      </Button>
      {error && <p className="text-xs text-sev-critical">{error}</p>}
    </Card>
  )
}

function ExportReportButton({ plate, windowHours }: { plate: string; windowHours: SearchWindow }) {
  const { t } = useTranslation()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function download() {
    setBusy(true)
    setError(null)
    try {
      const { blob, filename } = await detectionsApi.movementReport(plate, windowHours)
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
  const windowHours = parseWindow(searchParams.get('hours'))
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

  // A new search clears the result; a refresh of the same search (after
  // arming a watch) keeps it on screen. Clearing it on refresh unmounted the
  // "watch armed" confirmation and brought the button straight back — which
  // in a manual test was clicked six more times, arming the plate seven times.
  const searchKey = `${plateParam}|${windowHours}`
  const lastSearchKeyRef = useRef(searchKey)

  useEffect(() => {
    let cancelled = false
    setInput(plateParam)
    if (lastSearchKeyRef.current !== searchKey) {
      lastSearchKeyRef.current = searchKey
      setRoute(null)
    }
    setError(null)
    if (!plateParam) {
      setLoading(false)
      return
    }
    if (refreshKey === 0 || route === null) setLoading(true)
    detectionsApi
      .vehicleRoute(plateParam, windowHours)
      .then((result) => { if (!cancelled) setRoute(result) })
      .catch((err) => { if (!cancelled) setError(requestMessage(err, t('findVehicle.searchFailed'))) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plateParam, windowHours, refreshKey, t])

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
    setSearchParams(searchFor(trimmed, windowHours))
  }

  function searchFor(plate: string, hours: SearchWindow): Record<string, string> {
    return hours === 24 ? { plate } : { plate, hours: String(hours) }
  }

  function changeWindow(hours: SearchWindow) {
    const plate = plateParam || input.trim()
    setSearchParams(plate ? searchFor(plate, hours) : hours === 24 ? {} : { hours: String(hours) })
  }

  const windowLabel = t(`readiness:window${windowHours}`)

  // Memoised: replay re-renders this component every animation frame, and a
  // fresh array each time made the map redraw its pins and re-fit its view.
  const locatedPoints = useMemo(
    () =>
      route?.points
        .map((p, i) => ({ ...p, index: i }))
        .filter((p): p is typeof p & { location: NonNullable<RoutePoint['location']> } => p.location !== null) ?? [],
    [route],
  )

  const unmappedCount = (route?.points.length ?? 0) - locatedPoints.length

  // Timed sightings first (the route), then those whose camera clock was
  // unreadable. One selection index spans both; only timed ones are mapped.
  const allSightings = route ? [...route.points, ...route.untimed] : []
  const selectedIndex = activeHopIndex ?? 0

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

  // One pin per camera position: repeat sightings at a camera share it
  // ("3·4", "1–8") instead of stacking unreadably on the same spot. Pins are
  // coloured along the route, earliest to latest, like the line between them.
  const stops = useMemo(() => {
    const byPosition = new Map<string, typeof locatedPoints>()
    for (const point of locatedPoints) {
      const key = `${point.location.lat.toFixed(5)},${point.location.lon.toFixed(5)}`
      byPosition.set(key, [...(byPosition.get(key) ?? []), point])
    }
    const last = locatedPoints.length - 1
    return [...byPosition.values()].map((points) => ({
      points,
      hops: points.map((p) => p.index),
      order: last > 0 ? locatedPoints.indexOf(points[points.length - 1]) / last : 1,
      isStart: points.includes(locatedPoints[0]),
      isLatest: points.includes(locatedPoints[last]),
    }))
  }, [locatedPoints])

  const markers: MapMarker[] = useMemo(
    () =>
      stops.map((stop) => {
        const head = stop.points[0]
        const active = activeHopIndex ?? 0
        return {
          id: `stop-${head.location.lat}-${head.location.lon}`,
          lat: head.location.lat,
          lon: head.location.lon,
          color: mixColour(ROUTE_START_COLOUR, ROUTE_END_COLOUR, stop.order),
          text: hopLabel(stop.hops),
          size: 24,
          chip: stop.isLatest ? t('investigation:mapLatest') : stop.isStart ? t('investigation:mapStart') : undefined,
          label: `${head.camera_name} — ${stop.points.map((p) => `${p.index + 1}: ${sightingTime(p, t)}`).join(', ')}`,
          pulse: stop.hops.includes(active),
          onClick: () => {
            stopReplay()
            // Clicking a shared pin again steps through its sightings.
            const at = stop.hops.indexOf(active)
            setActiveHopIndex(stop.hops[at < 0 ? 0 : (at + 1) % stop.hops.length])
          },
        }
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [stops, activeHopIndex, t],
  )

  const routeSegments: RouteSegment[] = useMemo(() => {
    const last = locatedPoints.length - 1
    return locatedPoints.slice(0, -1).flatMap((p, i) => {
      const next = locatedPoints[i + 1]
      // Two sightings at one camera have no distance to draw or direction to show.
      if (p.location.lat === next.location.lat && p.location.lon === next.location.lon) return []
      return [{
        from: [p.location.lon, p.location.lat] as [number, number],
        to: [next.location.lon, next.location.lat] as [number, number],
        confirmed: next.match_rung === 'exact',
        order: (i + 1) / last,
      }]
    })
  }, [locatedPoints])

  return (
    <div className="investigation-workspace">
      <TopBar title={t('findVehicle.title')} subtitle={windowHours === 24 ? t('findVehicle.searchesLast24h') : t('readiness:searchesWindow', { window: windowLabel })} />
      <form role="search" aria-label={t('investigation:queryConsole')} onSubmit={(e) => { e.preventDefault(); handleSearch() }} className="iw-query-toolbar">
        <div className="iw-query-field">
          <label htmlFor="investigation-plate">{t('workspace.plate')}</label>
          <div><Search size={18} aria-hidden="true" /><Input id="investigation-plate" required value={input} onChange={(e) => setInput(e.target.value)} placeholder={t('findVehicle.platePlaceholder')} className="plate-mono" /></div>
        </div>
        <Button type="submit" disabled={!input.trim() || loading}>{t('findVehicle.search')}<ArrowRight size={16} /></Button>
        <label className="iw-query-scope flex items-center gap-2">
          <span>{t('readiness:searchWindow')}</span>
          <select
            aria-label={t('readiness:searchWindow')}
            value={windowHours}
            onChange={(e) => changeWindow(parseWindow(e.target.value))}
            className="h-10 rounded-md border border-border-strong bg-bg-inset px-2 text-sm text-text-primary"
          >
            {SEARCH_WINDOWS.map((hours) => <option key={hours} value={hours}>{t(`readiness:window${hours}`)}</option>)}
          </select>
        </label>
        {plateParam && <Button type="button" variant="ghost" onClick={() => setSearchParams({})}>{t('findVehicle.newSearch')}</Button>}
      </form>

      {!plateParam && <div className="iw-start">
        <section className="iw-start-intro">
          <div className="iw-start-symbol"><Search size={36} strokeWidth={1.4} /></div>
          <h2>{t('investigation:startTitle')}</h2>
          <p>{t('investigation:startDescription')}</p>
          <p className="iw-context-note">{t('investigation:plateHelp')}</p>
          <Button variant="secondary" onClick={() => document.getElementById('investigation-plate')?.focus()}>{t('workspace.startWithPlate')}<ArrowRight size={16} /></Button>
        </section>
        <aside className="iw-start-guide" aria-label={t('investigation:workflow')}>
          <h2>{t('investigation:workflow')}</h2>
          <div><MapPin size={21} /><section><h3>{t('workspace.traceTitle')}</h3><p>{t('workspace.traceDescription')}</p></section></div>
          <div><Camera size={21} /><section><h3>{t('investigation:reviewEvidence')}</h3><p>{t('investigation:reviewDescription')}</p></section></div>
          <div><ShieldCheck size={21} /><section><h3>{t('findVehicle.watchForVehicle')}</h3><p>{t('workspace.watchDescription')}</p></section></div>
        </aside>
      </div>}
      {loading && <div className="iw-loading" role="status"><p>{t('findVehicle.searching')}</p><div /><div /><div /></div>}
      {error && <div role="alert" className="page-body"><p className="mb-3 text-sev-critical">{error}</p><Button variant="secondary" onClick={() => setRefreshKey((k) => k + 1)}>{t('common.retry')}</Button></div>}

      {route && route.total_sightings === 0 && !loading && (
        <div className="flex flex-1 items-center justify-center p-8">
          <ArmBoloPanel plate={route.plate_normalised} windowHours={windowHours} onArmed={() => setRefreshKey((k) => k + 1)} />
        </div>
      )}

      {route && route.total_sightings > 0 && (
        <section aria-label={t('investigation:workbench')} className="iw-workbench">
          <div className="iw-result-header">
            <div>
              <p className="plate-mono text-xl font-semibold text-text-primary">{route.plate_normalised}</p>
              <p className="text-sm text-text-secondary">{t('investigation:loadedSightings', { count: route.total_sightings })} · {t('findVehicle.camera', { count: new Set(allSightings.map((p) => p.camera_id)).size })}</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
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
              <ExportReportButton plate={route.plate_normalised} windowHours={windowHours} />
            </div>
          </div>
          <dl className="iw-route-summary">
            <div><dt>{t('investigation:firstSeen')}</dt><dd>{route.first_seen_at ? formatTime(route.first_seen_at) : t('common.timeUnknownShort')}</dd></div>
            <div><dt>{t('investigation:lastSeen')}</dt><dd>{route.last_seen_at ? formatTime(route.last_seen_at) : t('common.timeUnknownShort')}</dd></div>
            <div><dt>{t('investigation:mappedSightings')}</dt><dd>{locatedPoints.length} / {route.points.length}</dd></div>
          </dl>
          <div className="iw-result-grid">
            <section className="iw-map-section" aria-label={t('investigation:movementMap')}>
              <div className="iw-section-heading"><h2>{t('investigation:movementMap')}</h2><span>{t('investigation:mapHint')}</span></div>
              <div className="iw-map">
              <MapView
                markers={markers}
                routeSegments={routeSegments}
                basemap="muted"
                vehiclePosition={vehiclePosition}
                fitToMarkers
                className="absolute inset-0"
              />
              {locatedPoints.length === 0 && <p className="iw-map-empty">{t(route.points.length === 0 ? 'investigation:noTimedSightings' : 'investigation:noMappedSightings')}</p>}
              </div>
              <footer className="iw-map-footer">
                <span><i className="is-gradient" />{t('investigation:routeLegend')}</span><span><i />{t('findVehicle.exactMatch')}</span><span><i className="is-probable" />{t('findVehicle.probableMatch')}</span>
                <p>{t('investigation:routeStraightLines')}</p>
                {unmappedCount > 0 && <p>{t('findVehicle.unmappedSightings', { count: unmappedCount, total: route.points.length })}</p>}
              </footer>
            </section>
            <aside className="iw-timeline">
              <div className="iw-section-heading"><h2>
                {t('findVehicle.timeline')}
              </h2><span>{t('investigation:selectSighting')}</span></div>
              <ol>
                {route.points.map((point, i) => (
                  <li
                    key={`${point.camera_id}-${i}`}
                  >
                    <button type="button" aria-pressed={selectedIndex === i} className={cn('iw-timeline-row', selectedIndex === i && 'is-selected')} onClick={() => { stopReplay(); setActiveHopIndex(i) }}>
                    <span className="iw-hop">{i + 1}</span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="text-sm font-medium text-text-primary">{sightingTime(point, t)}</span>
                        <ConfidenceBar point={point} />
                      </div>
                      <p className="iw-camera-name">{point.camera_name}</p>
                      {point.match_rung !== 'exact' && (
                        <SeverityBadge severity="medium" label={t('findVehicle.probableMatch')} className="mt-1" />
                      )}
                      {point.infeasible && (
                        <SeverityBadge severity="critical" label={t('readiness:impossibleTravel')} className="mt-1" />
                      )}
                    </div>
                    </button>
                  </li>
                ))}
              </ol>
              {route.untimed.length > 0 && (
                <section aria-label={t('investigation:untimedTitle')} className="mt-4">
                  <div className="iw-section-heading"><h2>{t('investigation:untimedTitle')}</h2></div>
                  <p className="iw-context-note">{t('investigation:untimedHint')}</p>
                  <ol>
                    {route.untimed.map((point, j) => {
                      const index = route.points.length + j
                      return (
                        <li key={`untimed-${point.camera_id}-${j}`}>
                          <button type="button" aria-pressed={selectedIndex === index} className={cn('iw-timeline-row', selectedIndex === index && 'is-selected')} onClick={() => { stopReplay(); setActiveHopIndex(index) }}>
                            <span className="iw-hop">U{j + 1}</span>
                            <div className="min-w-0 flex-1">
                              <div className="flex flex-wrap items-center justify-between gap-2">
                                <span className="text-sm font-medium text-text-secondary">{t('common.timeUnknown')}</span>
                                <ConfidenceBar point={point} />
                              </div>
                              <p className="iw-camera-name">{point.camera_name}</p>
                              {point.match_rung !== 'exact' && (
                                <SeverityBadge severity="medium" label={t('findVehicle.probableMatch')} className="mt-1" />
                              )}
                            </div>
                          </button>
                        </li>
                      )
                    })}
                  </ol>
                </section>
              )}
            </aside>
            {allSightings[selectedIndex] && <SightingEvidence key={`${plateParam}-${selectedIndex}`} point={allSightings[selectedIndex]} />}
          </div>
        </section>
      )}
    </div>
  )
}
