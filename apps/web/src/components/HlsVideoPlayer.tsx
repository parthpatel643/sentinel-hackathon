import Hls from 'hls.js'
import { useEffect, useRef } from 'react'

export type PlaybackState = 'loading' | 'playing' | 'buffering' | 'error'

interface HlsVideoPlayerProps {
  src: string
  className?: string
  onStateChange?: (state: PlaybackState) => void
  controls?: boolean
}

/** Plays an HLS (.m3u8) URL. hls.js (Media Source Extensions) is tried
 * first whenever the browser supports it — real Safari doesn't (no MSE
 * fallback needed, since Safari's own native HLS is solid), but some
 * embedded/Electron-based Chromium builds *report* native HLS support via
 * canPlayType() while their native demuxer can't actually parse MediaMTX's
 * fMP4/CMAF segments (confirmed here: DEMUXER_ERROR_COULD_NOT_PARSE from
 * the browser's own pipeline, not from hls.js) — trusting canPlayType()
 * over Hls.isSupported() silently broke every tile. Native <video src>
 * HLS is now only the fallback for engines hls.js genuinely can't run on.
 * `lowLatencyMode` is left off: MediaMTX's LL-HLS output hit a demuxer
 * parse error under hls.js's low-latency path during testing; standard
 * HLS trades a little latency for reliability here. hls.js's own
 * documented pattern for recovering from non-fatal errors (buffer stalls,
 * a dropped segment) is followed rather than treating every ERROR event as
 * fatal — those are expected on a live, looping source. */
export function HlsVideoPlayer({ src, className, onStateChange, controls = true }: HlsVideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null)

  useEffect(() => {
    const video = videoRef.current
    if (!video) return

    const report = (state: PlaybackState) => onStateChange?.(state)
    video.addEventListener('playing', () => report('playing'))
    video.addEventListener('waiting', () => report('buffering'))
    video.addEventListener('error', () => report('error'))

    if (Hls.isSupported()) {
      const hls = new Hls()
      hls.on(Hls.Events.ERROR, (_event, data) => {
        if (!data.fatal) return
        switch (data.type) {
          case Hls.ErrorTypes.NETWORK_ERROR:
            hls.startLoad()
            break
          case Hls.ErrorTypes.MEDIA_ERROR:
            hls.recoverMediaError()
            break
          default:
            report('error')
            hls.destroy()
        }
      })
      hls.loadSource(src)
      hls.attachMedia(video)
      return () => hls.destroy()
    }

    if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = src
      return undefined
    }

    report('error')
    return undefined
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src])

  return (
    <video
      ref={videoRef}
      className={className}
      controls={controls}
      autoPlay
      muted
      playsInline
      style={{ background: '#000' }}
    />
  )
}
