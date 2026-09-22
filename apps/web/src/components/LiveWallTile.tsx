import { PauseCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { camerasApi } from '../lib/api'
import { useInView } from '../lib/useInView'
import type { Camera, CameraStream, Detection } from '../lib/types'
import { HlsVideoPlayer, type PlaybackState } from './HlsVideoPlayer'
import { SeverityBadge, statusToSeverity } from './ui/SeverityBadge'

const STATUS_DOT: Record<string, string> = {
  live: 'bg-ok',
  connecting: 'bg-sev-medium',
  degraded: 'bg-sev-high',
  down: 'bg-sev-critical',
  unknown: 'bg-text-tertiary',
}

function fpsLabel(camera: Camera): string {
  return camera.measured_fps != null ? `${camera.measured_fps.toFixed(0)} fps` : '—'
}

const PLAYBACK_LABEL: Record<PlaybackState, string> = {
  loading: 'Connecting…',
  playing: 'HLS · live',
  buffering: 'HLS · buffering',
  error: 'Stream error',
}

interface LiveWallTileProps {
  camera: Camera
  latestDetection: Detection | undefined
  onOpen: (camera: Camera) => void
}

/** One Live Wall cell. Streams only while at least partially visible
 * (docs/03-UX-DESIGN.md §4.3) — scrolled-off tiles unmount their
 * <HlsVideoPlayer> entirely rather than merely hiding it, which is what
 * actually stops the network/decode work, not just the pixels. */
export function LiveWallTile({ camera, latestDetection, onOpen }: LiveWallTileProps) {
  const { ref, inView } = useInView<HTMLDivElement>(0.15)
  const [stream, setStream] = useState<CameraStream | null>(null)
  const [playback, setPlayback] = useState<PlaybackState>('loading')
  // Read once per render tick via state (not Date.now() inline in the JSX
  // below) so "is this read still recent" re-evaluates on a timer instead
  // of only whenever some unrelated prop happens to re-render this tile.
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 5000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    if (!inView) return
    let cancelled = false
    camerasApi
      .stream(camera.camera_id)
      .then((s) => !cancelled && setStream(s))
      .catch(() => !cancelled && setStream({ available: false, hls_url: null, reason: 'Could not reach the API.' }))
    return () => {
      cancelled = true
    }
  }, [camera.camera_id, inView])

  const recentRead =
    latestDetection && now - new Date(latestDetection.observed_at).getTime() < 30_000 ? latestDetection : undefined

  return (
    <div
      ref={ref}
      onDoubleClick={() => onOpen(camera)}
      className="group relative flex cursor-pointer flex-col overflow-hidden rounded-lg border border-border-subtle bg-bg-raised"
      title="Double-click for details"
    >
      <div className="flex items-center gap-2 border-b border-border-subtle bg-bg-inset px-2.5 py-1.5 text-xs">
        <span className={`h-1.5 w-1.5 flex-shrink-0 rounded-full ${STATUS_DOT[camera.status] ?? STATUS_DOT.unknown}`} />
        <span className="truncate font-medium text-text-primary">{camera.name}</span>
        {camera.department_name && (
          <span className="ml-auto flex-shrink-0 truncate text-text-tertiary">{camera.department_name}</span>
        )}
      </div>

      <div className="relative aspect-video w-full bg-black">
        {!inView && (
          <div className="flex h-full flex-col items-center justify-center gap-1.5 text-text-tertiary">
            <PauseCircle size={20} />
            <span className="text-[11px]">Paused · off-screen</span>
          </div>
        )}
        {inView && !stream && (
          <div className="flex h-full items-center justify-center text-xs text-text-tertiary">Checking stream…</div>
        )}
        {inView && stream?.available && stream.hls_url && (
          <HlsVideoPlayer
            src={stream.hls_url}
            className="h-full w-full"
            controls={false}
            onStateChange={setPlayback}
          />
        )}
        {inView && stream && !stream.available && (
          <div className="flex h-full flex-col items-center justify-center gap-1 p-3 text-center">
            <p className="text-xs text-text-tertiary">{stream.reason ?? 'Preview unavailable'}</p>
          </div>
        )}

        {inView && stream?.available && (
          <span className="absolute bottom-1.5 left-1.5 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-white">
            {PLAYBACK_LABEL[playback]}
          </span>
        )}
        {recentRead && (
          <span className="absolute right-1.5 top-1.5 flex items-center gap-1 rounded bg-black/70 px-1.5 py-0.5 text-[10px]">
            <span className="plate-mono font-semibold text-white">{recentRead.plate_text}</span>
            <span className="text-text-tertiary">{Math.round(recentRead.plate_confidence * 100)}%</span>
          </span>
        )}
      </div>

      <div className="flex items-center gap-2 px-2.5 py-1 text-[11px] text-text-tertiary">
        <SeverityBadge severity={statusToSeverity(camera.status)} label={camera.status} />
        <span className="plate-mono">{fpsLabel(camera)}</span>
      </div>
    </div>
  )
}
