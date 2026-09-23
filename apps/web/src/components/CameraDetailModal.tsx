import { useEffect, useState } from 'react'
import { camerasApi, zonesApi } from '../lib/api'
import type { Camera, CameraStream, Zone, ZoneEvent } from '../lib/types'
import { HlsVideoPlayer } from './HlsVideoPlayer'
import { Button } from './ui/Button'
import { Modal } from './ui/Modal'
import { SeverityBadge, statusToSeverity } from './ui/SeverityBadge'
import { useAuth } from '../lib/AuthContext'

const PRESET_REGIONS: { label: string; polygon: number[][] }[] = [
  { label: 'Full frame', polygon: [[0, 0], [1, 0], [1, 1], [0, 1]] },
  { label: 'Left half', polygon: [[0, 0], [0.5, 0], [0.5, 1], [0, 1]] },
  { label: 'Right half', polygon: [[0.5, 0], [1, 0], [1, 1], [0.5, 1]] },
  { label: 'Top half', polygon: [[0, 0], [1, 0], [1, 0.5], [0, 0.5]] },
  { label: 'Bottom half', polygon: [[0, 0.5], [1, 0.5], [1, 1], [0, 1]] },
  { label: 'Centre third', polygon: [[0.33, 0.33], [0.67, 0.33], [0.67, 0.67], [0.33, 0.67]] },
]

const RULE_TYPES = [
  { value: 'intrusion', label: 'Intrusion' },
  { value: 'loitering', label: 'Loitering' },
  { value: 'wrong_way', label: 'Wrong-way' },
  { value: 'stopped_vehicle', label: 'Stopped vehicle' },
]

interface CameraDetailModalProps {
  camera: Camera | null
  onClose: () => void
}

function fpsLabel(camera: Camera): string {
  if (camera.measured_fps == null) return '—'
  const declared = camera.declared_fps != null ? `/${camera.declared_fps.toFixed(0)}` : ''
  return `${camera.measured_fps.toFixed(1)}${declared} fps`
}

/** M13 secondary analytics: zone rules for this camera. A preset-region
 * picker rather than a draw-your-own-polygon canvas — the rule *engine*
 * (edge_agent.analytics.zone_rules) accepts any polygon; this is a
 * deliberately simple configuration surface on top of it, not a
 * limitation of what the engine itself can express. */
function ZoneRulesSection({ camera }: { camera: Camera }) {
  const { user } = useAuth()
  const [zones, setZones] = useState<Zone[] | null>(null)
  const [events, setEvents] = useState<ZoneEvent[] | null>(null)
  const [adding, setAdding] = useState(false)
  const [name, setName] = useState('')
  const [ruleType, setRuleType] = useState(RULE_TYPES[0].value)
  const [presetIndex, setPresetIndex] = useState(0)
  const [error, setError] = useState<string | null>(null)

  function load() {
    zonesApi.list(camera.camera_id).then(setZones)
    zonesApi.events(camera.camera_id).then(setEvents)
  }

  useEffect(load, [camera.camera_id])

  function createZone() {
    if (!name.trim()) return
    setError(null)
    zonesApi
      .create(camera.camera_id, {
        name: name.trim(),
        rule_type: ruleType,
        polygon: PRESET_REGIONS[presetIndex].polygon,
      })
      .then(() => {
        setName('')
        setAdding(false)
        load()
      })
      .catch(() => setError('Could not create this zone.'))
  }

  return (
    <div className="flex flex-col gap-3 border-t border-border-subtle pt-4">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-text-primary">Zone rules</p>
        {user?.role === 'admin' && (
          <Button size="sm" variant="secondary" onClick={() => setAdding((v) => !v)}>
            {adding ? 'Cancel' : 'Add zone'}
          </Button>
        )}
      </div>

      {adding && (
        <div className="flex flex-col gap-2 rounded-md bg-bg-inset p-3">
          <input
            className="rounded-md border border-border-subtle bg-bg-base px-2.5 py-1.5 text-sm text-text-primary"
            placeholder="Zone name (e.g. Loading Bay)"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <div className="flex gap-2">
            <select
              className="flex-1 rounded-md border border-border-subtle bg-bg-base px-2.5 py-1.5 text-sm text-text-primary"
              value={ruleType}
              onChange={(e) => setRuleType(e.target.value)}
            >
              {RULE_TYPES.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
            <select
              className="flex-1 rounded-md border border-border-subtle bg-bg-base px-2.5 py-1.5 text-sm text-text-primary"
              value={presetIndex}
              onChange={(e) => setPresetIndex(Number(e.target.value))}
            >
              {PRESET_REGIONS.map((r, i) => (
                <option key={r.label} value={i}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>
          <Button size="sm" onClick={createZone}>
            Create
          </Button>
          {error && <p className="text-xs text-sev-critical">{error}</p>}
        </div>
      )}

      {zones && zones.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm">
          {zones.map((z) => (
            <li key={z.id} className="flex items-center justify-between rounded-md bg-bg-inset px-3 py-1.5">
              <span className="text-text-primary">{z.name}</span>
              <span className="text-xs text-text-tertiary">{z.rule_type}</span>
            </li>
          ))}
        </ul>
      )}
      {zones && zones.length === 0 && !adding && (
        <p className="text-xs text-text-tertiary">No zone rules configured for this camera yet.</p>
      )}

      {events && events.length > 0 && (
        <div>
          <p className="mb-1 text-xs uppercase tracking-wide text-text-tertiary">Recent zone events</p>
          <ul className="flex flex-col gap-1 text-xs text-text-secondary">
            {events.slice(0, 5).map((e) => (
              <li key={e.id}>
                {new Date(e.observed_at).toLocaleTimeString()} — {e.zone_name ?? e.zone_id} (
                {e.rule_type}
                {e.dwell_time_s != null ? `, ${e.dwell_time_s.toFixed(0)}s` : ''})
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

/** The Cameras screen's "click a camera, see it" moment. Never asks for or
 * touches a raw stream URL itself — that would mean handling gov-catalogue
 * credentials in the browser, which core_api's /stream endpoint exists
 * specifically to avoid (see registry/service.py's resolve_camera_stream).
 * A camera outside our own local relay is reported as unavailable with a
 * plain-language reason instead of silently failing. */
export function CameraDetailModal({ camera, onClose }: CameraDetailModalProps) {
  const [stream, setStream] = useState<CameraStream | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!camera) {
      setStream(null)
      return
    }
    setLoading(true)
    setStream(null)
    camerasApi
      .stream(camera.camera_id)
      .then(setStream)
      .catch(() => setStream({ available: false, hls_url: null, reason: 'Could not reach the API.' }))
      .finally(() => setLoading(false))
  }, [camera])

  return (
    <Modal open={camera !== null} onOpenChange={(open) => !open && onClose()} title={camera?.name ?? ''}>
      {camera && (
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <SeverityBadge severity={statusToSeverity(camera.status)} label={camera.status} />
            <span className="text-text-tertiary">{camera.camera_id}</span>
            {camera.department_name && <span className="text-text-secondary">{camera.department_name}</span>}
            <span className="plate-mono text-text-secondary">{fpsLabel(camera)}</span>
          </div>

          <div className="aspect-video w-full overflow-hidden rounded-md bg-bg-inset">
            {loading && (
              <div className="flex h-full items-center justify-center text-sm text-text-tertiary">
                Checking stream…
              </div>
            )}
            {!loading && stream?.available && stream.hls_url && (
              <HlsVideoPlayer src={stream.hls_url} className="h-full w-full" />
            )}
            {!loading && stream && !stream.available && (
              <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
                <p className="text-sm text-text-secondary">{stream.reason ?? 'Live preview unavailable.'}</p>
              </div>
            )}
          </div>

          <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
            <div>
              <dt className="text-text-tertiary">Tier</dt>
              <dd className="text-text-primary">{camera.tier}</dd>
            </div>
            <div>
              <dt className="text-text-tertiary">Reconnects</dt>
              <dd className="text-text-primary">{camera.reconnects}</dd>
            </div>
            <div>
              <dt className="text-text-tertiary">Source</dt>
              <dd className="text-text-primary">{camera.source}</dd>
            </div>
            <div>
              <dt className="text-text-tertiary">Last seen</dt>
              <dd className="text-text-primary">
                {camera.last_seen_at ? new Date(camera.last_seen_at).toLocaleString() : '—'}
              </dd>
            </div>
          </dl>

          <ZoneRulesSection camera={camera} />
        </div>
      )}
    </Modal>
  )
}
