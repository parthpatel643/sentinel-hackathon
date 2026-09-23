import { useEffect, useState } from 'react'
import { Bell, CheckCircle2, Eye, Navigation } from 'lucide-react'
import { alertsApi, camerasApi } from '../lib/api'
import { usePolling } from '../lib/usePolling'
import { useLowBandwidthMode } from './useLowBandwidthMode'
import type { Alert, Camera } from '../lib/types'

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function haversineKm(a: { lat: number; lon: number }, b: { lat: number; lon: number }): number {
  const R = 6371
  const dLat = ((b.lat - a.lat) * Math.PI) / 180
  const dLon = ((b.lon - a.lon) * Math.PI) / 180
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((a.lat * Math.PI) / 180) * Math.cos((b.lat * Math.PI) / 180) * Math.sin(dLon / 2) ** 2
  return R * 2 * Math.asin(Math.sqrt(h))
}

function AlertCard({ alert, camera, myPosition }: { alert: Alert; camera: Camera | undefined; myPosition: GeolocationCoordinates | null }) {
  const [expanded, setExpanded] = useState(false)
  const [busy, setBusy] = useState<'ack' | 'seen' | null>(null)
  const { enabled: lowBandwidth } = useLowBandwidthMode()

  const distanceKm =
    myPosition && camera?.location
      ? haversineKm(
          { lat: myPosition.latitude, lon: myPosition.longitude },
          { lat: camera.location.lat, lon: camera.location.lon },
        )
      : null

  async function act(status: 'acknowledged' | 'resolved', kind: 'ack' | 'seen') {
    setBusy(kind)
    try {
      await alertsApi.update(alert.id, { status })
    } finally {
      setBusy(null)
    }
  }

  function navigate() {
    if (!camera?.location) return
    window.open(`https://www.google.com/maps?q=${camera.location.lat},${camera.location.lon}`, '_blank')
  }

  return (
    <div className="overflow-hidden rounded-xl border border-border-subtle bg-bg-raised">
      {!lowBandwidth && (
        <div className="flex h-28 items-center justify-center bg-bg-inset text-text-tertiary">
          <Bell size={28} />
        </div>
      )}
      <button className="w-full p-4 text-left" onClick={() => setExpanded((v) => !v)}>
        <p className="plate-mono text-xl font-bold text-text-primary">{alert.plate_text}</p>
        <p className="mt-1 text-sm text-text-secondary">
          {camera?.name ?? alert.camera_id} · {formatTime(alert.last_seen_at)}
        </p>
        {distanceKm != null && (
          <p className="mt-0.5 text-sm text-accent">{distanceKm.toFixed(1)} km away</p>
        )}
      </button>
      {expanded && (
        <div className="flex gap-2 border-t border-border-subtle p-3">
          <button
            onClick={navigate}
            disabled={!camera?.location}
            className="flex flex-1 flex-col items-center gap-1 rounded-lg bg-bg-inset py-3 text-xs font-medium text-text-secondary disabled:opacity-40"
          >
            <Navigation size={20} />
            Navigate
          </button>
          <button
            onClick={() => act('acknowledged', 'ack')}
            disabled={busy !== null}
            className="flex flex-1 flex-col items-center gap-1 rounded-lg bg-bg-inset py-3 text-xs font-medium text-text-secondary"
          >
            <CheckCircle2 size={20} />
            {busy === 'ack' ? '…' : 'Acknowledge'}
          </button>
          <button
            onClick={() => act('resolved', 'seen')}
            disabled={busy !== null}
            className="flex flex-1 flex-col items-center gap-1 rounded-lg bg-accent/15 py-3 text-xs font-medium text-accent"
          >
            <Eye size={20} />
            {busy === 'seen' ? '…' : 'I see it'}
          </button>
        </div>
      )}
    </div>
  )
}

export function FieldAlerts() {
  const { data: alerts } = usePolling(() => alertsApi.list('new'), 8000)
  const { data: cameras } = usePolling(() => camerasApi.list(), 30000)
  const [myPosition, setMyPosition] = useState<GeolocationCoordinates | null>(null)

  useEffect(() => {
    if (!navigator.geolocation) return
    const id = navigator.geolocation.watchPosition((pos) => setMyPosition(pos.coords), () => {}, {
      enableHighAccuracy: false,
    })
    return () => navigator.geolocation.clearWatch(id)
  }, [])

  const camerasById = new Map((cameras ?? []).map((c) => [c.camera_id, c]))

  return (
    <div className="flex flex-col gap-3 p-4">
      {alerts?.length === 0 && (
        <p className="py-12 text-center text-sm text-text-tertiary">No open alerts right now.</p>
      )}
      {alerts?.map((alert) => (
        <AlertCard key={alert.id} alert={alert} camera={camerasById.get(alert.camera_id)} myPosition={myPosition} />
      ))}
    </div>
  )
}
