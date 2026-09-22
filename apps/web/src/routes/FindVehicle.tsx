import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Download } from 'lucide-react'
import { detectionsApi, watchlistApi } from '../lib/api'
import { ApiError } from '../lib/http'
import { MapView, type MapMarker } from '../components/MapView'
import { Card } from '../components/ui/Card'
import { Input } from '../components/ui/Input'
import { Button } from '../components/ui/Button'
import { SeverityBadge } from '../components/ui/SeverityBadge'
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

  function handleSearch() {
    const trimmed = input.trim()
    if (!trimmed) return
    setSearchParams({ plate: trimmed })
  }

  const markers: MapMarker[] =
    route?.points
      .filter((p): p is RoutePoint & { location: NonNullable<RoutePoint['location']> } => p.location !== null)
      .map((p, i) => ({
        id: `${p.camera_id}-${i}`,
        lat: p.location.lat,
        lon: p.location.lon,
        color: 'oklch(0.68 0.16 245)',
        label: `${i + 1}. ${p.camera_name} · ${formatTime(p.observed_at)}`,
      })) ?? []

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
            <ExportReportButton plate={route.plate_normalised} />
          </div>
          <div className="relative flex min-h-0 flex-1">
            <div className="relative flex-[1.4]">
              <MapView markers={markers} className="absolute inset-0" />
            </div>
            <aside className="w-[360px] flex-shrink-0 overflow-y-auto border-l border-border-subtle bg-bg-raised p-4">
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-text-tertiary">
                Timeline
              </h2>
              <ol className="flex flex-col gap-3">
                {route.points.map((point, i) => (
                  <li key={`${point.camera_id}-${i}`} className="flex gap-3">
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
