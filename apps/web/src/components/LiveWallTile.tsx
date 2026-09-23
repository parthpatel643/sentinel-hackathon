import { ArrowUpRight, PauseCircle, VideoOff } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
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

const PLAYBACK_LABEL_KEY: Record<PlaybackState, string> = {
  loading: 'liveWall.playback.loading',
  playing: 'liveWall.playback.playing',
  buffering: 'liveWall.playback.buffering',
  error: 'liveWall.playback.error',
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
  const { t } = useTranslation()
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
      .catch(() => !cancelled && setStream({ available: false, hls_url: null, reason: t('cameraDetail.couldNotReachApi') }))
    return () => {
      cancelled = true
    }
  }, [camera.camera_id, inView, t])

  const recentRead =
    latestDetection && now - new Date(latestDetection.observed_at).getTime() < 30_000 ? latestDetection : undefined

  return (
    <div
      ref={ref}
      onDoubleClick={() => onOpen(camera)}
      className="monitoring-feed group relative flex flex-col overflow-hidden"
      title={t('liveWall.doubleClickDetails')}
    >
      <div className="monitoring-feed-heading">
        <span className={`h-1.5 w-1.5 flex-shrink-0 rounded-full ${STATUS_DOT[camera.status] ?? STATUS_DOT.unknown}`} />
        <button className="monitoring-feed-open" onClick={() => onOpen(camera)} aria-label={t('monitoring:openDetails', { name: camera.name })}><span>{camera.name}</span><ArrowUpRight size={15} /></button>
      </div>

      <div className="monitoring-video relative aspect-video w-full">
        {!inView && (
          <div className="flex h-full flex-col items-center justify-center gap-1.5 text-text-tertiary">
            <PauseCircle size={20} />
            <span className="text-[11px]">{t('liveWall.pausedOffscreen')}</span>
          </div>
        )}
        {inView && !stream && (
          <div className="flex h-full items-center justify-center text-xs text-text-tertiary">
            {t('liveWall.checkingStream')}
          </div>
        )}
        {inView && stream?.available && stream.hls_url && (
          <HlsVideoPlayer
            src={stream.hls_url}
            className="h-full w-full"
            controls={false}
            onStateChange={setPlayback}
          />
        )}
        {inView && stream && (!stream.available || !stream.hls_url) && (
          <div className="flex h-full flex-col items-center justify-center gap-1 p-3 text-center">
            <VideoOff size={24} strokeWidth={1.5} className="mb-2" />
            <strong className="text-xs">{t('monitoring:unavailable')}</strong>
            <p className="text-xs">{stream.reason ?? t('liveWall.previewUnavailable')}</p>
          </div>
        )}

        {inView && stream?.available && (
          <span className="absolute bottom-1.5 left-1.5 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-white">
            {t(PLAYBACK_LABEL_KEY[playback])}
          </span>
        )}
        {recentRead && (
          <span className="absolute right-1.5 top-1.5 flex items-center gap-1 rounded bg-black/70 px-1.5 py-0.5 text-[10px]">
            <span className="plate-mono font-semibold text-white">{recentRead.plate_text}</span>
            <span className="text-text-tertiary">{Math.round(recentRead.plate_confidence * 100)}%</span>
          </span>
        )}
      </div>

      <div className="monitoring-feed-footer">
        <SeverityBadge severity={statusToSeverity(camera.status)} label={t(`cameraStatus.${camera.status}`)} />
        <span className="plate-mono">{fpsLabel(camera)}</span>
        <span className="ml-auto truncate">{camera.department_name ?? camera.camera_id}</span>
      </div>
    </div>
  )
}
