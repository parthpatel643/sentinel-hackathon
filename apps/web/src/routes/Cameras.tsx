import { useState } from 'react'
import { camerasApi } from '../lib/api'
import { usePolling } from '../lib/usePolling'
import { TopBar } from '../components/layout/TopBar'
import { Card } from '../components/ui/Card'
import { SeverityBadge, statusToSeverity } from '../components/ui/SeverityBadge'
import { MapView, type MapMarker } from '../components/MapView'
import { Button } from '../components/ui/Button'
import type { Camera } from '../lib/types'

const STATUS_COLOR: Record<string, string> = {
  live: 'oklch(0.72 0.16 155)',
  connecting: 'oklch(0.72 0.13 230)',
  degraded: 'oklch(0.75 0.17 65)',
  down: 'oklch(0.62 0.21 25)',
  unknown: 'oklch(0.66 0.02 250)',
}

function fpsLabel(camera: Camera): string {
  if (camera.measured_fps == null) return '—'
  const declared = camera.declared_fps != null ? `/${camera.declared_fps.toFixed(0)}` : ''
  return `${camera.measured_fps.toFixed(1)}${declared} fps`
}

export function Cameras() {
  const { data: cameras, loading } = usePolling(() => camerasApi.list(), 10000)
  const [view, setView] = useState<'table' | 'map'>('table')

  const markers: MapMarker[] =
    cameras
      ?.filter((c): c is Camera & { location: NonNullable<Camera['location']> } => c.location !== null)
      .map((c) => ({
        id: c.camera_id,
        lat: c.location.lat,
        lon: c.location.lon,
        color: STATUS_COLOR[c.status] ?? STATUS_COLOR.unknown,
        label: c.name,
      })) ?? []

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <TopBar title="Cameras" subtitle={cameras ? `${cameras.length} registered` : undefined} />
      <div className="flex items-center gap-2 border-b border-border-subtle px-6 py-3">
        <Button size="sm" variant={view === 'table' ? 'primary' : 'secondary'} onClick={() => setView('table')}>
          Table
        </Button>
        <Button size="sm" variant={view === 'map' ? 'primary' : 'secondary'} onClick={() => setView('map')}>
          Map
        </Button>
      </div>

      {view === 'map' ? (
        <div className="relative flex-1">
          <MapView markers={markers} className="absolute inset-0" />
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-6">
          {loading && !cameras && <p className="text-sm text-text-tertiary">Loading cameras…</p>}
          {cameras?.length === 0 && (
            <p className="text-sm text-text-tertiary">
              No cameras registered yet. Run catalogue discovery or add one manually via the API.
            </p>
          )}
          {cameras && cameras.length > 0 && (
            <Card className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className="border-b border-border-subtle text-xs uppercase tracking-wide text-text-tertiary">
                  <tr>
                    <th className="px-4 py-2.5 font-medium">Name</th>
                    <th className="px-4 py-2.5 font-medium">Department</th>
                    <th className="px-4 py-2.5 font-medium">Tier</th>
                    <th className="px-4 py-2.5 font-medium">Status</th>
                    <th className="px-4 py-2.5 font-medium">FPS</th>
                    <th className="px-4 py-2.5 font-medium">Reconnects</th>
                  </tr>
                </thead>
                <tbody>
                  {cameras.map((camera) => (
                    <tr key={camera.camera_id} className="border-b border-border-subtle/60 last:border-0">
                      <td className="px-4 py-2.5">
                        <div className="font-medium text-text-primary">{camera.name}</div>
                        <div className="text-xs text-text-tertiary">{camera.camera_id}</div>
                      </td>
                      <td className="px-4 py-2.5 text-text-secondary">{camera.department_name ?? '—'}</td>
                      <td className="px-4 py-2.5 text-text-secondary">{camera.tier}</td>
                      <td className="px-4 py-2.5">
                        <SeverityBadge severity={statusToSeverity(camera.status)} label={camera.status} />
                      </td>
                      <td className="px-4 py-2.5 plate-mono text-text-secondary">{fpsLabel(camera)}</td>
                      <td className="px-4 py-2.5 text-text-secondary">{camera.reconnects}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </div>
      )}
    </div>
  )
}
