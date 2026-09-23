import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ArrowRight, Camera, Download, MapPin, Pause, Play, Search, ShieldCheck, ScanLine } from 'lucide-react'
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
import './investigation-workspace.css'

function requestMessage(error: unknown, fallback: string): string {
  if (!(error instanceof ApiError)) return fallback
  if (typeof error.detail === 'string') return error.detail
  if (error.detail && typeof error.detail === 'object' && 'detail' in error.detail && typeof error.detail.detail === 'string') return error.detail.detail
  return fallback
}

function SightingEvidence({ point }: { point: RoutePoint }) {
  const { t } = useTranslation()
  const [imageFailed, setImageFailed] = useState(false)
  return (
    <section aria-label={t('investigation:evidence')} className="iw-evidence">
      <div className="iw-section-heading"><h2>{t('investigation:evidence')}</h2><Camera size={17} /></div>
      <div className="iw-snapshot">
        {point.snapshot_uri && !imageFailed
          ? <img src={point.snapshot_uri} alt={t('investigation:snapshotAlt', { camera: point.camera_name })} onError={() => setImageFailed(true)} />
          : <><ScanLine size={32} strokeWidth={1.3} /><p>{t(imageFailed ? 'investigation:snapshotFailed' : 'investigation:noSnapshot')}</p></>}
      </div>
      <div className="iw-evidence-copy">
        <h3>{point.camera_name}</h3>
        <p>{formatTime(point.observed_at)}</p>
        <dl className="iw-facts">
          <div><dt>{t('investigation:observedPlate')}</dt><dd className="plate-mono">{point.plate_text}</dd></div>
          <div><dt>{t('investigation:match')}</dt><dd>{t(point.match_rung === 'exact' ? 'findVehicle.exactMatch' : 'findVehicle.probableMatch')}</dd></div>
          <div><dt>{t('investigation:confidence')}</dt><dd>{Math.round(point.plate_confidence * 100)}%</dd></div>
          <div><dt>{t('investigation:location')}</dt><dd>{point.location ? `${point.location.lat.toFixed(5)}, ${point.location.lon.toFixed(5)}` : t('investigation:noLocation')}</dd></div>
        </dl>
        {point.match_rung !== 'exact' && <p className="iw-context-note">{t('findVehicle.matchedByAmbiguity')}</p>}
      </div>
    </section>
  )
}

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
      setError(requestMessage(err, t('findVehicle.armError')))
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
      .catch((err) => { if (!cancelled) setError(requestMessage(err, t('findVehicle.searchFailed'))) })
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
    color: '#2456d6',
    label: `${p.index + 1}. ${p.camera_name} · ${formatTime(p.observed_at)}`,
    number: p.index + 1,
    pulse: activeHopIndex === p.index,
    onClick: () => { stopReplay(); setActiveHopIndex(p.index) },
  }))

  const routeSegments = locatedPoints.slice(0, -1).map((p, i) => ({
    from: [p.location.lon, p.location.lat] as [number, number],
    to: [locatedPoints[i + 1].location.lon, locatedPoints[i + 1].location.lat] as [number, number],
    confirmed: locatedPoints[i + 1].match_rung !== 'ambiguity_class',
  }))

  return (
    <div className="investigation-workspace">
      <TopBar title={t('findVehicle.title')} subtitle={t('findVehicle.searchesLast24h')} />
      <form role="search" aria-label={t('investigation:queryConsole')} onSubmit={(e) => { e.preventDefault(); handleSearch() }} className="iw-query-toolbar">
        <div className="iw-query-field">
          <label htmlFor="investigation-plate">{t('workspace.plate')}</label>
          <div><Search size={18} aria-hidden="true" /><Input id="investigation-plate" required value={input} onChange={(e) => setInput(e.target.value)} placeholder={t('findVehicle.platePlaceholder')} className="plate-mono" /></div>
        </div>
        <Button type="submit" disabled={!input.trim() || loading}>{t('findVehicle.search')}<ArrowRight size={16} /></Button>
        <span className="iw-query-scope">{t('findVehicle.searchesLast24h')}</span>
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
          <ArmBoloPanel plate={route.plate_normalised} onArmed={() => setRefreshKey((k) => k + 1)} />
        </div>
      )}

      {route && route.total_sightings > 0 && (
        <section aria-label={t('investigation:workbench')} className="iw-workbench">
          <div className="iw-result-header">
            <div>
              <p className="plate-mono text-xl font-semibold text-text-primary">{route.plate_normalised}</p>
              <p className="text-sm text-text-secondary">{t('investigation:loadedSightings', { count: route.points.length })} · {t('findVehicle.camera', { count: new Set(route.points.map((p) => p.camera_id)).size })}</p>
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
              <ExportReportButton plate={route.plate_normalised} />
            </div>
          </div>
          <dl className="iw-route-summary">
            <div><dt>{t('investigation:firstSeen')}</dt><dd>{route.first_seen_at ? formatTime(route.first_seen_at) : t('common.notAvailable')}</dd></div>
            <div><dt>{t('investigation:lastSeen')}</dt><dd>{route.last_seen_at ? formatTime(route.last_seen_at) : t('common.notAvailable')}</dd></div>
            <div><dt>{t('investigation:mappedSightings')}</dt><dd>{locatedPoints.length} / {route.points.length}</dd></div>
          </dl>
          <div className="iw-result-grid">
            <section className="iw-map-section" aria-label={t('investigation:movementMap')}>
              <div className="iw-section-heading"><h2>{t('investigation:movementMap')}</h2><span>{t('investigation:mapHint')}</span></div>
              <div className="iw-map">
              <MapView
                markers={markers}
                routeSegments={routeSegments}
                vehiclePosition={vehiclePosition}
                fitToMarkers
                className="absolute inset-0"
              />
              {locatedPoints.length === 0 && <p className="iw-map-empty">{t('investigation:noMappedSightings')}</p>}
              </div>
              <footer className="iw-map-footer">
                <span><i />{t('findVehicle.exactMatch')}</span><span><i className="is-probable" />{t('findVehicle.probableMatch')}</span>
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
                    <button type="button" aria-pressed={(activeHopIndex ?? 0) === i} className={cn('iw-timeline-row', (activeHopIndex ?? 0) === i && 'is-selected')} onClick={() => { stopReplay(); setActiveHopIndex(i) }}>
                    <span className="iw-hop">{i + 1}</span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="text-sm font-medium text-text-primary">{formatTime(point.observed_at)}</span>
                        <ConfidenceBar point={point} />
                      </div>
                      <p className="iw-camera-name">{point.camera_name}</p>
                      {point.match_rung === 'ambiguity_class' && (
                        <SeverityBadge severity="medium" label={t('findVehicle.probableMatch')} className="mt-1" />
                      )}
                    </div>
                    </button>
                  </li>
                ))}
              </ol>
            </aside>
            {route.points[activeHopIndex ?? 0] && <SightingEvidence key={`${plateParam}-${activeHopIndex ?? 0}`} point={route.points[activeHopIndex ?? 0]} />}
          </div>
        </section>
      )}
    </div>
  )
}
