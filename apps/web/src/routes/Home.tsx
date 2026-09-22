import { useMemo } from 'react'
import { alertsApi, camerasApi } from '../lib/api'
import { usePolling } from '../lib/usePolling'
import { MapView, type MapMarker } from '../components/MapView'
import { TopBar } from '../components/layout/TopBar'
import { Card } from '../components/ui/Card'
import { SeverityBadge, priorityToSeverity } from '../components/ui/SeverityBadge'
import type { Alert, Camera } from '../lib/types'
import { Link } from 'react-router-dom'

const STATUS_COLOR: Record<string, string> = {
  live: 'oklch(0.72 0.16 155)',
  connecting: 'oklch(0.72 0.13 230)',
  degraded: 'oklch(0.75 0.17 65)',
  down: 'oklch(0.62 0.21 25)',
  unknown: 'oklch(0.66 0.02 250)',
}

function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime()
  const minutes = Math.round(ms / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.round(hours / 24)}d ago`
}

function AttentionCard({ alert }: { alert: Alert }) {
  return (
    <Link to="/alerts" className="block">
      <Card className="p-3 hover:border-border-strong">
        <div className="mb-1.5 flex items-center justify-between gap-2">
          <SeverityBadge severity={priorityToSeverity('critical')} label="Watchlist hit" />
          <span className="text-xs text-text-tertiary">{timeAgo(alert.last_seen_at)}</span>
        </div>
        <p className="plate-mono text-lg font-semibold text-text-primary">{alert.plate_text}</p>
        <p className="mt-1 truncate text-xs text-text-secondary">
          {alert.camera_id} · {alert.sighting_count} sighting{alert.sighting_count === 1 ? '' : 's'}
        </p>
      </Card>
    </Link>
  )
}

export function Home() {
  const { data: cameras } = usePolling(() => camerasApi.list(), 8000)
  const { data: alerts } = usePolling(() => alertsApi.list('new'), 6000)

  const markers = useMemo<MapMarker[]>(() => {
    if (!cameras) return []
    return cameras
      .filter((c): c is Camera & { location: NonNullable<Camera['location']> } => c.location !== null)
      .map((c) => ({
        id: c.camera_id,
        lat: c.location.lat,
        lon: c.location.lon,
        color: STATUS_COLOR[c.status] ?? STATUS_COLOR.unknown,
        label: `${c.name} · ${c.status}`,
      }))
  }, [cameras])

  const liveCount = cameras?.filter((c) => c.status === 'live').length ?? 0
  const downCount = cameras?.filter((c) => c.status === 'down').length ?? 0
  const degradedCount = cameras?.filter((c) => c.status === 'degraded').length ?? 0

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <TopBar title="Sentinel" subtitle="Situational awareness" />
      <div className="relative flex min-h-0 flex-1">
        <div className="relative flex-1">
          <MapView markers={markers} className="absolute inset-0" />
          <Card className="absolute bottom-4 left-4 z-10 px-4 py-2.5 text-sm">
            <span className="text-ok font-medium">{liveCount} live</span>
            <span className="mx-2 text-border-strong">·</span>
            <span className="text-sev-critical font-medium">{downCount} down</span>
            <span className="mx-2 text-border-strong">·</span>
            <span className="text-sev-high font-medium">{degradedCount} degraded</span>
          </Card>
        </div>
        <aside className="w-[320px] flex-shrink-0 overflow-y-auto border-l border-border-subtle bg-bg-raised p-4">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-text-tertiary">
            Needs attention
          </h2>
          {!alerts && <p className="text-sm text-text-tertiary">Loading…</p>}
          {alerts?.length === 0 && (
            <p className="text-sm text-text-tertiary">Nothing needs you right now.</p>
          )}
          <div className="flex flex-col gap-2">
            {alerts?.map((alert) => (
              <AttentionCard key={alert.id} alert={alert} />
            ))}
          </div>
        </aside>
      </div>
    </div>
  )
}
