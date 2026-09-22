import { useEffect, useState } from 'react'
import { camerasApi } from '../lib/api'
import type { Camera, CameraStream } from '../lib/types'
import { HlsVideoPlayer } from './HlsVideoPlayer'
import { Modal } from './ui/Modal'
import { SeverityBadge, statusToSeverity } from './ui/SeverityBadge'

interface CameraDetailModalProps {
  camera: Camera | null
  onClose: () => void
}

function fpsLabel(camera: Camera): string {
  if (camera.measured_fps == null) return '—'
  const declared = camera.declared_fps != null ? `/${camera.declared_fps.toFixed(0)}` : ''
  return `${camera.measured_fps.toFixed(1)}${declared} fps`
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
        </div>
      )}
    </Modal>
  )
}
